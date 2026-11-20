#!/usr/bin/env python3
"""
series_dedupe.py - merge duplicate SERIES rows in an Xtream-UI panel.
Run on the MAIN panel server (the one with the MySQL database), as root.

PROBLEM
  One show ends up as many rows in the `series` table (same tmdb_id, 1 episode each).
  Deleting duplicate episode names cannot fix that: the episodes are already unique
  ("Show - S01E01 - Title"); it is the SERIES rows that are duplicated.

WHAT THIS DOES (per duplicate group, in ONE transaction)
  1. Group series by tmdb_id (when > 0). When tmdb_id is empty/0: by exact title
     (trimmed, case-insensitive) AND the same release year. No year and no tmdb_id
     = ambiguous, skipped. Different tmdb_ids are NEVER merged.
  2. Keeper = the series with the most real episodes (lowest id on a tie).
  3. Moves all series_episodes of the other rows to the keeper.
  4. If the same (season, episode number) now exists more than once (sort > 0 only),
     keeps the newest stream and deletes the older copies (series_episodes + streams
     + streams_sys). Episodes with sort 0 are never collapsed.
  5. Deletes the now-empty duplicate series rows.
  6. Rewrites bouquets.bouquet_series: removed ids -> keeper id, no repeats, same order.
  --orphans also removes series_episodes / streams_sys rows that point to streams
  that no longer exist, and REPORTS (never deletes) episode streams with no series.

SAFETY
  * Default is a DRY RUN. Nothing changes without --apply.
  * --apply first writes a mysqldump backup (.sql) and aborts if that fails.
    Restore: mysql <db> < the_backup.sql   (rows are written back with REPLACE).
  * One transaction per group; any error rolls that group back.
  * A stream is only deleted when it is type 5 (episode) and no remaining
    series_episodes row uses it.

USAGE
  python3 series_dedupe.py                         # dry run
  python3 series_dedupe.py --series-id 1007902     # dry run, one show
  python3 series_dedupe.py --series-id 1007902 --apply
  python3 series_dedupe.py --apply                 # everything
  python3 series_dedupe.py --orphans [--apply]     # also clean orphan rows
  Needs: apt install -y python3-pymysql
"""
import argparse
import base64
import collections
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

VERSION = "2026-11-17-A"
CONFIG_CRYPT_KEY = "5709650b0d7806074842c6de575025b1"
CONFIG_FILE = "/home/xtreamcodes/iptv_xtream_codes/config"
FILL_FIELDS = ("cover", "cover_big", "genre", "plot", "cast", "director",
               "releaseDate", "youtube_trailer", "backdrop_path", "seasons")
EMPTY_VALUES = ("", "[]", "{}", "null", "NULL")


# ---------------------------------------------------------------------------
# Panel config reader + DB helper (same logic as vod_heal.py)
# ---------------------------------------------------------------------------
def _xor_parse(data, key):
    kb = key.encode()
    return bytes(data[i] ^ kb[i % len(kb)] for i in range(len(data)))


def read_panel_config(config_path=CONFIG_FILE):
    raw = base64.b64decode(open(config_path, "rb").read().strip())
    return json.loads(_xor_parse(raw, CONFIG_CRYPT_KEY).decode("utf-8"))


def db_connect(cfg=None, config_path=CONFIG_FILE):
    try:
        import pymysql
    except ImportError:
        return None, None, "pymysql not installed (run as root: apt install -y python3-pymysql)"
    if cfg is None:
        try:
            cfg = read_panel_config(config_path)
        except Exception as e:
            return None, None, "cannot read panel config %s: %s" % (config_path, e)
    try:
        conn = pymysql.connect(
            host=cfg["host"], port=int(cfg.get("db_port", 3306)),
            user=cfg["db_user"], password=cfg["db_pass"],
            database=cfg["db_name"], charset="utf8mb4",
            connect_timeout=10, read_timeout=300, write_timeout=300,
            autocommit=False,
        )
        return conn, cfg, None
    except Exception as e:
        return None, None, "DB connect failed: %s" % e


# ---------------------------------------------------------------------------
# Pure logic (no database access; unit-testable)
# ---------------------------------------------------------------------------
def norm_title(t):
    return (t or "").strip().casefold()


def release_year(s):
    m = re.match(r"\s*(\d{4})", str(s or ""))
    return m.group(1) if m else ""


def group_series(rows):
    """rows: dicts with id, title, tmdb_id, releaseDate.
    Returns (groups, skipped_ambiguous). groups: list of sorted id lists (len >= 2)."""
    by_tmdb = collections.defaultdict(list)
    by_title = collections.defaultdict(list)
    skipped = 0
    for r in rows:
        tm = int(r.get("tmdb_id") or 0)
        if tm > 0:
            by_tmdb[tm].append(int(r["id"]))
            continue
        t = norm_title(r.get("title"))
        y = release_year(r.get("releaseDate"))
        if not t or not y:
            skipped += 1
            continue
        by_title[(t, y)].append(int(r["id"]))
    groups = [sorted(v) for v in list(by_tmdb.values()) + list(by_title.values()) if len(v) > 1]
    groups.sort(key=lambda g: g[0])
    return groups, skipped


def choose_keeper(ids, ep_counts):
    """Most (real) episodes wins; lowest id on a tie."""
    return sorted(ids, key=lambda i: (-ep_counts.get(i, 0), i))[0]


def plan_merge(keeper, group_ids, se_rows, streams):
    """se_rows: dicts id, season_num, series_id, stream_id, sort for every series in the group.
    streams: {stream_id: type} for streams that EXIST.
    Returns dict: move_ids (se ids to repoint), delete_se (se ids), delete_streams (stream ids
    candidates, type 5 only), conflicts [(season, sort, kept_se, [lost_se])], remove_series."""
    slots = collections.defaultdict(list)
    for r in se_rows:
        if int(r["sort"] or 0) > 0:
            slots[(int(r["season_num"]), int(r["sort"]))].append(r)
    delete_se = []
    conflicts = []
    for slot, lst in sorted(slots.items()):
        if len(lst) < 2:
            continue
        lst = sorted(lst, key=lambda r: (int(r["stream_id"]) in streams, int(r["stream_id"]), int(r["id"])))
        win = lst[-1]
        lost = lst[:-1]
        delete_se.extend(int(r["id"]) for r in lost)
        conflicts.append((slot[0], slot[1], int(win["id"]), [int(r["id"]) for r in lost]))
    gone = set(delete_se)
    kept_streams = set(int(r["stream_id"]) for r in se_rows if int(r["id"]) not in gone)
    delete_streams = sorted(set(
        int(r["stream_id"]) for r in se_rows
        if int(r["id"]) in gone and int(r["stream_id"]) in streams
        and streams[int(r["stream_id"])] == 5 and int(r["stream_id"]) not in kept_streams))
    move_ids = [int(r["id"]) for r in se_rows
                if int(r["series_id"]) != keeper and int(r["id"]) not in gone]
    return {"move_ids": move_ids, "delete_se": delete_se, "delete_streams": delete_streams,
            "conflicts": conflicts, "remove_series": [i for i in group_ids if i != keeper]}


def rewrite_bouquet(text, group_ids, keeper):
    """Return (new_text, changed). Removed ids -> keeper at first occurrence, no repeats, order kept,
    element type (int/string) of the first replaced entry is kept. Invalid JSON raises ValueError."""
    arr = json.loads(text)
    if not isinstance(arr, list):
        raise ValueError("bouquet_series is not a JSON list")
    members = set(group_ids)
    out, seen, changed = [], set(), False
    for el in arr:
        try:
            v = int(el)
        except (TypeError, ValueError):
            out.append(el)
            continue
        if v in members:
            if keeper in seen:
                changed = True
                continue
            seen.add(keeper)
            new = str(keeper) if isinstance(el, str) else keeper
            if v != keeper or new != el:
                changed = True
            out.append(new)
        else:
            if v in seen:
                changed = True
                continue
            seen.add(v)
            out.append(el)
    return json.dumps(out, separators=(",", ":")), changed


def blank(v):
    return v is None or str(v).strip() in EMPTY_VALUES


def fill_updates(keeper_row, donors):
    """Fields that are blank on the keeper and filled on the first donor that has them."""
    upd = {}
    for f in FILL_FIELDS:
        if f in keeper_row and blank(keeper_row[f]):
            for d in donors:
                if f in d and not blank(d[f]):
                    upd[f] = d[f]
                    break
    return upd


# ---------------------------------------------------------------------------
# Database reads
# ---------------------------------------------------------------------------
def q(conn, sql, args=None):
    import pymysql.cursors
    with conn.cursor(pymysql.cursors.DictCursor) as c:
        c.execute(sql, args)
        return list(c.fetchall())


def in_list(ids):
    return ",".join(str(int(i)) for i in ids) or "NULL"


def fetch_series(conn):
    cols = [r["Field"] for r in q(conn, "SHOW COLUMNS FROM `series`")]
    return [r for r in q(conn, "SELECT * FROM `series`")], cols


def fetch_ep_counts(conn):
    """Real episodes per series (series_episodes row whose stream exists)."""
    rows = q(conn, "SELECT se.series_id AS sid, COUNT(*) AS n FROM series_episodes se "
                   "INNER JOIN streams s ON s.id = se.stream_id GROUP BY se.series_id")
    return {int(r["sid"]): int(r["n"]) for r in rows}


def fetch_se(conn, series_ids, lock=False):
    return q(conn, "SELECT id, season_num, series_id, stream_id, sort FROM series_episodes "
                   "WHERE series_id IN (%s)%s" % (in_list(series_ids), " FOR UPDATE" if lock else ""))


def fetch_streams(conn, stream_ids):
    out = {}
    ids = list(stream_ids)
    for i in range(0, len(ids), 2000):
        for r in q(conn, "SELECT id, type FROM streams WHERE id IN (%s)" % in_list(ids[i:i + 2000])):
            out[int(r["id"])] = int(r["type"])
    return out


def still_referenced(conn, stream_ids, deleting_se):
    """Streams used by a series_episodes row that is NOT being deleted."""
    ids = list(stream_ids)
    used = set()
    skip = "" if not deleting_se else " AND id NOT IN (%s)" % in_list(deleting_se)
    for i in range(0, len(ids), 2000):
        for r in q(conn, "SELECT DISTINCT stream_id FROM series_episodes WHERE stream_id IN (%s)%s"
                   % (in_list(ids[i:i + 2000]), skip)):
            used.add(int(r["stream_id"]))
    return used


def bouquets_for(conn, member_ids):
    """Bouquets whose bouquet_series mentions any member id. Returns [(id, name, text)]."""
    out = []
    members = set(member_ids)
    for b in q(conn, "SELECT id, bouquet_name, bouquet_series FROM bouquets"):
        try:
            arr = json.loads(b["bouquet_series"] or "[]")
        except ValueError:
            continue
        if isinstance(arr, list) and any(_toint(x) in members for x in arr):
            out.append(b)
    return out


def _toint(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def build_plan(conn, series_rows, only_series_id=None, limit=0):
    by_id = {int(r["id"]): r for r in series_rows}
    groups, skipped = group_series(series_rows)
    if only_series_id:
        groups = [g for g in groups if only_series_id in g]
    if limit:
        groups = groups[:limit]
    counts = fetch_ep_counts(conn)
    all_bouquets = q(conn, "SELECT id, bouquet_name, bouquet_series FROM bouquets")
    plans = []
    for g in groups:
        keeper = choose_keeper(g, counts)
        se = fetch_se(conn, g)
        streams = fetch_streams(conn, [int(r["stream_id"]) for r in se])
        p = plan_merge(keeper, g, se, streams)
        refd = still_referenced(conn, p["delete_streams"], p["delete_se"])
        p["delete_streams"] = [s for s in p["delete_streams"] if s not in refd]
        p.update(group=g, keeper=keeper, title=by_id[keeper]["title"], tmdb_id=int(by_id[keeper].get("tmdb_id") or 0),
                 ep_counts={i: counts.get(i, 0) for i in g}, se=se, streams=streams)
        members = set(g)
        p["bouquets"] = []
        for b in all_bouquets:
            try:
                arr = json.loads(b["bouquet_series"] or "[]")
            except ValueError:
                continue
            if isinstance(arr, list) and any(_toint(x) in members for x in arr):
                p["bouquets"].append((int(b["id"]), b["bouquet_name"]))
        plans.append(p)
    return plans, skipped


def orphan_report(conn):
    return {
        "se": [int(r["id"]) for r in q(conn, "SELECT se.id FROM series_episodes se LEFT JOIN streams s "
                                             "ON s.id = se.stream_id WHERE s.id IS NULL")],
        "sys": [int(r["server_stream_id"]) for r in q(conn, "SELECT ss.server_stream_id FROM streams_sys ss "
                                                            "LEFT JOIN streams s ON s.id = ss.stream_id WHERE s.id IS NULL")],
        "no_series": [int(r["id"]) for r in q(conn, "SELECT s.id FROM streams s LEFT JOIN series_episodes se "
                                                    "ON se.stream_id = s.id WHERE s.type = 5 AND se.id IS NULL")],
    }


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
def print_summary(plans, skipped, orph, top, apply_mode):
    extra = sum(len(p["remove_series"]) for p in plans)
    moves = sum(len(p["move_ids"]) for p in plans)
    conf = sum(len(p["conflicts"]) for p in plans)
    dels = sum(len(p["delete_streams"]) for p in plans)
    bq = len(set(b[0] for p in plans for b in p["bouquets"]))
    print("=" * 70)
    print("SERIES DEDUPE - %s" % ("APPLY" if apply_mode else "DRY RUN (nothing is changed)"))
    print("=" * 70)
    print("Duplicate groups (shows split into several rows) : %d" % len(plans))
    print("Extra series rows to remove                      : %d" % extra)
    print("Episodes to move to the kept series              : %d" % moves)
    print("Slot conflicts (same season+episode twice)       : %d  (older copies removed: %d streams)" % (conf, dels))
    print("Bouquets that will be rewritten                  : %d" % bq)
    print("Skipped (no tmdb_id and no year, cannot be sure) : %d" % skipped)
    if orph is not None:
        print("Orphans: series_episodes with no stream          : %d" % len(orph["se"]))
        print("Orphans: streams_sys rows with no stream         : %d" % len(orph["sys"]))
        print("Report only: episode streams with no series      : %d  (never deleted)" % len(orph["no_series"]))
        if orph["no_series"]:
            print("   first ids: %s" % ", ".join(str(i) for i in orph["no_series"][:20]))
    print()
    for p in sorted(plans, key=lambda p: -len(p["group"]))[:top]:
        print("- %s  (tmdb %s)  keep id %d, remove %d rows" % (p["title"], p["tmdb_id"] or "-", p["keeper"], len(p["remove_series"])))
        print("    series ids : %s" % ", ".join("%d(%d ep)" % (i, p["ep_counts"][i]) for i in p["group"]))
        print("    move %d episode(s), %d conflict(s), bouquets: %s" % (
            len(p["move_ids"]), len(p["conflicts"]),
            ", ".join("%s(#%d)" % (n, i) for i, n in p["bouquets"]) or "none"))
        for season, sort, win, lost in p["conflicts"][:5]:
            print("    conflict S%02dE%02d: keep newest, drop %d older" % (season, sort, len(lost)))
    if len(plans) > top:
        print("... and %d more group(s). Use --top N to see more." % (len(plans) - top))
    print()


# ---------------------------------------------------------------------------
# Backup
# ---------------------------------------------------------------------------
def make_backup(cfg, plans, orph, out_dir):
    exe = shutil.which("mysqldump")
    if not exe:
        return None, "mysqldump not found (apt install -y mysql-client or mariadb-client)"
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    n = 1
    while os.path.exists(os.path.join(out_dir, "series_dedupe_backup_%s.sql" % ts)):
        n += 1
        ts = "%s_%d" % (ts.split("_")[0] + "_" + ts.split("_")[1], n)
    path = os.path.join(out_dir, "series_dedupe_backup_%s.sql" % ts)
    fd, cnf = tempfile.mkstemp(prefix="sd_", suffix=".cnf")
    try:
        with os.fdopen(fd, "w") as f:
            f.write("[client]\nuser=%s\npassword=\"%s\"\nhost=%s\nport=%s\n" % (
                cfg["db_user"], str(cfg["db_pass"]).replace("\\", "\\\\").replace('"', '\\"'),
                cfg["host"], int(cfg.get("db_port", 3306))))
        os.chmod(cnf, 0o600)
        help_txt = subprocess.run([exe, "--help"], capture_output=True, text=True).stdout
        base = [exe, "--defaults-extra-file=" + cnf, "--single-transaction", "--no-create-info",
                "--replace", "--complete-insert", "--skip-comments", "--default-character-set=utf8mb4"]
        if "no-tablespaces" in help_txt:
            base.append("--no-tablespaces")
        db = cfg["db_name"]
        jobs = [base + [db, "series"], base + [db, "series_episodes"], base + [db, "bouquets"]]
        sids = sorted(set(s for p in plans for s in p["delete_streams"]))
        for i in range(0, len(sids), 1000):
            ids = in_list(sids[i:i + 1000])
            jobs.append(base + ["--where=id IN (%s)" % ids, db, "streams"])
            jobs.append(base + ["--where=stream_id IN (%s)" % ids, db, "streams_sys"])
        if orph is not None and orph["sys"]:
            jobs.append(base + ["--where=stream_id NOT IN (SELECT id FROM streams)", db, "streams_sys"])
        with open(path, "w") as out:
            out.write("-- series_dedupe backup %s. Restore: mysql %s < this file\n" % (ts, db))
            out.write("SET NAMES utf8mb4;\n")
            for cmd in jobs:
                r = subprocess.run(cmd, stdout=out, stderr=subprocess.PIPE, text=True)
                if r.returncode != 0:
                    return None, "mysqldump failed: %s" % r.stderr.strip()[:300]
        if os.path.getsize(path) < 100:
            return None, "backup file is empty"
        return path, None
    except Exception as e:
        return None, "backup error: %s" % e
    finally:
        try:
            os.unlink(cnf)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------
def apply_group(conn, p, series_cols, allowed_streams):
    """One transaction. Re-reads everything under lock; aborts (rollback) if it differs unsafely."""
    g, keeper = p["group"], p["keeper"]
    try:
        conn.begin()
        rows = q(conn, "SELECT * FROM `series` WHERE id IN (%s) FOR UPDATE" % in_list(g))
        if len(rows) != len(g):
            raise RuntimeError("series rows changed since the scan")
        tm = set(int(r.get("tmdb_id") or 0) for r in rows)
        if len(tm) != 1:
            raise RuntimeError("tmdb_id differs inside group (refusing to merge)")
        by_id = {int(r["id"]): r for r in rows}
        se = fetch_se(conn, g, lock=True)
        streams = fetch_streams(conn, [int(r["stream_id"]) for r in se])
        p2 = plan_merge(keeper, g, se, streams)
        refd = still_referenced(conn, p2["delete_streams"], p2["delete_se"])
        p2["delete_streams"] = [s for s in p2["delete_streams"] if s not in refd]
        extra = [s for s in p2["delete_streams"] if s not in allowed_streams]
        if extra:
            raise RuntimeError("stream(s) %s to delete are not in the backup" % extra[:5])
        with conn.cursor() as c:
            if p2["move_ids"]:
                c.execute("UPDATE series_episodes SET series_id = %s WHERE id IN (" + in_list(p2["move_ids"]) + ")", (keeper,))
            if p2["delete_se"]:
                c.execute("DELETE FROM series_episodes WHERE id IN (" + in_list(p2["delete_se"]) + ")")
            for sid in p2["delete_streams"]:
                c.execute("DELETE FROM streams_sys WHERE stream_id = %s", (sid,))
                c.execute("DELETE FROM streams WHERE id = %s AND type = 5", (sid,))
            c.execute("SELECT COUNT(*) FROM series_episodes WHERE series_id IN (" + in_list(p2["remove_series"]) + ")")
            if c.fetchone()[0] != 0:
                raise RuntimeError("episodes still point at a series about to be deleted")
            upd = fill_updates(by_id[keeper], [by_id[i] for i in g if i != keeper])
            upd["last_modified"] = int(time.time())
            sets = ", ".join("`%s` = %%s" % k for k in upd)
            c.execute("UPDATE `series` SET %s WHERE id = %%s" % sets, list(upd.values()) + [keeper])
            c.execute("DELETE FROM `series` WHERE id IN (" + in_list(p2["remove_series"]) + ")")
            for b in q(conn, "SELECT id, bouquet_series FROM bouquets FOR UPDATE"):
                try:
                    arr = json.loads(b["bouquet_series"] or "[]")
                except ValueError:
                    continue
                if not (isinstance(arr, list) and any(_toint(x) in set(g) for x in arr)):
                    continue
                new, changed = rewrite_bouquet(b["bouquet_series"], g, keeper)
                if changed:
                    c.execute("UPDATE bouquets SET bouquet_series = %s WHERE id = %s", (new, b["id"]))
        conn.commit()
        return True, "ok", p2
    except Exception as e:
        conn.rollback()
        return False, str(e), None


def apply_orphans(conn):
    done = {"se": 0, "sys": 0}
    try:
        conn.begin()
        with conn.cursor() as c:
            done["se"] = c.execute("DELETE se FROM series_episodes se LEFT JOIN streams s ON s.id = se.stream_id WHERE s.id IS NULL")
            done["sys"] = c.execute("DELETE ss FROM streams_sys ss LEFT JOIN streams s ON s.id = ss.stream_id WHERE s.id IS NULL")
        conn.commit()
        return True, done
    except Exception as e:
        conn.rollback()
        return False, str(e)


def check_innodb(conn):
    rows = q(conn, "SELECT TABLE_NAME AS t, ENGINE AS e FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() "
                   "AND TABLE_NAME IN ('series','series_episodes','streams','streams_sys','bouquets')")
    return [r["t"] for r in rows if str(r["e"]).lower() != "innodb"]


def main():
    ap = argparse.ArgumentParser(description="Merge duplicate series rows (dry run by default).")
    ap.add_argument("--version", action="version", version="series_dedupe " + VERSION)
    ap.add_argument("--apply", action="store_true", help="make the changes (default: dry run)")
    ap.add_argument("--orphans", action="store_true", help="also clean orphan series_episodes / streams_sys rows")
    ap.add_argument("--limit", type=int, default=0, metavar="N", help="only process N groups (testing)")
    ap.add_argument("--series-id", type=int, default=0, metavar="X", help="only the group containing series id X")
    ap.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    ap.add_argument("--top", type=int, default=10, metavar="N", help="groups to show in detail (default 10)")
    ap.add_argument("--config", default=CONFIG_FILE, help="panel config file (default %s)" % CONFIG_FILE)
    ap.add_argument("--backup-dir", default=".", help="where the backup .sql goes (default: current folder)")
    ap.add_argument("--db-host"); ap.add_argument("--db-port", type=int); ap.add_argument("--db-user")
    ap.add_argument("--db-pass"); ap.add_argument("--db-name")
    a = ap.parse_args()

    cfg = None
    if a.db_host and a.db_user and a.db_name:
        cfg = {"host": a.db_host, "db_port": a.db_port or 3306, "db_user": a.db_user,
               "db_pass": a.db_pass or "", "db_name": a.db_name}
    conn, cfg, err = db_connect(cfg, a.config)
    if err:
        print("ERROR: " + err)
        return 2
    bad = check_innodb(conn)
    if bad and a.apply:
        print("ERROR: these tables are not InnoDB, so transactions cannot roll back: %s" % ", ".join(bad))
        return 2
    series_rows, series_cols = fetch_series(conn)
    plans, skipped = build_plan(conn, series_rows, a.series_id or None, a.limit)
    if a.series_id and not plans:
        print("Series %d is not part of a duplicate group (or does not exist). Nothing to do." % a.series_id)
    orph = orphan_report(conn) if a.orphans else None
    conn.commit()
    print_summary(plans, skipped, orph, a.top, a.apply)
    if not a.apply:
        print("Dry run only. To make the changes add --apply (a backup is written first).")
        return 0
    if not plans and not (orph and (orph["se"] or orph["sys"])):
        print("Nothing to do.")
        return 0
    if not a.yes:
        if input("Type YES to back up and apply these changes: ").strip() != "YES":
            print("Cancelled. Nothing changed.")
            return 1
    path, err = make_backup(cfg, plans, orph, a.backup_dir)
    if err:
        print("ABORTED, nothing changed. Backup failed: " + err)
        return 3
    print("Backup written: %s" % os.path.abspath(path))
    allowed = set(s for p in plans for s in p["delete_streams"])
    ok_n = fail_n = 0
    for i, p in enumerate(plans, 1):
        ok, msg, p2 = apply_group(conn, p, series_cols, allowed)
        if ok:
            ok_n += 1
            print("[%d/%d] merged '%s' -> series %d (removed %d rows, moved %d episodes, dropped %d old streams)" % (
                i, len(plans), p["title"], p["keeper"], len(p2["remove_series"]), len(p2["move_ids"]), len(p2["delete_streams"])))
        else:
            fail_n += 1
            print("[%d/%d] SKIPPED '%s' (rolled back, nothing changed for it): %s" % (i, len(plans), p["title"], msg))
    if orph is not None:
        ok, res = apply_orphans(conn)
        if ok:
            print("Orphans removed: %d series_episodes, %d streams_sys rows" % (res["se"], res["sys"]))
        else:
            print("Orphan cleanup FAILED (rolled back): %s" % res)
    print()
    print("Done. Merged %d group(s), %d skipped. Backup: %s" % (ok_n, fail_n, os.path.abspath(path)))
    print("Next: reload the Series page. If a show looks wrong, restore with:  mysql %s < %s" % (cfg["db_name"], os.path.abspath(path)))
    print("Series 'seasons' info comes from TMDB and is kept as is. To refresh it, open the show in the panel and Save.")
    return 0 if fail_n == 0 else 4


if __name__ == "__main__":
    sys.exit(main())
