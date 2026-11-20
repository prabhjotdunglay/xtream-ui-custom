# Fixing duplicate series (Average Joe x10)

## Why it happens
Each episode is its own stream with a unique name, so deleting duplicate episode names does nothing for this.
The duplicates are in the **series** table. The panel function `getSeriesByTMDB()` returns nothing when more than
one series has the same TMDB id, so every new episode creates yet another series. Two steps fix it:

1. **Patch the panel** so no new duplicates appear (otherwise they come back).
2. **Run `series_dedupe.py`** once to merge the existing duplicates.

Do step 1 first.

## 1. Patch the OLD panel (one line)
File: `/home/xtreamcodes/iptv_xtream_codes/admin/functions.php`

In `getSeriesByTMDB`, the query must return the lowest id and accept 1 or more matches.

```
cp -p /home/xtreamcodes/iptv_xtream_codes/admin/functions.php /home/xtreamcodes/iptv_xtream_codes/admin/functions.php.bak_series
python3 - <<'EOF'
p="/home/xtreamcodes/iptv_xtream_codes/admin/functions.php"
t=open(p,encoding="utf8").read()
old='function getSeriesByTMDB($rID) { global $db; $result = $db->query("SELECT * FROM `series` WHERE `tmdb_id` = ".intval($rID).";"); if (($result) && ($result->num_rows == 1)) {'
new='function getSeriesByTMDB($rID) { global $db; $result = $db->query("SELECT * FROM `series` WHERE `tmdb_id` = ".intval($rID)." ORDER BY `id` ASC LIMIT 1;"); if (($result) && ($result->num_rows >= 1)) {'
assert t.count(old)==1, "text not found, edit by hand"
open(p,"w",encoding="utf8").write(t.replace(old,new))
print("patched")
EOF
/home/xtreamcodes/iptv_xtream_codes/php/bin/php -l /home/xtreamcodes/iptv_xtream_codes/admin/functions.php
```

If it prints "text not found", edit by hand: in `getSeriesByTMDB`, change the query end from `intval($rID).";"` to
`intval($rID)." ORDER BY \`id\` ASC LIMIT 1;"` and change `num_rows == 1` to `num_rows >= 1` (only in that function).
To undo: copy the `.bak_series` file back.

The new base panel (main_FINAL.zip) already has this fix.

## 2. Merge the existing duplicates
Copy `series_dedupe.py` to the MAIN server (the one with the database), then:

```
apt install -y python3-pymysql          # once
cd /root
python3 series_dedupe.py                # DRY RUN: only reports, changes nothing
```
It reads the DB login from the panel config automatically. The report shows duplicate groups, extra rows,
episodes to move, same-episode conflicts, and bouquets affected, plus the biggest groups in detail.

**Test on one show first** (Average Joe):
```
python3 series_dedupe.py --series-id 1007902            # dry run for that show
python3 series_dedupe.py --series-id 1007902 --apply    # asks you to type YES
```
Check the show in the panel (all episodes under one series, bouquets still list it). Then everything:
```
python3 series_dedupe.py --apply
```

### What it does and does not do
- Groups by TMDB id. If a series has no TMDB id, it groups only by identical title (ignoring case/spaces) AND same year.
  A series with no TMDB id and no year is skipped. Different TMDB ids are never merged.
- Keeps the series with the most episodes (lowest id on a tie) and moves all episodes into it.
- If the same season+episode number exists twice, it keeps the newest stream and deletes the older copy.
  Episodes with episode number 0 are never treated as copies.
- Deletes the empty duplicate series rows and fixes every bouquet (same list format, no repeats, same order).
- Each show is one database transaction. If anything fails, that show is rolled back and the tool continues.
- Viewing history (user_activity, logs) is not touched.
- Files of deleted streams on the servers (`movies/<id>.*`) are not removed. They are harmless.
- The `seasons` info is TMDB data and is kept. To refresh it for a show, open it in the panel and press Save.

### Leftovers from your earlier episode delete
```
python3 series_dedupe.py --orphans              # dry run
python3 series_dedupe.py --orphans --apply
```
Removes `series_episodes` rows whose stream is gone and `streams_sys` rows for deleted streams (database-wide).
Episode streams that belong to no series are only listed, never deleted (re-add or delete them in the panel).
Episodes your earlier delete already removed are gone for good; the tool cannot bring them back. Re-import them.

### Backup and restore
Before any change `--apply` writes `series_dedupe_backup_<date>.sql` in the current folder (or `--backup-dir`)
and prints the path. If the backup fails, nothing is changed. To restore (puts back the old rows):
```
mysql -u<user> -p <dbname> < series_dedupe_backup_YYYYMMDD_HHMMSS.sql
```
The DB name and user are in the panel config; `python3 series_dedupe.py` prints errors if it cannot connect.
After restoring, run it again in dry-run mode to see the state.

### Options
`--apply` make changes, `--orphans` orphan cleanup, `--limit N` only N groups, `--series-id X` only the group with
series X, `--yes` skip the YES prompt, `--top N` groups shown in detail, `--backup-dir DIR`.
Run it when no big import is running (watch folder or episode import), and stop adding episodes while it runs.
