#!/usr/bin/env python3
"""
vod_heal.py - find and repair VOD symlinks that Radarr/Sonarr upgrades left dangling.

RUN ON EACH LOAD BALANCER that has the movies/ folder of <id>.<ext> symlinks and the
rclone mount (/mnt/unionfs). Run as the xtreamcodes user.

PROBLEM
  movies/123.mkv -> /mnt/unionfs/Media/Movies/Movies/Title (2020) [imdb-tt1]/Title.2020.1080p.mkv
  Radarr/Sonarr later replace the file with a better release (new filename, sometimes a new
  folder). The symlink now points at nothing, so the title will not play, and nothing in the
  panel tells you.

WHAT THIS DOES
  1. Scans every symlink in movies/ and checks whether its target still exists.
     This is a DIRECTORY-LISTING check served from rclone's directory cache. It never opens or
     reads a file, so it does not download data and does not spend Google Drive download quota.
  2. For each dangling link, finds the replacement:
       movie   -> the single video file in the same folder; if that folder is gone, looks the
                  folder up by its [imdb-tt...] tag (or "Title (Year)") under the media root.
       episode -> the file with the same SxxExx inside the show folder (any season subfolder);
                  if the show folder moved, looks it up the same way.
  3. With --apply, atomically repoints the link (same <id>.<ext> name, so the panel database
     does not change). Anything ambiguous or not found is left alone and listed for you.

SAFETY
  * Default is a DRY RUN: it only reports. Nothing changes without --apply.
  * Never deletes anything. Repointing is atomic (new link swapped in with rename).
  * Every change is logged with the old target, and --undo <log> restores them.
  * If the media mount looks dead (missing/empty, or more than --max-broken-pct of links
    appear broken) it refuses to touch anything unless you pass --force. A dead mount makes
    every link look broken, which must never trigger a mass "repair".
  * Ambiguous matches (several candidate files) are skipped unless --pick-largest.
  * Only one run at a time (lock file).

USAGE
  python3 vod_heal.py                       # dry run, report only
  python3 vod_heal.py --apply               # repair what can be repaired safely
  python3 vod_heal.py --undo /path/to/heal_YYYYmmdd_HHMMSS.tsv
  python3 vod_heal.py --help
"""
import argparse
import collections
import datetime
import fcntl
import glob
import os
import random
import re
import sys
import time
import unicodedata

VERSION = "2026-11-08-E (trial, only-ids, find-gone, peek, auto-pick-2160p, panel-info, decisions)"

VIDEO_EXT = {".mkv", ".mp4", ".avi", ".m4v", ".mov", ".ts", ".wmv", ".mpg", ".mpeg", ".webm"}
JUNK_RE = re.compile(r"(?i)(^|[\W_])(sample|trailer|featurette|extras?|behind[\W_]the[\W_]scenes|deleted[\W_]scenes)([\W_]|$)")
EP_RE = re.compile(r"(?i)(?<![a-z0-9])s(\d{1,3})[ ._-]?e(\d{1,4})((?:[ ._-]?-?e\d{1,4})*)")
SEASON_RE = re.compile(r"(?i)^(season|series|specials?)\b|^s\d{1,3}$")
TAG_RE = re.compile(r"(?i)[\[{(](imdb|tmdb|tvdb)-?(tt\d+|\d+)[\]})]")   # [imdb-tt1] {tvdb-12} ...
YEAR_RE = re.compile(r"\((\d{4})\)")


def norm_text(s):
    """lower-case, accents folded, '&' -> 'and', everything but letters/digits dropped."""
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode("ascii").lower().replace("&", "and")
    return re.sub(r"[^a-z0-9]+", "", s)


def tag_keys(name):
    """Stable ids found in a folder name, e.g. ['imdb:tt1', 'tvdb:12']. Empty tags like [imdb-] give none."""
    return ["%s:%s" % (m.group(1).lower(), m.group(2).lower()) for m in TAG_RE.finditer(name)]


def folder_tags(name):
    d = {}
    for m in TAG_RE.finditer(name):
        d.setdefault(m.group(1).lower(), set()).add(m.group(2).lower())
    return d


def folder_year(name):
    m = YEAR_RE.search(name)
    return int(m.group(1)) if m else None


def conflicts(old_name, cand_name, weak):
    """Return a reason string if the candidate folder is PROVABLY a different title, else ''.
      * both names carry an imdb/tmdb/tvdb id of the same kind and the ids differ  -> different title
      * (title-only matches) both names have a year and they are more than 1 apart  -> remake/other film
    A year off by one is allowed because metadata corrections of +-1 year are common."""
    ot, ct = folder_tags(old_name), folder_tags(cand_name)
    for kind in ot:
        if kind in ct and not (ot[kind] & ct[kind]):
            return "different-%s-id" % kind
    if weak:
        oy, cy = folder_year(old_name), folder_year(cand_name)
        if oy and cy and abs(oy - cy) > 1:
            return "years-differ-%d-vs-%d" % (oy, cy)
    return ""


def norm_key(name):
    """'Alpha (2020) [imdb-tt1]' -> 'alpha2020'. Only used when the name has a (YYYY) year."""
    if not YEAR_RE.search(name):
        return ""
    return norm_text(re.sub(r"[\[{].*?[\]}]", " ", name))


def title_key(name):
    """Title with the year and any tags removed: 'Hook (1991) [imdb-tt1]' -> 'hook'.
    Weakest match (a remake can share it), so it is opt-in."""
    s = re.sub(r"[\[{].*?[\]}]", " ", name)
    s = YEAR_RE.sub(" ", s)
    return norm_text(s)


RES_RE = re.compile(r"(?i)(?<![0-9])(2160|1440|1080|720|576|480|360)\s*[pi]?(?![0-9])|(?<![a-z0-9])(4k|uhd)(?![a-z0-9])")
PART_RE = re.compile(r"(?i)(?<![a-z0-9])(cd|disc|disk|part|pt)[ ._-]?\d{1,2}(?![0-9])")


def resolution_of(name):
    """2160 / 1080 / 720 ... from a release name ('4K' and 'UHD' count as 2160). 0 if not stated."""
    best = 0
    for m in RES_RE.finditer(name):
        if m.group(1):
            best = max(best, int(m.group(1)))
        elif m.group(2):
            best = max(best, 2160)
    return best


DATE_RE = re.compile(r"(?<!\d)(\d{4})[.\-_ ](\d{2})[.\-_ ](\d{2})(?!\d)")


def air_date(filename):
    """'Daily.Show.2024-01-05.mkv' -> '2024-01-05' (daily shows have no SxxExx). None if no date."""
    m = DATE_RE.search(filename)
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if not (1900 <= y <= 2100 and 1 <= mo <= 12 and 1 <= d <= 31):
        return None
    return "%04d-%02d-%02d" % (y, mo, d)


def episodes_in(filename):
    """Set of (season, episode) tuples named in a filename, including multi-episode files."""
    out = set()
    for m in EP_RE.finditer(filename):
        season = int(m.group(1))
        out.add((season, int(m.group(2))))
        for e in re.findall(r"(?i)e(\d{1,4})", m.group(3) or ""):
            out.add((season, int(e)))
    return out


def first_episode(filename):
    m = EP_RE.search(filename)
    return (int(m.group(1)), int(m.group(2))) if m else None


class DirCache(object):
    """Directory listings, each fetched at most once. None means 'directory does not exist'.
    Any other OSError (I/O error, mount trouble) propagates so the caller can count it."""

    def __init__(self):
        self.d = {}

    def names(self, path):
        if path in self.d:
            return self.d[path]
        try:
            with os.scandir(path) as it:
                v = set(e.name for e in it)
        except (FileNotFoundError, NotADirectoryError):
            v = None
        self.d[path] = v
        return v


class Index(object):
    """Folders under the media roots, found by IMDb tag and by normalised 'Title (Year)'.
    Built lazily, only if a link actually needs it, and only lists directories (never files)."""

    def __init__(self, roots, depth):
        self.roots, self.depth, self.built = roots, depth, False
        self.by_tag = collections.defaultdict(list)     # imdb/tmdb/tvdb id  (strong)
        self.by_norm = collections.defaultdict(list)    # 'title+year'       (strong)
        self.by_title = collections.defaultdict(list)   # title only         (weak, opt-in)

    def build(self):
        if self.built:
            return
        self.built = True

        def register(path, name):
            for k in tag_keys(name):
                self.by_tag[k].append(path)
            k = norm_key(name)
            if k:
                self.by_norm[k].append(path)
            k = title_key(name)
            if k:
                self.by_title[k].append(path)

        def walk(p, level):
            try:
                entries = list(os.scandir(p))
            except OSError:
                return
            for e in entries:
                try:
                    if not e.is_dir(follow_symlinks=False):
                        continue
                except OSError:
                    continue
                if level + 1 == self.depth:
                    register(e.path, e.name)
                elif level + 1 < self.depth:
                    walk(e.path, level + 1)

        for r in self.roots:
            walk(r, 0)

    def lookup(self, folder_name):
        """Return (strong, weak): strong = same stable id or same 'title+year'; weak = same title only."""
        self.build()
        strong = []
        for k in tag_keys(folder_name):
            strong += self.by_tag.get(k, [])
        k = norm_key(folder_name)
        if k:
            strong += self.by_norm.get(k, [])
        seen = set()
        strong = [p for p in strong if not (p in seen or seen.add(p))]
        weak = [p for p in self.by_title.get(title_key(folder_name), []) if p not in seen]
        return strong, weak


def common_depth(a, b):
    n = 0
    for x, y in zip(a.split("/"), b.split("/")):
        if x != y:
            break
        n += 1
    return n


class Healer(object):
    def __init__(self, roots, depth, auto_pick=True, allow_title_only=False, decisions=None, panel_year=None):
        self.cache = DirCache()
        self.index = Index(roots, depth)
        self.auto_pick = auto_pick
        self.panel_year = panel_year or {}    # stream id -> release year the PANEL has for it
        self.allow_title_only = allow_title_only
        self.decisions = decisions or {}      # old title-folder name -> path | GONE | SKIP  (from you)
        self.multi_rej = []

    # ---- helpers -------------------------------------------------------------------------
    def target_exists(self, target):
        names = self.cache.names(os.path.dirname(target))
        return names is not None and os.path.basename(target) in names

    def movie_files(self, folder):
        names = self.cache.names(folder)
        out = []
        for n in sorted(names or ()):
            if os.path.splitext(n)[1].lower() in VIDEO_EXT and not JUNK_RE.search(n):
                out.append(os.path.join(folder, n))
        return out

    def episode_files(self, show_folder, key, old_eps=None):
        """Files in a show folder that contain episode `key`.
        A double-episode file (S01E25-E26) replacing a single-episode link is only accepted when `key`
        is the FIRST episode in it; otherwise the viewer would start in the wrong episode, silently."""
        out = []

        def ok(path, name):
            eps = episodes_in(name)
            if key not in eps:
                return False
            if old_eps is not None and len(eps) > max(1, len(old_eps)) and key != min(eps):
                self.multi_rej.append(path)
                return False
            return True

        top = self.cache.names(show_folder)
        if top is None:
            return out
        for n in sorted(top):
            p = os.path.join(show_folder, n)
            if os.path.splitext(n)[1].lower() in VIDEO_EXT:
                if not JUNK_RE.search(n) and ok(p, n):
                    out.append(p)
                continue
            sub = self.cache.names(p)
            if sub is None:
                continue
            for fn in sorted(sub):
                if os.path.splitext(fn)[1].lower() in VIDEO_EXT and not JUNK_RE.search(fn):
                    if ok(os.path.join(p, fn), fn):
                        out.append(os.path.join(p, fn))
        # if a normal single-episode file exists, never prefer a double-episode file over it
        singles = [x for x in out if len(episodes_in(os.path.basename(x))) <= max(1, len(old_eps or ()))]
        return singles if singles else out

    def date_files(self, show_folder, dkey):
        """Daily shows: files anywhere in the show folder whose name carries the same air date."""
        out = []
        top = self.cache.names(show_folder)
        if top is None:
            return out
        for n in sorted(top):
            p = os.path.join(show_folder, n)
            if os.path.splitext(n)[1].lower() in VIDEO_EXT:
                if not JUNK_RE.search(n) and air_date(n) == dkey:
                    out.append(p)
                continue
            sub = self.cache.names(p)
            for fn in sorted(sub or ()):
                if (os.path.splitext(fn)[1].lower() in VIDEO_EXT and not JUNK_RE.search(fn)
                        and air_date(fn) == dkey):
                    out.append(os.path.join(p, fn))
        return out

    def suggest(self, old_name):
        """Folders on the drive that MIGHT be the same title, for the worksheet. Never applied
        automatically. Returns [(path, note)], note is a reason it is probably a different title."""
        self.index.build()
        strong, weak = self.index.lookup(old_name)
        found, seen = [], set()
        for alt in strong + weak:
            if alt in seen:
                continue
            seen.add(alt)
            found.append((alt, conflicts(old_name, os.path.basename(alt), weak=(alt in weak))))
        tk = title_key(old_name)
        if len(tk) >= 4:                    # cheap containment: "agentsofshield" inside "marvelsagentsofshield"
            for k, paths in self.index.by_title.items():
                if k != tk and len(k) >= 4 and (tk in k or k in tk):
                    for alt in paths:
                        if alt not in seen:
                            seen.add(alt)
                            found.append((alt, conflicts(old_name, os.path.basename(alt), weak=True)))
        found.sort(key=lambda x: (x[1] != "", len(x[0])))
        return found[:3]

    def choose(self, cands, old_target):
        """Return (path, note). path is None if there is no single safe choice."""
        seen, uniq = set(), []
        for c in cands:
            if c not in seen:
                seen.add(c)
                uniq.append(c)
        if not uniq:
            return None, "no-replacement-found"
        if len(uniq) == 1:
            return uniq[0], ""
        scored = sorted(((common_depth(c, old_target), c) for c in uniq), reverse=True)
        if scored[0][0] > scored[1][0]:
            return scored[0][1], "chose-nearest-folder"
        if self.auto_pick:
            # several versions of the same movie/episode: take the best quality (2160p > 1080p > ...),
            # then the largest file. But a movie split into parts (CD1/CD2, Part 1/2) is NOT several
            # versions - picking one part would silently cut the film, so that stays manual.
            if any(PART_RE.search(os.path.basename(c)) for c in uniq):
                return None, "ambiguous-multi-part:" + " | ".join(uniq[:4])

            def size(p):
                try:
                    return os.stat(p).st_size           # metadata only
                except OSError:
                    return -1
            best = max(uniq, key=lambda p: (resolution_of(os.path.basename(p)), size(p)))
            return best, "chose-best-quality"
        return None, "ambiguous:" + " | ".join(uniq[:4])

    # ---- main resolution -----------------------------------------------------------------
    def resolve(self, old_target, link_id=None):
        """Return (new_target or None, note)."""
        py = self.panel_year.get(link_id) if link_id else None   # year the panel knows for this title
        base = os.path.basename(old_target)
        parent = os.path.dirname(old_target)
        pname = os.path.basename(parent)
        key = first_episode(base)

        self.multi_rej = []
        dkey = air_date(base) if key is None else None
        if key is not None:                               # an episode
            folder = os.path.dirname(parent) if SEASON_RE.match(pname) else parent
            old_eps = episodes_in(base)
            finder = lambda f: self.episode_files(f, key, old_eps)
        elif dkey and SEASON_RE.match(pname):             # daily show: match by air date
            folder = os.path.dirname(parent)
            finder = lambda f: self.date_files(f, dkey)
        else:                                             # a movie
            if SEASON_RE.match(pname):
                return None, "episode-name-has-no-SxxExx (manual)"
            folder = parent
            finder = self.movie_files

        # ---- your decision for this title wins over every guess ----
        dec = self.decisions.get(os.path.basename(folder))
        if dec:
            if dec.upper() == "GONE":
                return None, "marked-gone-by-you"
            if dec.upper() == "SKIP":
                return None, "skipped-by-you"
            if self.cache.names(dec) is None:
                return None, "your-folder-does-not-exist: " + dec
            found = finder(dec)
            if not found:
                return None, "your-folder-has-no-matching-file: " + dec
            path, note = self.choose(found, old_target)
            return (path, ("via-your-decision " + note).strip()) if path else (None, note)

        old_name = os.path.basename(folder)
        tried, cands, rejected = [], [], []
        if self.cache.names(folder) is not None:
            tried.append(folder)
            cands += finder(folder)
        weak_hits = []
        if not cands:
            strong, weak = self.index.lookup(old_name)
            for alt in strong:
                if alt in tried or self.cache.names(alt) is None:
                    continue
                why = conflicts(old_name, os.path.basename(alt), weak=False)
                if why:                       # e.g. two different films that share title+year
                    rejected.append("%s: %s" % (why, os.path.basename(alt)))
                    continue
                tried.append(alt)
                cands += finder(alt)
            if not cands:
                # weakest match: same title, no shared id. Opt-in, and still guarded - UNLESS the panel
                # itself knows the release year, which settles remake/revival questions with evidence.
                weak_ok, verified = [], []
                for alt in weak:
                    if alt in tried or self.cache.names(alt) is None:
                        continue
                    aname = os.path.basename(alt)
                    # with a panel year, the old folder's own year is irrelevant (it may have been wrong)
                    why = conflicts(old_name, aname, weak=(py is None))
                    if not why and py:
                        cy = folder_year(aname)
                        if cy and abs(cy - py) > 1:
                            why = "panel-says-%d-folder-is-%d" % (py, cy)
                        elif cy:
                            verified.append(alt)
                    if why:                   # different imdb/tmdb/tvdb id, or the years do not fit
                        rejected.append("%s: %s" % (why, aname))
                        continue
                    weak_ok.append(alt)
                if len(verified) == 1:
                    tried.append(verified[0])
                    found = finder(verified[0])
                    if found:
                        path, note = self.choose(found, old_target)
                        if not path:
                            return None, note
                        return path, ("via-panel-year(%d) %s" % (py, note)).strip()
                    weak_ok = []
                elif len(verified) > 1:
                    weak_ok = verified
                if len(weak_ok) > 1:
                    # e.g. '227' vs '22+7', or an original series and its revival. We cannot tell which
                    # one the old folder was, so never guess, whatever the episode numbers say.
                    return None, "several-look-alike-folders: " + " | ".join(
                        os.path.basename(x) for x in weak_ok[:3])
                if weak_ok:
                    tried.append(weak_ok[0])
                    weak_hits = finder(weak_ok[0])
                if weak_hits:
                    if not self.allow_title_only:
                        return None, "title-only-candidate (review): " + " | ".join(weak_hits[:3])
                    path, note = self.choose(weak_hits, old_target)
                    if not path:
                        return None, note
                    tag = "via-title-only" + ("" if folder_year(old_name) else "(old-name-has-no-year)")
                    return path, (tag + " " + note).strip()
        if not cands:
            if self.multi_rej:                # only a double-episode file exists for this episode
                return None, "multi-episode-file: " + os.path.basename(self.multi_rej[0])
            if rejected:                      # a look-alike exists but is provably a different title
                return None, "look-alike-rejected (%s)" % "; ".join(rejected[:2])
            # tell "folder is there but the file is not" apart from "folder is gone everywhere"
            if tried:
                return None, "folder-exists-but-no-matching-file"
            return None, "folder-missing-and-not-found-elsewhere"
        return self.choose(cands, old_target)


def title_of(old_target):
    """The title folder (movie folder, or show folder above the Season folder) of an old file path."""
    parts = old_target.split("/")
    if len(parts) > 2 and SEASON_RE.match(parts[-2]):
        return parts[-3]
    return parts[-2] if len(parts) > 1 else ""


def load_decisions(path):
    """worksheet (header: old_title_folder ... suggestion ... decision) or plain 2-column name<TAB>decision."""
    dec = {}
    if not path:
        return dec
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = [l.rstrip("\n") for l in f if l.strip() and not l.startswith("#")]
    if not lines:
        return dec
    head = lines[0].split("\t")
    if "old_title_folder" in head and "decision" in head:
        ci, di = head.index("old_title_folder"), head.index("decision")
        si = head.index("suggestion") if "suggestion" in head else -1
        for l in lines[1:]:
            c = l.split("\t")
            if len(c) <= max(ci, di):
                continue
            name, d = c[ci].strip(), c[di].strip()
            if not name or not d:
                continue
            if d.upper() == "OK":
                parts = c[si].split(" | ") if (si >= 0 and len(c) > si and c[si].strip()) else []
                if len(parts) != 1 or "[DIFFERENT?" in parts[0]:
                    print("  decision OK ignored for '%s': it needs exactly one clean suggestion - "
                          "paste the folder path instead" % name)
                    continue
                d = parts[0].strip()
            dec[name] = d
    else:
        for l in lines:
            c = l.split("\t")
            if len(c) >= 2 and c[0].strip() and c[1].strip():
                dec[c[0].strip()] = c[1].strip()
    return dec


def explain(note):
    """Machine reason -> a sentence a person can act on."""
    n = note or ""
    if n.startswith("marked-gone-by-you"):
        return "You marked this title as gone (ids are in gone_ids_*.txt for cleanup)"
    if n.startswith("skipped-by-you"):
        return "You told the tool to leave this title alone"
    if n.startswith("your-folder-does-not-exist"):
        return "The folder you gave for this title does not exist - check the path"
    if n.startswith("your-folder-has-no-matching-file"):
        return "The folder you gave has no file for this episode/movie"
    if n.startswith("folder-missing-and-not-found-elsewhere"):
        return "Title folder is gone from the drive (deleted, or renamed beyond recognition)"
    if n.startswith("folder-exists-but-no-matching-file"):
        return "Folder is there but this exact movie/episode file is not"
    if n.startswith("ambiguous-multi-part"):
        return "Movie is split into parts (CD1/CD2, Part 1/2) - pick by hand, the tool will not cut a film"
    if n.startswith("ambiguous"):
        return "Several possible replacement files - needs a human to pick one"
    if n.startswith("multi-episode-file"):
        return "Replaced by a double-episode file - this episode would start with the other one; check by hand"
    if n.startswith("several-look-alike-folders"):
        return "Several folders share this title (other years / a revival) - pick the right one by hand"
    if n.startswith("title-only-candidate"):
        return "Possible match found by title only - check it, then re-run with --allow-title-only"
    if n.startswith("look-alike-rejected"):
        return "Only a look-alike (other year / other IMDb id) exists - left alone on purpose"
    if n.startswith("episode-name-has-no-SxxExx"):
        return "Daily show or special with no season/episode number - fix by hand"
    if n.startswith("in --skip-ids"):
        return "You told the tool to skip this id"
    if n.startswith("io-error") or n.startswith("repoint-failed"):
        return "Read/write error on the drive or folder - re-run later"
    return n or "unknown"


def repoint(link, new_target):
    tmp = link + ".heal_tmp"
    try:
        os.unlink(tmp)
    except FileNotFoundError:
        pass
    os.symlink(new_target, tmp)
    os.replace(tmp, link)               # atomic swap: playback never sees a missing link


def do_undo(logfile):
    n = 0
    with open(logfile, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 4 or not parts[0].startswith("FIXED"):
                continue
            link, old = parts[1], parts[2]
            repoint(link, old)
            n += 1
    removed = 0
    with open(logfile, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 2 and parts[0] == "ADDED" and os.path.islink(parts[1]):
                os.unlink(parts[1])         # remove the extra <id>.<newext> link we created
                removed += 1
    print("restored %d links and removed %d added links using %s" % (n, removed, logfile))


def latest_attention(log_dir):
    fs = sorted(glob.glob(os.path.join(log_dir, "needs_attention_*.tsv")), key=os.path.getmtime)
    return fs[-1] if fs else ""


def read_attention(path):
    """needs_attention file -> list of [id, what, title, old_file, detail]."""
    rows = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        next(f, None)
        for line in f:
            c = line.rstrip("\n").split("\t")
            if len(c) >= 5:
                rows.append(c)
    return rows


def cmd_find_gone(a):
    """Read-only. For every title the tool called 'gone', look through the WHOLE drive (not just the
    folders the repair looks in) and say whether it is really gone or just somewhere else."""
    f = latest_attention(a.log_dir)
    if not f:
        print("I could not find a report to work from in %s." % a.log_dir)
        print("Run the normal dry run first (the one that prints the SUMMARY), then run this again.")
        try:
            print("That folder currently contains: %s" % (", ".join(sorted(os.listdir(a.log_dir))[:8]) or "(nothing)"))
        except OSError:
            print("(that folder does not exist yet)")
        return 1
    gone = collections.OrderedDict()
    for r in read_attention(f):
        if r[4].startswith("folder-missing"):
            g = gone.setdefault(r[2], {"links": 0, "ex": r[0]})
            g["links"] += 1
    print("Using report: %s" % f)
    if not gone:
        print("Nothing in the 'title folder is gone' group, so there is nothing to look for.")
        return 0
    root = a.search_root
    try:
        okroot = os.path.isdir(root) and len(os.listdir(root)) > 0
    except OSError:
        okroot = False
    if not okroot:
        print("STOPPED: %s is missing or empty (is the drive mounted?)." % root)
        return 3
    print("Looking through every folder on the drive under %s (down to %d levels)." % (root, a.search_depth))
    print("This only READS folder names. It does not open or download any video, so it does not use")
    print("your Google download quota. It can take a few minutes the first time.")

    by_tag, by_tk, n_dirs = collections.defaultdict(list), collections.defaultdict(list), 0
    level = [root]
    for depth in range(a.search_depth):
        nxt = []
        for p in level:
            try:
                ents = list(os.scandir(p))
            except OSError:
                continue
            for e in ents:
                try:
                    if not e.is_dir(follow_symlinks=False):
                        continue
                except OSError:
                    continue
                nxt.append(e.path)
                if SEASON_RE.match(e.name):
                    continue
                tk = title_key(e.name)
                if not tk:
                    continue
                n_dirs += 1
                for t in tag_keys(e.name):
                    by_tag[t].append(e.path)
                by_tk[tk].append(e.path)
                if n_dirs % 20000 == 0:
                    print("  ...looked through %d folders" % n_dirs)
        level = nxt
    print("Done: %d title-like folders on the drive.\n" % n_dirs)

    rel = lambda p: p.replace(root.rstrip("/") + "/", "")
    result = collections.OrderedDict()           # title -> (status, [paths])
    tk_list = list(by_tk.keys())
    for name in gone:
        tags, tk = tag_keys(name), title_key(name)
        byid = []
        for t in tags:
            for p in by_tag.get(t, []):
                if p not in byid:
                    byid.append(p)
        if byid:
            result[name] = ("FOUND-ID", byid)
            continue
        same = [p for p in by_tk.get(tk, []) if not conflicts(name, os.path.basename(p), weak=True)]
        if len(same) == 1:
            result[name] = ("FOUND-TITLE", same)
            continue
        if len(same) > 1:
            result[name] = ("SEVERAL", same)
            continue
        similar = []
        if len(tk) >= 6:
            for k in tk_list:
                if k != tk and len(k) >= 6 and (tk in k or k in tk):
                    for p in by_tk[k]:
                        if not conflicts(name, os.path.basename(p), weak=True):
                            similar.append(p)
                if len(similar) >= 3:
                    break
        result[name] = ("SIMILAR", similar) if similar else ("NOT-FOUND", [])

    labels = [("FOUND-ID", "FOUND, same IMDb/TVDB id (safe to repair)"),
              ("FOUND-TITLE", "FOUND, same title, one folder"),
              ("SEVERAL", "SEVERAL folders with this title"),
              ("SIMILAR", "SIMILAR name only (probably a different spelling)"),
              ("NOT-FOUND", "NOT FOUND anywhere - really gone")]
    total_t, total_l = len(gone), sum(g["links"] for g in gone.values())
    print("=" * 70)
    print("ARE THE 'GONE' TITLES REALLY GONE?   (%d titles, %d links)" % (total_t, total_l))
    print("=" * 70)
    for key, text in labels:
        ts = [n for n, v in result.items() if v[0] == key]
        print("%-52s %5d titles %6d links" % (text, len(ts), sum(gone[n]["links"] for n in ts)))
    print("-" * 70)
    for key, text in labels[:4]:
        ts = sorted([n for n, v in result.items() if v[0] == key], key=lambda n: -gone[n]["links"])[:12]
        if ts:
            print("\n%s (biggest first):" % text)
            for n in ts:
                print("  %5d  %s\n         -> %s" % (gone[n]["links"], n, " | ".join(rel(p) for p in result[n][1][:2])))
    nf = sorted([n for n, v in result.items() if v[0] == "NOT-FOUND"], key=lambda n: -gone[n]["links"])[:12]
    if nf:
        print("\nReally gone (biggest first):")
        for n in nf:
            print("  %5d  %s" % (gone[n]["links"], n))

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    check = os.path.join(a.log_dir, "gone_check_%s.tsv" % stamp)
    dec = os.path.join(a.log_dir, "found_decisions_%s.tsv" % stamp)
    with open(check, "w", encoding="utf-8") as fh:
        fh.write("links\tstatus\told_title_folder\tfound_at\n")
        for n, (st, ps) in result.items():
            fh.write("%d\t%s\t%s\t%s\n" % (gone[n]["links"], st, n, " | ".join(ps[:3])))
    n_auto = 0
    with open(dec, "w", encoding="utf-8") as fh:
        fh.write("links\twhy\told_title_folder\tsuggestion\tdecision\texample_id\n")
        for n, (st, ps) in sorted(result.items(), key=lambda kv: -gone[kv[0]]["links"]):
            d = ""
            if st == "FOUND-ID" and len(ps) == 1:
                d = ps[0]                      # same IMDb/TVDB id, one folder: the safe case
                n_auto += 1
            fh.write("%d\t%s\t%s\t%s\t%s\t%s\n" % (gone[n]["links"], st, n, " | ".join(ps[:3]), d, gone[n]["ex"]))
    print("\nFiles written to %s:" % a.log_dir)
    print("  %s   <- the full list, one line per title" % os.path.basename(check))
    print("  %s <- ready to use: %d titles already filled in (same IMDb/TVDB id)" % (os.path.basename(dec), n_auto))
    print("\nNEXT: repair those %d titles with:" % n_auto)
    print("  sudo -u xtreamcodes python3 %s --decisions %s" % (os.path.abspath(sys.argv[0]), dec))
    print("(that is still a dry run - add --apply only after you have looked at the summary)")
    return 0


def cmd_peek(a):
    """Read-only. Shows a few real examples of the groups that need a human look, in plain words."""
    f = latest_attention(a.log_dir)
    if not f:
        print("No report found in %s. Run the normal dry run first." % a.log_dir)
        return 1
    rows = read_attention(f)
    random.seed(7)
    short = lambda p: p.replace("/mnt/unionfs/Media/", "")

    def pick(prefix, n, title):
        sel = [r for r in rows if r[4].startswith(prefix)]
        print("\n" + "#" * 72 + "\n# %s: %d links\n" % (title, len(sel)) + "#" * 72)
        return random.sample(sel, min(n, len(sel)))

    for r in pick("folder-exists-but-no-matching-file", 12, "THE FOLDER IS THERE BUT THIS FILE IS NOT"):
        d = os.path.dirname(r[3])
        print("\nWAS   ", short(r[3]))
        try:
            names = sorted(os.listdir(d))
        except OSError:
            names = ["(folder not readable)"]
        print("NOW THAT FOLDER HAS %d files, for example:" % len(names))
        for n in names[:8]:
            print("      ", n)
    for r in pick("ambiguous", 10, "SEVERAL VERSIONS TO CHOOSE FROM"):
        print("\nWAS   ", short(r[3]))
        for c in r[4].split(":", 1)[1].split(" | "):
            try:
                sz = "%.1f GB" % (os.path.getsize(c) / 1e9)
            except OSError:
                sz = "?"
            print("   -", sz, short(c).rsplit("/", 1)[-1])
    for r in pick("multi-episode-file", 8, "REPLACED BY A DOUBLE-EPISODE FILE"):
        print("\nWAS   ", short(r[3]).rsplit("/", 1)[-1])
        print("NOW   ", r[4].split(": ", 1)[1])
    return 0


def pick_trial(plans, n):
    """Choose a small, VARIED set of repairs to try first: episodes, movies, file-type changes, moved
    folders, panel-year and best-quality picks. Returns (chosen_plans, info_rows)."""
    def kinds(pl):
        k = []
        base = os.path.basename(pl["old"])
        k.append("episode" if first_episode(base) is not None else ("daily-show" if air_date(base) else "movie"))
        if pl["link_ext"] != pl["new_ext"]:
            k.append("file-type-change")
        if os.path.dirname(pl["old"]) != os.path.dirname(pl["new"]):
            k.append("moved-folder")
        if "via-panel-year" in pl["note"]:
            k.append("panel-year")
        if "best-quality" in pl["note"]:
            k.append("best-quality")
        return k
    rnd = random.Random(2026)      # fixed seed + sorted input: the dry run and the real run pick the SAME links
    plans = sorted(plans, key=lambda x: x["link"])
    buckets = collections.OrderedDict((k, []) for k in
                                      ("movie", "episode", "file-type-change", "moved-folder", "panel-year",
                                       "best-quality", "daily-show"))
    tagged = {}
    for pl in plans:
        ks = kinds(pl)
        tagged[id(pl)] = ks
        for k in ks:
            buckets[k].append(pl)
    for b in buckets.values():
        rnd.shuffle(b)
    chosen, seen = [], set()
    while len(chosen) < n and any(buckets.values()):
        for k, b in buckets.items():
            while b and id(b[-1]) in seen:
                b.pop()
            if b and len(chosen) < n:
                pl = b.pop()
                seen.add(id(pl))
                chosen.append((k, pl))
    info = []
    for k, pl in chosen:
        info.append((k, pl["id"], title_of(pl["old"]), os.path.basename(pl["old"]), os.path.basename(pl["new"]),
                     "+".join(tagged[id(pl)])))
    return [pl for _, pl in chosen], info


def main():
    ap = argparse.ArgumentParser(description="Repair VOD symlinks broken by Radarr/Sonarr upgrades.")
    ap.add_argument("--version", action="version", version="vod_heal " + VERSION)
    ap.add_argument("--find-gone", action="store_true",
                    help="READ-ONLY check: are the titles reported as 'gone' really gone, or just somewhere else on the drive?")
    ap.add_argument("--peek", action="store_true",
                    help="READ-ONLY: show a few real examples of the groups that need a human look")
    ap.add_argument("--search-root", default="/mnt/unionfs", help="where --find-gone looks (default /mnt/unionfs)")
    ap.add_argument("--search-depth", type=int, default=6, help="how many folder levels --find-gone goes down")
    ap.add_argument("--movies-dir", default="/home/xtreamcodes/iptv_xtream_codes/movies")
    ap.add_argument("--media-root", action="append", default=None,
                    help="rclone media root to search (repeatable). Default /mnt/unionfs/Media")
    ap.add_argument("--index-depth", type=int, default=3,
                    help="folder depth under the media root where title folders live (default 3)")
    ap.add_argument("--apply", action="store_true", help="actually repoint links (default: dry run)")
    ap.add_argument("--pick-largest", action="store_true", help=argparse.SUPPRESS)   # now the default
    ap.add_argument("--no-auto-pick", action="store_true",
                    help="when several versions of one movie/episode exist (1080p, 2160p...), do NOT pick the "
                         "best-quality one automatically; list them for you instead")
    ap.add_argument("--panel-info", metavar="FILE",
                    help="optional 'stream_id<TAB>release_year' export from the panel DB. With it, a title-only "
                         "match is accepted automatically when the year fits, and refused when it does not "
                         "(remakes, revivals). See the SQL in the instructions.")
    ap.add_argument("--decisions", metavar="WORKSHEET",
                    help="the worksheet_*.tsv you filled in. In its 'decision' column put: a folder path "
                         "(look for the files there), OK (accept the one clean suggestion), GONE (deleted "
                         "for good; listed in gone_ids_*.txt for later cleanup) or SKIP (leave alone)")
    ap.add_argument("--trial", type=int, metavar="N",
                    help="repair only N varied links first (a mix of movies, episodes, file-type changes, moved "
                         "folders...), so you can play them before doing the rest. Without --apply it just shows "
                         "which N it would pick")
    ap.add_argument("--only-ids", metavar="FILE_OR_LIST",
                    help="repair only these stream ids (a file, or comma-separated)")
    ap.add_argument("--skip-ids", metavar="FILE_OR_LIST",
                    help="ids the tool must never touch: a file, or a comma-separated list "
                         "(use for any pairing you rejected on review)")
    ap.add_argument("--allow-title-only", action="store_true",
                    help="also accept a folder that matches by title alone (no shared id/year). "
                         "Off by default: a remake with the same name could be paired with the wrong show")
    ap.add_argument("--skip-ext-change", action="store_true",
                    help="leave links alone when the replacement file has a different extension "
                         "(e.g. .avi -> .mkv); they are listed for manual handling")
    ap.add_argument("--add-ext-link", action="store_true", help=argparse.SUPPRESS)  # now the default
    ap.add_argument("--no-ext-link", action="store_true",
                    help="when the extension differs (e.g. .avi -> .mkv) do NOT also create <id>.<newext> "
                         "and the ext_updates_*.sql file (the old-name link is still repointed)")
    ap.add_argument("--max-broken-pct", type=float, default=10.0,
                    help="refuse to apply if more than this %% of links look broken (dead-mount guard)")
    ap.add_argument("--force", action="store_true", help="override the dead-mount guard")
    ap.add_argument("--limit", type=int, default=0, help="stop after this many links (testing)")
    ap.add_argument("--log-dir", default="/home/xtreamcodes/iptv_xtream_codes/logs/vod_heal")
    ap.add_argument("--undo", metavar="LOGFILE", help="restore links changed by a previous --apply run")
    a = ap.parse_args()
    a.add_ext_link = not a.no_ext_link

    if a.undo:
        do_undo(a.undo)
        return 0
    if a.find_gone:
        return cmd_find_gone(a)
    if a.peek:
        return cmd_peek(a)

    roots = a.media_root or ["/mnt/unionfs/Media"]
    try:
        os.makedirs(a.log_dir, exist_ok=True)
    except OSError as e:
        print("cannot create log dir %s: %s" % (a.log_dir, e))
        return 1

    lock = open(os.path.join(a.log_dir, ".lock"), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("another vod_heal run is in progress; exiting")
        return 0

    t0 = time.time()
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    # --- mount sanity: a dead/empty mount makes EVERY link look broken ---
    for r in roots:
        try:
            ok = os.path.isdir(r) and len(os.listdir(r)) > 0
        except OSError:
            ok = False
        if not ok:
            print("ABORT: media root %s is missing or empty (mount down?). Nothing was changed." % r)
            return 3

    if not os.path.isdir(a.movies_dir):
        print("ABORT: movies dir %s not found (run this on the LB)." % a.movies_dir)
        return 3

    # --- 1) scan ---
    decisions = {}
    if a.decisions:
        try:
            decisions = load_decisions(a.decisions)
        except OSError as e:
            print("cannot read --decisions file: %s" % e)
            return 1
        print("decisions loaded from your worksheet: %d titles" % len(decisions))
    panel_year = {}
    if a.panel_info:
        try:
            with open(a.panel_info, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    c = line.strip().split("\t")
                    if len(c) >= 2 and c[0].isdigit():
                        m = re.match(r"^(\d{4})", c[1].strip().strip('"'))
                        if m and 1880 <= int(m.group(1)) <= 2100:
                            panel_year[c[0]] = int(m.group(1))
        except OSError as e:
            print("cannot read --panel-info file: %s" % e)
            return 1
        print("panel release years loaded for %d titles" % len(panel_year))
    healer = Healer(roots, a.index_depth, not a.no_auto_pick, a.allow_title_only, decisions, panel_year)
    total = ok_count = 0
    broken = []
    healthy = {}          # link -> target for links that work now; re-checked after --apply
    io_errors = 0
    for e in os.scandir(a.movies_dir):
        try:
            if not e.is_symlink():
                continue
            total += 1
            target = os.readlink(e.path)
            if not os.path.isabs(target):
                target = os.path.normpath(os.path.join(a.movies_dir, target))
            if healer.target_exists(target):
                ok_count += 1
                healthy[e.path] = target
            else:
                broken.append((e.path, target))
        except OSError:
            io_errors += 1
        if total and total % 50000 == 0:
            print("  scanned %d links..." % total)
        if a.limit and total >= a.limit:
            break

    pct = (100.0 * len(broken) / total) if total else 0.0
    if io_errors:
        print("read errors: %d links could not be read (skipped, not counted as broken)" % io_errors)

    if a.apply and not a.force and (pct > a.max_broken_pct or io_errors > max(50, total // 100)):
        print("")
        print("STOPPED, nothing was changed: %.1f%% of links look broken (limit %.0f%%)." % (pct, a.max_broken_pct))
        print("A sudden jump usually means the rclone mount is unhealthy, not that thousands of files")
        print("were upgraded. If this is your FIRST run on a library with a big backlog and the dry-run")
        print("list looked right, run again with:  --max-broken-pct 40")
        return 2

    # --- 2) resolve (and optionally apply) ---
    rows, fixed, unresolved, ext_mismatch, skipped_ext = [], 0, 0, 0, 0
    ext_ids = {}            # new extension -> [stream ids] for the target_container SQL
    skip = set()
    if a.skip_ids:
        raw = open(a.skip_ids).read() if os.path.isfile(a.skip_ids) else a.skip_ids
        skip = set(re.findall(r"\d+", raw))
    only = set()
    if a.only_ids:
        raw = open(a.only_ids).read() if os.path.isfile(a.only_ids) else a.only_ids
        only = set(re.findall(r"\d+", raw))
    plans = []
    for link, old in broken:
        name = os.path.basename(link)
        mid = re.match(r"^(\d+)\.", name)
        if mid and mid.group(1) in skip:
            rows.append(("SKIPPED_ID", link, old, "", "in --skip-ids"))
            continue
        try:
            new, note = healer.resolve(old, mid.group(1) if mid else None)
        except OSError as ex:
            rows.append(("ERROR", link, old, "", "io-error: %s" % ex))
            unresolved += 1
            continue
        if new is None:
            rows.append(("UNRESOLVED", link, old, "", note))
            unresolved += 1
            continue
        plans.append({"link": link, "old": old, "new": new, "note": note, "name": name,
                      "id": mid.group(1) if mid else "",
                      "link_ext": os.path.splitext(name)[1].lower(),
                      "new_ext": os.path.splitext(new)[1].lower()})

    # ---- which repairs to do now: all (default), only the listed ids, or a small varied trial ----
    chosen = [p for p in plans if p["id"] in only] if only else plans
    trial_info = []
    if a.trial:
        chosen, trial_info = pick_trial(chosen, a.trial)
    held = len(plans) - len(chosen)

    for p_ in chosen:
        link, old, new, note, name = p_["link"], p_["old"], p_["new"], p_["note"], p_["name"]
        flag = ""
        ext_differs = p_["link_ext"] != p_["new_ext"]
        new_ext = p_["new_ext"]
        if ext_differs:
            flag = "EXT_MISMATCH(link %s, file %s)" % (p_["link_ext"], new_ext)
            ext_mismatch += 1
            if a.skip_ext_change:
                rows.append(("SKIPPED_EXT", link, old, new, flag))
                skipped_ext += 1
                continue
        status = "FIXED" if a.apply else "WOULD_FIX"
        if a.apply:
            try:
                repoint(link, new)
            except OSError as ex:
                rows.append(("ERROR", link, old, new, "repoint-failed: %s" % ex))
                unresolved += 1
                continue
        fixed += 1
        rows.append((status, link, old, new, " ".join(x for x in (note, flag) if x)))
        if ext_differs and a.add_ext_link:
            m_id = re.match(r"^(\d+)\.", name)
            if m_id:
                extra = os.path.join(os.path.dirname(link), m_id.group(1) + new_ext)
                if os.path.lexists(extra) and not os.path.islink(extra):
                    rows.append(("ERROR", extra, "", new, "not-a-symlink-so-not-replaced"))
                else:
                    if a.apply:
                        try:
                            repoint(extra, new)
                        except OSError as ex:
                            rows.append(("ERROR", extra, "", new, "add-link-failed: %s" % ex))
                            continue
                    rows.append(("ADDED" if a.apply else "WOULD_ADD", extra, "", new, ""))
                    ext_ids.setdefault(new_ext.lstrip("."), []).append(m_id.group(1))
    # --- 3) reports ---
    tsv = os.path.join(a.log_dir, "heal_%s.tsv" % stamp)
    with open(tsv, "w", encoding="utf-8") as f:
        for r in rows:
            f.write("\t".join(r) + "\n")
    ids = []
    for r in rows:
        if r[0] in ("UNRESOLVED", "ERROR"):
            m = re.match(r"^(\d+)\.", os.path.basename(r[1]))
            if m:
                ids.append(m.group(1))
    idfile = os.path.join(a.log_dir, "unresolved_ids_%s.txt" % stamp)
    with open(idfile, "w") as f:
        f.write(",".join(ids) + "\n")

    sqlfile = ""
    if ext_ids:
        sqlfile = os.path.join(a.log_dir, "ext_updates_%s.sql" % stamp)
        with open(sqlfile, "w") as f:
            f.write("-- Run on the PANEL DATABASE that owns these stream ids (not on the LB).\n")
            f.write("-- Makes streams.target_container match the new file extension.\n")
            for ext, idl in sorted(ext_ids.items()):
                for i in range(0, len(idl), 1000):
                    chunk = idl[i:i + 1000]
                    f.write("UPDATE `streams` SET `target_container` = '[\"%s\"]' WHERE `id` IN (%s);\n"
                            % (ext, ",".join(chunk)))

    # ---- the "needs your attention" list, in plain English ----
    attn = [r for r in rows if r[0] in ("UNRESOLVED", "ERROR", "SKIPPED_ID", "SKIPPED_EXT")]
    reasons = collections.Counter(explain(r[4]) for r in attn)
    attn_file = os.path.join(a.log_dir, "needs_attention_%s.tsv" % stamp)
    with open(attn_file, "w", encoding="utf-8") as f:
        f.write("id\twhat_happened\ttitle_folder\told_file\tdetail\n")
        for r in sorted(attn, key=lambda r: (explain(r[4]), r[2])):
            mid = re.match(r"^(\d+)\.", os.path.basename(r[1]))
            old_parts = r[2].split("/")
            folder = old_parts[-3] if len(old_parts) > 2 and SEASON_RE.match(old_parts[-2]) else (
                old_parts[-2] if len(old_parts) > 1 else "")
            f.write("%s\t%s\t%s\t%s\t%s\n" % (mid.group(1) if mid else "", explain(r[4]), folder,
                                              r[2], r[4]))

    # ---- worksheet: one row per TITLE (not per link), biggest first, with suggestions to confirm ----
    ws_file, gone_file, n_ws = "", "", 0
    titles = {}
    for r in attn:
        n = r[4]
        if r[0] == "SKIPPED_ID" or n.startswith(("marked-gone-by-you", "skipped-by-you")):
            continue
        t = titles.setdefault(title_of(r[2]), {"links": 0, "why": collections.Counter(), "ex": ""})
        t["links"] += 1
        t["why"][explain(n)] += 1
        mid = re.match(r"^(\d+)\.", os.path.basename(r[1]))
        if mid and not t["ex"]:
            t["ex"] = mid.group(1)
    if titles:
        ws_file = os.path.join(a.log_dir, "worksheet_%s.tsv" % stamp)
        with open(ws_file, "w", encoding="utf-8") as f:
            f.write("links\twhy\told_title_folder\tsuggestion\tdecision\texample_id\n")
            for name, t in sorted(titles.items(), key=lambda kv: -kv[1]["links"]):
                try:
                    sug = " | ".join(p + ("  [DIFFERENT? %s]" % why if why else "")
                                     for p, why in healer.suggest(name))
                except OSError:
                    sug = ""
                f.write("%d\t%s\t%s\t%s\t\t%s\n" % (t["links"], t["why"].most_common(1)[0][0], name, sug, t["ex"]))
                n_ws += 1
    gone_ids = []
    for r in rows:
        if r[0] == "UNRESOLVED" and r[4].startswith("marked-gone-by-you"):
            mid = re.match(r"^(\d+)\.", os.path.basename(r[1]))
            if mid:
                gone_ids.append(mid.group(1))
    if gone_ids:
        gone_file = os.path.join(a.log_dir, "gone_ids_%s.txt" % stamp)
        with open(gone_file, "w") as f:
            f.write(",".join(gone_ids) + "\n")

    # ---- after --apply: prove nothing healthy was touched and every repair resolves ----
    check_line = ""
    if a.apply:
        changed = vanished = 0
        for p, t in healthy.items():
            try:
                if os.readlink(p) != t:
                    changed += 1
            except OSError:
                vanished += 1
        not_resolving = 0
        for r in rows:
            if r[0] == "FIXED":
                try:
                    os.stat(r[1])            # follows the link; metadata only, reads no file data
                except OSError:
                    not_resolving += 1
        if changed == 0 and vanished == 0 and not_resolving == 0:
            check_line = ("SELF-CHECK PASS: all %d working links are untouched, and all %d repaired "
                          "links now resolve." % (len(healthy), fixed))
        else:
            check_line = ("SELF-CHECK FAIL: %d working links changed, %d disappeared, %d repaired links do "
                          "not resolve. UNDO NOW:  python3 %s --undo %s"
                          % (changed, vanished, not_resolving, os.path.abspath(sys.argv[0]), tsv))

    W = 66
    print("")
    print("=" * W)
    print("VOD HEAL SUMMARY  " + ("(DRY RUN - nothing was changed)" if not a.apply else "(APPLIED)"))
    print("script version: " + VERSION)
    print("=" * W)
    print("All VOD links ................ %d" % total)
    print("  Working (never touched) .... %d" % ok_count)
    print("  Broken ..................... %d  (%.1f%%)" % (len(broken), pct))
    if a.apply:
        print("     REPAIRED ................ %d" % fixed)
    else:
        print("     CAN BE REPAIRED ......... %d   <- run again with --apply" % fixed)
    if held:
        print("     HELD BACK FOR LATER ..... %d   (not part of this %s; still broken, untouched)"
              % (held, "trial" if a.trial else "selection"))
    print("     NEEDS YOUR ATTENTION .... %d" % len(attn))
    for k, v in reasons.most_common():
        print("          %6d  %s" % (v, k))
    if ext_mismatch and not a.skip_ext_change:
        print("  (%d of the repairs change the file type, e.g. .avi -> .mkv; handled automatically)" % ext_mismatch)
    print("-" * W)
    if check_line:
        print(check_line)
    print("Files in %s:" % a.log_dir)
    if ws_file:
        print("  worksheet_%s.tsv         <- %d titles. Fill the 'decision' column, then re-run with" % (stamp, n_ws))
        print("                              --decisions <this file>   (path / OK / GONE / SKIP)")
    if gone_file:
        print("  gone_ids_%s.txt          <- %d links you marked gone, for later cleanup" % (stamp, len(gone_ids)))
    print("  needs_attention_%s.tsv   <- open this one: id, why, title, old file" % stamp)
    print("  heal_%s.tsv              <- every link and what happened (also used for --undo)" % stamp)
    if sqlfile:
        print("  %s  <- run on the PANEL database after applying" % os.path.basename(sqlfile))
    if trial_info:
        trial_file = os.path.join(a.log_dir, "trial_%s.tsv" % stamp)
        with open(trial_file, "w", encoding="utf-8") as fh:
            fh.write("kind\tid\ttitle\told_file\tnew_file\ttags\n")
            for t in trial_info:
                fh.write("\t".join(t) + "\n")
        print("")
        print("TRIAL: %s these %d links (a mix of kinds, so each type of repair gets tested):"
              % ("repaired" if a.apply else "would repair", len(trial_info)))
        for k, i, title, oldn, newn, tags in trial_info:
            print("  id %-8s [%s]  %s" % (i, k, title))
            print("      was: %s" % oldn[:100])
            print("      now: %s" % newn[:100])
        print("")
        print("To see the names in your panel, run this on the main database server:")
        print("  SELECT id, stream_display_name FROM streams WHERE id IN (%s);" % ",".join(t[1] for t in trial_info))
        print("Play these in the panel / your app. If they are fine, run the same command again WITHOUT")
        print("--trial to repair the rest. If not, undo with:  python3 %s --undo %s" % (os.path.abspath(sys.argv[0]), tsv))
    print("Took %.0fs." % (time.time() - t0))

    # keep 30 days of logs
    cutoff = time.time() - 30 * 86400
    for fn in os.listdir(a.log_dir):
        if fn.startswith(("heal_", "unresolved_ids_", "needs_attention_", "ext_updates_", "report_",
                          "worksheet_", "gone_ids_")):
            p = os.path.join(a.log_dir, fn)
            try:
                if os.path.getmtime(p) < cutoff:
                    os.unlink(p)
            except OSError:
                pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
