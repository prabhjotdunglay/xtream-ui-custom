#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Builds the release assets for the in-panel updater (BUILD_NOTES.md section 24):
#   update_code.zip         code-only package (allow-listed panel files + manifest.json [+ migrations/])
#   update_code.zip.sha256  64 hex characters + newline
#   version.json            what the panel reads before downloading anything
#
# Usage:
#   python3 scripts/build_update_code.py <base_dir> <version_int> <out_dir>
#       [--changelog-file F] [--min-version N] [--requires-manual]
#       [--manual-notes-file F] [--migrations-dir DIR]
#
# <base_dir> is the panel tree, e.g.
#   "/Users/prabhjotdunglay/Downloads/untitled folder/xtreamcodes/iptv_xtream_codes"
# It is only read, never modified. The version must equal $rGTBVersion in admin/functions.php.
#
# The allow-list and exclusions below MUST match crons/gtb_update.php (gtbu_path_problem).
# The build fails (it never silently skips) on a file that is forbidden but not an
# known runtime file, so a bad file cannot reach a customer.
import argparse
import hashlib
import json
import os
import re
import stat
import sys
import zipfile

TOP_DIRS = ["admin", "wwwdir", "crons", "tools", "pytools", "SecTools", "isp"]
ROOT_FILES = ["BUILD_NOTES.md", "database.sql"]
# Runtime data inside allowed directories: silently left out.
EXCLUDE_PREFIX = ["isp/data/", "admin/icons/"]
EXCLUDE_EXACT = ["isp/errors.txt", "isp/cloud_ips", "isp/apibackup.txt"]
EXCLUDE_NAMES = {".DS_Store", "Thumbs.db", "GeoLite2.mmdb", "maxmind.key"}
EXCLUDE_DIR_NAMES = {"__pycache__", ".agents", ".git"}
EXCLUDE_SUFFIXES = (".pyc", ".bak")  # .obf.bak ends with .bak
EXCLUDE_NAME_PREFIX = ("cloud_ssl",)
COMPONENT = re.compile(r"^[A-Za-z0-9._@+() -]+$")
MIGRATION = re.compile(r"^\d{3}_[a-z0-9_]{1,60}\.sql$")
FIXED_DATE = (2024, 1, 1, 0, 0, 0)  # deterministic zip entries
MAX_ZIP = 200 * 1024 * 1024  # keep equal to GTBU_MAX_ZIP in crons/gtb_update.php


def excluded(rel):
    """True for known runtime/backup files that are left out of the package."""
    parts = rel.split("/")
    base = parts[-1]
    if any(p in EXCLUDE_DIR_NAMES for p in parts[:-1]):
        return True
    if base in EXCLUDE_NAMES or base.startswith(EXCLUDE_NAME_PREFIX) or base.endswith(EXCLUDE_SUFFIXES):
        return True
    if rel in EXCLUDE_EXACT or any(rel.startswith(x) for x in EXCLUDE_PREFIX):
        return True
    return False


def bad_name(rel):
    if len(rel) > 240:
        return "path too long"
    for c in rel.split("/"):
        if not COMPONENT.match(c) or c.startswith(" ") or c.endswith(" ") or ".gtbtmp" in c:
            return "unsupported characters in %r" % c
    return None


def collect(base):
    files = []
    for top in TOP_DIRS:
        root = os.path.join(base, top)
        if not os.path.isdir(root):
            sys.exit("missing directory: " + root)
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            dirnames.sort()
            for d in list(dirnames):
                if os.path.islink(os.path.join(dirpath, d)):
                    sys.exit("symbolic link directory refused: " + os.path.join(dirpath, d))
            for fn in sorted(filenames):
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, base).replace(os.sep, "/")
                if os.path.islink(full):
                    sys.exit("symbolic link refused: " + rel)
                if excluded(rel):
                    continue
                problem = bad_name(rel)
                if problem:
                    sys.exit("cannot ship %s: %s" % (rel, problem))
                files.append((rel, full))
    for fn in ROOT_FILES:
        full = os.path.join(base, fn)
        if os.path.isfile(full):
            files.append((fn, full))
    files.sort(key=lambda x: x[0])
    return files


def is_exec(full, rel):
    mode = os.stat(full).st_mode
    base = rel.rsplit("/", 1)[-1]
    scripty = base.endswith((".sh", ".py")) or "." not in base
    return bool(mode & stat.S_IXUSR) and scripty


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def add(z, name, data, exec_bit=False):
    zi = zipfile.ZipInfo(name, FIXED_DATE)
    zi.compress_type = zipfile.ZIP_DEFLATED
    zi.create_system = 3
    zi.external_attr = ((stat.S_IFREG | (0o755 if exec_bit else 0o644)) & 0xFFFF) << 16
    z.writestr(zi, data)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("base_dir")
    ap.add_argument("version", type=int)
    ap.add_argument("out_dir")
    ap.add_argument("--changelog-file")
    ap.add_argument("--min-version", type=int, default=0)
    ap.add_argument("--requires-manual", action="store_true")
    ap.add_argument("--manual-notes-file")
    ap.add_argument("--migrations-dir")
    ap.add_argument("--published", help="date string for version.json (default: today)")
    a = ap.parse_args()

    base = os.path.abspath(a.base_dir)
    out = os.path.abspath(a.out_dir)
    if not os.path.isdir(base):
        sys.exit("base_dir not found: " + base)
    if a.version < 1:
        sys.exit("version must be a positive integer")
    if out == base or out.startswith(base + os.sep):
        sys.exit("out_dir must be outside base_dir (the base is never modified)")
    with open(os.path.join(base, "admin", "functions.php"), "r", encoding="utf-8", errors="replace") as f:
        m = re.search(r'\$rGTBVersion\s*=\s*"(\d+)"', f.read(4000))
    if not m or int(m.group(1)) != a.version:
        sys.exit("admin/functions.php has $rGTBVersion = %s but you asked for version %d. Bump it first." % (m.group(1) if m else "?", a.version))

    files = collect(base)
    required = ["admin/functions.php", "admin/settings.php", "admin/login.php", "admin/gtb_health.php",
                "admin/gtb_update_api.php", "wwwdir/init.php", "crons/gtb_update.php"]
    names = {r for r, _ in files}
    for r in required:
        if r not in names:
            sys.exit("required file missing from the package: " + r)

    migrations = []
    if a.migrations_dir:
        for fn in sorted(os.listdir(a.migrations_dir)):
            if not MIGRATION.match(fn):
                sys.exit("invalid migration name (use NNN_name.sql, lowercase): " + fn)
            migrations.append(("migrations/" + fn, os.path.join(a.migrations_dir, fn)))

    changelog = ""
    if a.changelog_file:
        with open(a.changelog_file, "r", encoding="utf-8") as f:
            changelog = f.read().strip()
    notes = ""
    if a.manual_notes_file:
        with open(a.manual_notes_file, "r", encoding="utf-8") as f:
            notes = f.read().strip()
    if a.requires_manual and not notes:
        sys.exit("--requires-manual needs --manual-notes-file")

    entries = []
    manifest_files = []
    for rel, full in files + migrations:
        manifest_files.append({"path": rel, "sha256": sha256_file(full), "size": os.path.getsize(full),
                               "exec": is_exec(full, rel) if not rel.startswith("migrations/") else False})
        entries.append((rel, full, manifest_files[-1]["exec"]))
    manifest = {"version": a.version, "files": manifest_files}
    manifest_bytes = (json.dumps(manifest, indent=1, sort_keys=True) + "\n").encode("utf-8")

    os.makedirs(out, exist_ok=True)
    zpath = os.path.join(out, "update_code.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as z:
        add(z, "manifest.json", manifest_bytes)
        for rel, full, ex in entries:
            with open(full, "rb") as f:
                add(z, rel, f.read(), ex)
    size = os.path.getsize(zpath)
    if size > MAX_ZIP:
        sys.exit("update_code.zip is %d bytes, over the 200 MB limit the panel accepts" % size)
    digest = sha256_file(zpath)
    with open(zpath + ".sha256", "w") as f:
        f.write(digest + "\n")
    import datetime
    published = a.published or datetime.date.today().isoformat()
    vj = {"version": a.version, "name": "GTB v%d" % a.version, "changelog": changelog, "min_version": a.min_version,
          "requires_manual": bool(a.requires_manual), "manual_notes": notes, "sha256": digest, "size": size,
          "published": published}
    with open(os.path.join(out, "version.json"), "w", encoding="utf-8") as f:
        f.write(json.dumps(vj, indent=1, sort_keys=True) + "\n")
    print("files in package : %d (+%d migrations)" % (len(files), len(migrations)))
    print("uncompressed     : %d bytes" % sum(e["size"] for e in manifest_files))
    print("update_code.zip  : %d bytes" % size)
    print("sha256           : %s" % digest)
    print("written to       : %s" % out)


if __name__ == "__main__":
    main()
