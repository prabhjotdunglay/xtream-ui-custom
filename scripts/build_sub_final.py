#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Builds sub_FINAL.zip, the LB payload asset, from the recovered znuff
# payload in lbznuff/iptv_xtream_codes/.
#
# Reused program files (nginx, php, ffmpeg, decoded PHP) only. Removed:
#   - the real config (main IP, DB password), tmp/*, logs/*, *.pid, streams/*,
#     .DS_Store files
#   - pytools/config.py and config.rs (znuff's downloaded Rust binary), both
#     replaced by our flag-based pytools/config.py
#   - the 0-byte GeoLite2.mmdb, replaced by our GeoLite2.mmdb
#
# Usage:
#   python3 scripts/build_sub_final.py <lbznuff_dir> <our_config_py> <our_geolite> <out_zip>
import os
import sys
import zipfile

SKIP_NAMES = {".DS_Store"}
# Only the top-level runtime directories, not any directory sharing that name
# deeper in the tree (e.g. php/include/php/main/streams/ is real PHP source).
SKIP_TOP_LEVEL_DIRS = {"tmp", "logs", "streams"}
SKIP_FILES_AT_ROOT = {"config", "GeoLite2.mmdb"}
SKIP_PATTERNS_SUFFIX = (".pid",)
SKIP_RELATIVE = {
    os.path.join("pytools", "config.py"),
    os.path.join("pytools", "config.rs"),
}


def should_skip(rel_path, is_dir_entry):
    parts = rel_path.split(os.sep)
    base = parts[-1]
    if base in SKIP_NAMES:
        return True
    if parts[0] in SKIP_TOP_LEVEL_DIRS and (len(parts) > 1 or is_dir_entry):
        return True
    if len(parts) == 1 and base in SKIP_FILES_AT_ROOT:
        return True
    if base.endswith(SKIP_PATTERNS_SUFFIX):
        return True
    if rel_path in SKIP_RELATIVE:
        return True
    return False


def build(lbznuff_root, our_config_py, our_geolite, out_zip):
    src_root = os.path.join(lbznuff_root, "iptv_xtream_codes")
    if not os.path.isdir(src_root):
        raise SystemExit("not found: %s" % src_root)

    if os.path.exists(out_zip):
        os.remove(out_zip)

    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        for dirpath, dirnames, filenames in os.walk(src_root):
            rel_dir = os.path.relpath(dirpath, src_root)
            # prune skipped directories in-place so os.walk does not descend into them
            dirnames[:] = [
                d for d in dirnames
                if not should_skip(os.path.normpath(os.path.join(rel_dir, d)) if rel_dir != "." else d, True)
            ]
            for fname in filenames:
                rel_file = os.path.normpath(os.path.join(rel_dir, fname)) if rel_dir != "." else fname
                if should_skip(rel_file, False):
                    continue
                full_path = os.path.join(dirpath, fname)
                arcname = os.path.join("iptv_xtream_codes", rel_file)
                zf.write(full_path, arcname)

        # our own config.py (flag-based), replacing znuff's Rust binary
        zi = zipfile.ZipInfo.from_file(our_config_py, os.path.join("iptv_xtream_codes", "pytools", "config.py"))
        zi.external_attr = (0o100755 << 16)
        zi.compress_type = zipfile.ZIP_DEFLATED
        with open(our_config_py, "rb") as fh:
            zf.writestr(zi, fh.read())
        # our own GeoLite2.mmdb, replacing the 0-byte placeholder
        zf.write(our_geolite, os.path.join("iptv_xtream_codes", "GeoLite2.mmdb"))

    bad = None
    with zipfile.ZipFile(out_zip) as zf:
        bad = zf.testzip()
    if bad is not None:
        raise SystemExit("zip failed testzip() at %s" % bad)

    print("built %s (%d bytes)" % (out_zip, os.path.getsize(out_zip)))


if __name__ == "__main__":
    if len(sys.argv) != 5:
        print("usage: build_sub_final.py <lbznuff_dir> <our_config_py> <our_geolite> <out_zip>")
        sys.exit(1)
    build(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
