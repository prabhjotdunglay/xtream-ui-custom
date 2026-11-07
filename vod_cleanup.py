#!/usr/bin/env python3
"""
vod_cleanup.py - remove dead VOD entries (movies / episodes whose file is gone for good) from the PANEL
database, safely.

RUN THIS ON THE PANEL'S MAIN (DATABASE) SERVER - not on the load balancer.
  B's list  -> B's main server        A's list -> A's main server   (the ids in each list belong to that panel)

The ids come from the load balancer:  vod_heal.py --export-cleanup   (writes cleanup_ids_<time>.txt).
Copy that file to this server, then:

  python3 vod_cleanup.py --ids-file cleanup_ids_X.txt            # DRY RUN: shows exactly what would go
  python3 vod_cleanup.py --ids-file cleanup_ids_X.txt --commit   # backs up, deletes, verifies

WHAT IT REMOVES (only for the ids in your list)
  * the movie / episode rows in `streams`                      (only type 2 = movie, type 5 = episode)
  * their `streams_sys` rows (server assignments) and `series_episodes` rows
  * a series that is left with NO episodes at all              (series row + its entry in bouquets)
  * those movie ids from the movie bouquets (`bouquet_channels`)
WHAT IT NEVER TOUCHES
  * live TV (type 1) or anything that is not a movie/episode - such ids in your file are ignored
  * series that still have at least one episode (only the dead episodes are removed)
  * users, lines, packages, history/log tables

SAFETY
  * dry run is the default; --commit is needed to change anything
  * before deleting it saves every row it will delete (and the whole bouquets table) to a .sql.gz backup;
    if the backup fails, nothing is deleted
  * all deletes run in ONE transaction (InnoDB tables); it is verified afterwards
  * refuses to remove an unusually large share of your library unless you pass --force
  * restore:  gunzip -c <backup>.sql.gz | mysql -u root xtream_iptvpro
"""
import argparse
import collections
import datetime
import gzip
import json
import os
import re
import shlex
import subprocess
import sys

VERSION = "2026-11-08-F"


class MySQL(object):
    def __init__(self, opts, db):
        self.opts = shlex.split(opts)
        self.db = db

    def query(self, sql):
        r = subprocess.run(["mysql"] + self.opts + ["--batch", "--skip-column-names", self.db, "-e", sql],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip() or "mysql failed")
        return [line.split("\t") for line in r.stdout.split("\n") if line != ""]

    def script(self, sql):
        r = subprocess.run(["mysql"] + self.opts + [self.db], input=sql,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip() or "mysql failed")

    def dump(self, table, where):
        r = subprocess.run(["mysqldump"] + self.opts + ["--no-create-info", "--complete-insert", "--replace",
                                                       "--single-transaction", "--quick", "--where=" + where,
                                                       self.db, table],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        if r.returncode != 0:
            raise RuntimeError("mysqldump %s failed: %s" % (table, r.stderr.strip()))
        if "Dump completed" not in r.stdout:
            raise RuntimeError("mysqldump %s did not finish cleanly" % table)
        return r.stdout


def chunks(seq, n=1000):
    seq = list(seq)
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def in_list(ids):
    return ",".join(str(int(i)) for i in ids)


def sql_str(s):
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


def main(argv=None, db=None):
    ap = argparse.ArgumentParser(description="Remove dead VOD entries from the panel database (dry run by default).")
    ap.add_argument("--ids-file", required=True, help="cleanup_ids_*.txt from 'vod_heal.py --export-cleanup'")
    ap.add_argument("--commit", action="store_true", help="really back up and delete (default: dry run)")
    ap.add_argument("--db", default="xtream_iptvpro")
    ap.add_argument("--mysql-opts", default="-u root", help="extra mysql options (default '-u root')")
    ap.add_argument("--backup-dir", default="/root")
    ap.add_argument("--max-delete", type=int, default=8000, help="refuse to delete more ids than this (default 8000)")
    ap.add_argument("--max-percent", type=float, default=15.0, help="refuse to delete more than this %% of all movies+episodes")
    ap.add_argument("--force", action="store_true", help="override the two limits above")
    ap.add_argument("--keep-empty-series", action="store_true", help="do not remove series that end up with no episodes")
    ap.add_argument("--version", action="version", version="vod_cleanup " + VERSION)
    a = ap.parse_args(argv)

    if not os.path.isfile(a.ids_file):
        print("ids file not found: %s" % a.ids_file)
        return 1
    ids = sorted(set(int(x) for x in re.findall(r"\d+", open(a.ids_file).read())))
    if not ids:
        print("The ids file is empty - nothing to do.")
        return 0
    db = db or MySQL(a.mysql_opts, a.db)
    try:
        db.query("SELECT 1")
    except Exception as e:
        print("Cannot talk to MySQL: %s" % e)
        print("Run this on the panel's MAIN server as root, or pass --mysql-opts '-u root -pPASSWORD'.")
        return 3

    # ---- what are these ids? ----
    info = {}
    for ch in chunks(ids):
        for r in db.query("SELECT id, type, stream_display_name FROM streams WHERE id IN (%s)" % in_list(ch)):
            info[int(r[0])] = (int(r[1]), r[2] if len(r) > 2 else "")
    not_found = [i for i in ids if i not in info]
    foreign = [i for i in ids if i in info and info[i][0] not in (2, 5)]
    del_ids = [i for i in ids if i in info and info[i][0] in (2, 5)]
    movies = [i for i in del_ids if info[i][0] == 2]
    episodes = [i for i in del_ids if info[i][0] == 5]
    print("vod_cleanup %s on database '%s'" % (VERSION, a.db))
    print("ids in your file               : %d" % len(ids))
    print("  not in this database         : %d  (already gone - nothing to do)" % len(not_found))
    print("  NOT a movie/episode (ignored): %d  (live TV and other types are never removed)" % len(foreign))
    print("  movies to remove             : %d" % len(movies))
    print("  episodes to remove           : %d" % len(episodes))
    if not del_ids:
        print("Nothing to remove.")
        return 0

    # ---- series bookkeeping ----
    per_series_deleted = collections.Counter()
    for ch in chunks(del_ids):
        for r in db.query("SELECT series_id, stream_id FROM series_episodes WHERE stream_id IN (%s)" % in_list(ch)):
            per_series_deleted[int(r[0])] += 1
    n_ep_rows = sum(per_series_deleted.values())
    totals = {}
    for ch in chunks(per_series_deleted.keys()):
        for r in db.query("SELECT series_id, COUNT(*) FROM series_episodes WHERE series_id IN (%s) GROUP BY series_id" % in_list(ch)):
            totals[int(r[0])] = int(r[1])
    empty_series = sorted(s for s, k in per_series_deleted.items() if totals.get(s, 0) == k)
    if a.keep_empty_series:
        empty_series = []
    partial = [s for s in per_series_deleted if s not in set(empty_series)]
    titles = {}
    for ch in chunks(per_series_deleted.keys()):
        for r in db.query("SELECT id, title FROM series WHERE id IN (%s)" % in_list(ch)):
            titles[int(r[0])] = r[1]

    n_sys = 0
    for ch in chunks(del_ids):
        n_sys += int(db.query("SELECT COUNT(*) FROM streams_sys WHERE stream_id IN (%s)" % in_list(ch))[0][0])

    # ---- bouquets ----
    del_set, empty_set = set(del_ids), set(empty_series)
    bq_changes = []                      # (id, name, new_channels_json, new_series_json, removed_channels, removed_series)
    bq_problems = []
    for r in db.query("SELECT id, bouquet_name, bouquet_channels, bouquet_series FROM bouquets"):
        bid, name, ch_raw, se_raw = int(r[0]), r[1], (r[2] if len(r) > 2 else "[]"), (r[3] if len(r) > 3 else "[]")
        try:
            ch_l = json.loads(ch_raw) if ch_raw.strip() else []
            se_l = json.loads(se_raw) if se_raw.strip() else []
            if not isinstance(ch_l, list) or not isinstance(se_l, list):
                raise ValueError("not a list")
            new_ch = [x for x in ch_l if int(x) not in del_set]
            new_se = [x for x in se_l if int(x) not in empty_set]
        except Exception as e:
            bq_problems.append("bouquet %d (%s): cannot read its list (%s) - left unchanged" % (bid, name, e))
            continue
        rem_c, rem_s = len(ch_l) - len(new_ch), len(se_l) - len(new_se)
        if rem_c or rem_s:
            bq_changes.append((bid, name, json.dumps(new_ch, separators=(",", ":")),
                               json.dumps(new_se, separators=(",", ":")), rem_c, rem_s))

    # ---- table engines / other tables that mention stream_id ----
    engines, other = {}, []
    try:
        for r in db.query("SELECT table_name, engine FROM information_schema.tables WHERE table_schema='%s' AND table_name IN "
                          "('streams','streams_sys','series','series_episodes','bouquets')" % a.db):
            engines[r[0]] = r[1]
        for r in db.query("SELECT DISTINCT table_name FROM information_schema.columns WHERE table_schema='%s' AND column_name='stream_id'" % a.db):
            if r[0] not in ("streams_sys", "series_episodes"):
                other.append(r[0])
    except Exception:
        pass
    total_vod = int(db.query("SELECT COUNT(*) FROM streams WHERE type IN (2,5)")[0][0])
    pct = 100.0 * len(del_ids) / total_vod if total_vod else 0.0

    # ---- report ----
    weight = collections.Counter()
    ep_series = {}
    for ch in chunks(episodes):
        for r in db.query("SELECT stream_id, series_id FROM series_episodes WHERE stream_id IN (%s)" % in_list(ch)):
            ep_series[int(r[0])] = int(r[1])
    for i in del_ids:
        if info[i][0] == 2:
            weight[info[i][1] or ("movie #%d" % i)] += 1
        else:
            weight[(titles.get(ep_series.get(i)) or "episodes without a series") + "  (episodes)"] += 1
    print("")
    print("=" * 68)
    print("WHAT WOULD BE REMOVED" if not a.commit else "REMOVING")
    print("=" * 68)
    print("streams rows (movies + episodes)   : %d   of %d in the library (%.1f%%)" % (len(del_ids), total_vod, pct))
    print("streams_sys rows (server links)    : %d" % n_sys)
    print("series_episodes rows               : %d" % n_ep_rows)
    print("series left with NO episodes       : %d  -> removed too%s" % (len(empty_series), "" if not a.keep_empty_series else " (kept: --keep-empty-series)"))
    print("series that lose some episodes     : %d  (they stay, with their other episodes)" % len(partial))
    for bid, name, _, _, rc, rs in bq_changes:
        print("bouquet %-3d %-22s      : -%d movies, -%d series" % (bid, name[:22], rc, rs))
    for p in bq_problems:
        print("WARNING: " + p)
    for t, e in engines.items():
        if e and e.lower() != "innodb":
            print("WARNING: table %s is %s, not InnoDB - the delete cannot be rolled back automatically (the backup still protects you)" % (t, e))
    if other:
        print("other tables that mention stream_id (left as they are): %s" % ", ".join(other))
    print("\nBiggest removals:")
    for t, n in weight.most_common(15):
        print("  %5d  %s" % (n, t))
    if empty_series:
        print("\nSeries that would disappear completely (first 12):")
        for s in empty_series[:12]:
            print("  #%-7d %s   (%d episodes)" % (s, titles.get(s, "?"), per_series_deleted[s]))

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    outdir = a.backup_dir if os.path.isdir(a.backup_dir) else "."
    prev = os.path.join(outdir, "vod_cleanup_preview_%s.tsv" % stamp)
    try:
        with open(prev, "w", encoding="utf-8") as fh:
            fh.write("id\ttype\ttitle\n")
            for i in del_ids:
                fh.write("%d\t%s\t%s\n" % (i, "movie" if info[i][0] == 2 else "episode", info[i][1]))
        print("\nFull list of what is affected: %s" % prev)
    except OSError:
        pass

    too_many = len(del_ids) > a.max_delete or pct > a.max_percent
    if too_many and not a.force:
        print("\nSTOP: that is %d ids (%.1f%% of the library). The limits are %d ids / %.0f%%." % (len(del_ids), pct, a.max_delete, a.max_percent))
        print("If you have looked at the list above and it is right, add --force. Nothing was changed.")
        return 2

    if not a.commit:
        print("\nDRY RUN - nothing was changed.")
        print("If this looks right, run the same command with --commit.")
        return 0

    # ---- COMMIT: backup first ----
    backup = os.path.join(outdir, "vod_cleanup_backup_%s.sql.gz" % stamp)
    print("\n1/4 saving a backup of everything that will change -> %s" % backup)
    try:
        with gzip.open(backup, "wt", encoding="utf-8") as gz:
            gz.write("-- vod_cleanup backup %s. Restore: gunzip -c this file | mysql -u root %s\n" % (stamp, a.db))
            for ch in chunks(del_ids, 2000):
                gz.write(db.dump("streams", "id IN (%s)" % in_list(ch)))
                gz.write(db.dump("streams_sys", "stream_id IN (%s)" % in_list(ch)))
                gz.write(db.dump("series_episodes", "stream_id IN (%s)" % in_list(ch)))
            for ch in chunks(empty_series, 2000):
                gz.write(db.dump("series", "id IN (%s)" % in_list(ch)))
            gz.write(db.dump("bouquets", "1=1"))
    except Exception as e:
        print("BACKUP FAILED, NOTHING WAS DELETED: %s" % e)
        try:
            os.remove(backup)
        except OSError:
            pass
        return 4
    print("    backup written (%.1f MB)." % (os.path.getsize(backup) / 1e6))

    # ---- delete in one transaction ----
    print("2/4 deleting (one transaction)...")
    sql = ["START TRANSACTION;"]
    for ch in chunks(del_ids):
        sql.append("DELETE FROM series_episodes WHERE stream_id IN (%s);" % in_list(ch))
        sql.append("DELETE FROM streams_sys WHERE stream_id IN (%s);" % in_list(ch))
        sql.append("DELETE FROM streams WHERE id IN (%s) AND type IN (2,5);" % in_list(ch))
    for ch in chunks(empty_series):
        sql.append("DELETE FROM series WHERE id IN (%s);" % in_list(ch))
    for bid, name, ch_json, se_json, rc, rs in bq_changes:
        sql.append("UPDATE bouquets SET bouquet_channels=%s, bouquet_series=%s WHERE id=%d;" % (sql_str(ch_json), sql_str(se_json), bid))
    sql.append("COMMIT;")
    try:
        db.script("\n".join(sql))
    except Exception as e:
        print("DELETE FAILED: %s" % e)
        print("The transaction was not committed. Check with the dry run; your backup is at %s" % backup)
        return 5

    # ---- verify ----
    print("3/4 checking the result...")
    left = 0
    for ch in chunks(del_ids):
        left += int(db.query("SELECT COUNT(*) FROM streams WHERE id IN (%s)" % in_list(ch))[0][0])
        left += int(db.query("SELECT COUNT(*) FROM streams_sys WHERE stream_id IN (%s)" % in_list(ch))[0][0])
    still_live = db.query("SELECT COUNT(*) FROM streams WHERE type=1")[0][0]
    after_vod = int(db.query("SELECT COUNT(*) FROM streams WHERE type IN (2,5)")[0][0])
    ok = (left == 0 and after_vod == total_vod - len(del_ids))
    print("    rows of the removed ids still present : %d  (must be 0)" % left)
    print("    movies+episodes before -> after       : %d -> %d  (expected %d)" % (total_vod, after_vod, total_vod - len(del_ids)))
    print("    live TV streams (untouched)           : %s" % still_live)
    print("4/4 " + ("DONE - verified." if ok else "CHECK FAILED - restore from the backup and tell me what you saw."))
    print("\nNEXT:")
    print("  * On this server:  sudo -u xtreamcodes /home/xtreamcodes/iptv_xtream_codes/php/bin/php /home/xtreamcodes/iptv_xtream_codes/crons/setup_cache.php")
    print("    (the per-minute cron does this anyway; the lists in apps update within ~1-2 minutes)")
    print("  * On the load balancer: remove the dead links for the same ids:")
    print("      python3 vod_heal.py --remove-links cleanup_ids_X.txt          (dry run)   then add --apply")
    print("  * To undo everything:  gunzip -c %s | mysql -u root %s" % (backup, a.db))
    return 0 if ok else 6


if __name__ == "__main__":
    sys.exit(main())
