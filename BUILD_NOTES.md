# BUILD_NOTES — Custom Xtream-UI build (Ubuntu 24.04, PHP 7.4.33, no IonCube)

This tree is a custom Xtream Codes / Xtream-UI panel built by modifying the BASE tree in place.
It keeps BASE's decoded ODIN admin superset and modern (2023) ffmpeg, and swaps in the newer
runtime binaries (PHP 7.4.33 / OpenSSL 3, nginx 1.27.0, nginx-http-flv RTMP) taken from the
"redss" tree. IonCube is disabled — the admin is fully decoded plaintext PHP and does not need it.

---

## 1. Release ZIP layout

The ZIP's top-level directory **must** be `iptv_xtream_codes/`, because the installer extracts into
`/home/xtreamcodes/` (so the panel lands at `/home/xtreamcodes/iptv_xtream_codes/`).

Build the MAIN release ZIP from the **parent** directory of `iptv_xtream_codes`:

```sh
cd "<parent of iptv_xtream_codes>"
zip -r main_FINAL.zip iptv_xtream_codes \
  -x '*.pid' \
     '*.obf.bak' \
     '*/.DS_Store' \
     '.DS_Store' \
     'iptv_xtream_codes/admin_deobfuscated/*'
```

Excluded on purpose:
- `*.pid` — stale php-fpm pid files (start_services.sh recreates them).
- `*.obf.bak` (17 files) — pre-decode backups, not needed at runtime.
- `.DS_Store` (4 files) — macOS Finder metadata.
- `admin_deobfuscated/` (5 files) — the reverse-engineering workspace, not runtime code.

Operator-tooling you may keep or drop at your discretion (document, not auto-excluded above):
- `SecTools/` — operator scripts; safe to ship or omit.
- `config.py` — a Python 3 DB-config decrypt helper (ported from Python 2, see sections 9 and 16). It is inert at install time (the installer does not import it). Keep it only as an operator tool.

A LB/sub-server payload `sub_FINAL.zip` (streamer-only pool, no admin/DB) is NOT built here; build
and upload it separately if you want LB installs. `php/etc/streamer.conf` is already shipped so LB
mode has its pool config.

---

## 2. What to upload to the GitHub release

Repo: `prabhjotdunglay/xtream-ui-custom` (already set in `install.py`).

- `main_FINAL.zip` → attach as the asset of the **`latest`** release.
- `sub_FINAL.zip` → attach under tag **`v1`** (only if/when you build the LB payload).
- `install.py` → commit to the **`main`** branch of the repo.
- Optional raw fallbacks on `main`: `GeoLite2.mmdb` and `pid_monitor.php`
  (the installer only fetches `GeoLite2.mmdb` if it is missing, since the ZIP already ships it).

---

## 3. User install one-liner

On a fresh Ubuntu 24.04 server, as root:

```sh
rm -rf install.py && wget -qO install.py https://raw.githubusercontent.com/prabhjotdunglay/xtream-ui-custom/main/install.py && sudo python3 install.py
```

The installer is 24.04-ONLY and refuses any other release. It prompts for `MAIN` or `LB`, sets up
MariaDB (MAIN), writes the encrypted `config`, configures tmpfs/init.d/cron, creates a placeholder SSL cert if
needed (see §Custom nginx.conf), and starts services (the `:8880` admin server ships in `nginx.conf`).

---

## 4. VERIFICATION

### Verified in this build environment
- **PHP lint (stricter-than-7.4 proxy):** every plaintext PHP file under `admin/ crons/ tools/
  wwwdir/` was linted with `php -l` using **PHP 8.2.28** (the only PHP available here).
  Result: **241 / 242 pass.** The single failure is `wwwdir/panel_api.php` — an obfuscated goto+hex
  file that trips PHP 8.2's parser on a goto-label `:` (its sibling obfuscated endpoints
  `player_api/get/portal/api/init/enigma2.php` + `includes/streaming.php` all pass under 8.2), so
  this is a PHP 8.2 parser edge-case on that one construct, **not a real 7.4 defect**.
  **This is NOT a real PHP 7.4 lint** — no 7.4 interpreter exists here. See "Could NOT verify".
- **PHP 7.4 breakage static scan:** 0 genuine `each()`, 0 `ereg/eregi/ereg_replace/spliti`, 0 global
  `split()` (the only `split(` hits are the OOP method in `admin/HTMLPurifier.standalone.php`),
  0 `create_function`, 0 curly-brace string offsets `$x{...}`, 0 `mysql_*`. No live 7.4 fixes needed.
- **Binary version strings** (via `strings`, binaries not executed — they are Linux x86-64, this host
  is macOS/arm64):
  - `php/sbin/php-fpm`: was 7.2.3 / OpenSSL 1.0.1f / libssl.so.1.0.0 → now **7.4.33 / OpenSSL 3.0.2 /
    libssl.so.3**, exec bit set.
  - `nginx/sbin/nginx`: 1.23.3 → **1.27.0**, exec bit set.
  - `nginx_rtmp/sbin/nginx_rtmp`: 1.16.1 → **1.27.0 built with nginx-http-flv-module + OpenSSL 3.3.1**,
    exec bit set.
  - `bin/ffmpeg` unchanged (still the 2023 Lavc60 build).
- **nginx configs:** originally byte-identical between BASE and redss. BASE `nginx/conf/nginx.conf` now
  deliberately differs (custom config, see §Custom nginx.conf); `nginx_rtmp` differs only in the hook port (8080).
- **php.ini:** IonCube line commented (`;zend_extension=ioncube_loader_lin_7.2.so`); only
  `zend_extension=opcache.so` remains active; `memory_limit = 2048M` preserved; commented opt-in
  JIT lines added.
- **Brand/watermark sweep:** `grep -ril easytoyou` → 0; visible `ODIN` brand strings → 0.
  The filename `wwwdir/configblock_odin.php` is intentionally kept (the obfuscated endpoints include
  it by hex path), and its `$attempts`/`$ips`/two `define()` lines are byte-unchanged.
- **Installer:** `python3 -m py_compile install.py` succeeds; 0 `ioncube_loader`/install references;
  no `red56`/`bitbucket`/`masoudgb`/`xtreamtools` strings; 24.04-only guard present.
- **start_services.sh:** `bash -n` clean; pid cleanup added; 3 absolute `/sbin/start-stop-daemon`
  launches for the 3 pools (VaiIb8/JdlJXm/CWcfSP); streamer pool NOT launched; BASE log reset +
  balancer-json cleanup preserved.

Full evidence is in `.agents/tasks/verification.md`.

### Could NOT verify here (LIVE-ONLY — the user MUST smoke-test on real Ubuntu 24.04)
- **Actually running php-fpm 7.4.33 / nginx 1.27.0 / nginx_rtmp** — the shipped binaries are Linux
  x86-64 ELF and cannot execute on this macOS/arm64 build host.
- **A true PHP 7.4 lint** — no PHP 7.4 interpreter is available here (only 8.2). The 8.2 result above
  is a stricter proxy, not proof the code "works on 7.4".
- **Full `install.py` run** on a 24.04 host (apt, MariaDB stand-up, tmpfs mount, nginx reload).
- **Stream playback / token auth** behavior of the obfuscated client-API endpoints.

### User smoke-test steps (do these on a fresh Ubuntu 24.04 server)
1. Run the one-liner in §3 and choose `MAIN`.
2. Confirm MariaDB came up and `start_services.sh` launched nginx, nginx_rtmp, and the 3 php-fpm pools.
3. Browse `http://SERVER_IP:8880` and log in with `admin` / `admin`.
4. Add a stream and confirm it plays.
5. Confirm the ODIN/line-theft whitelist still blocks after the configured wrong-attempt threshold.

---

## 4b. ODIN v46 pin + xtreamtools(dot)org removal + MaxMind GeoLite2 (this change)

### What changed and why
The base tree is already **R1 ODIN v46**. The third-party auto-updater host
`xtreamtools(dot)org` (a phone-home + encrypted update pusher that could silently
overwrite the whole panel) has been **fully removed**, the version label is
**pinned to "R1 ODIN v46"** with no "update available" banner, and GeoLite2
updates now come from **MaxMind's official endpoint** using a free license key.

- **No more `xtreamtools(dot)org` anywhere.** `grep -rn "xtreamtools(dot)org" .` returns 0.
  - `admin/functions.php`:
    - `updatePanel()` is now a **no-op** (`return false;`) — it never contacts a
      remote host and never wgets/overwrites panel files. The panel can no longer
      self-overwrite.
    - `updateGeoLite2()` now invokes the **local** MaxMind updater
      (`crons/geolite_update.php`) instead of fetching from the third-party host;
      it fails gracefully (returns false) if the updater or key is absent.
  - `admin/settings.php`: the version-check block no longer calls
    `file_get_contents()` on any remote JSON. `$rCurrent/$rInfos/$rGeoLite2/
    $rUpdatePanel` are set locally to the installed version, so the
    "`> installed`" banner branches never fire and Settings renders with no
    update link (array access is guarded, so no undefined-index fatal).
  - `check_geolite.sh`: repointed to call the local `crons/geolite_update.php`
    updater (PHP) instead of wgetting from the third-party host.
  - `pytools/balancer.py` and `pytools/fsremake.py` (the LB helper tools) had
    their third-party helper/update URLs blanked; the remote self-overwrite block
    in `fsremake.start()` was removed.

- **Version pin → "R1 ODIN v46".**
  - `admin/functions.php`: `$rEarlyAccess` set to `" ODIN v"` (with
    `$rRelease = "R1"`). The trailing `46` comes from the DB.
  - `install.py` `mysql()`: after importing `database.sql`, it now ensures the
    `admin_settings` key/value table exists and seeds
    `panel_version = '46'` and `geolite2_version = '20261016'`
    (a current-ish value so no GeoLite nag shows). NOTE: `panel_version` and
    `geolite2_version` are **rows in the `admin_settings` (type/value) table**,
    not columns in `settings` / `database.sql` — `grep -i panel_version
    database.sql` returns nothing because the 2019 base schema has no such
    column; the panel reads them from `admin_settings` via `getAdminSettings()`.

### MaxMind GeoLite2 credentials (superseded by section 7; kept short)
The edition is **GeoLite2-Country** (the only data the panel reads is the country code).
`crons/geolite_update.php` reads credentials, first match wins: env `MAXMIND_ACCOUNT_ID` /
`MAXMIND_LICENSE_KEY`; the repo file `maxmind.key` (`ACCOUNT_ID:LICENSE_KEY`, shipped in the
release ZIP, the place to rotate the key); the constants in the script (last-resort fallback).
The user approved committing the free-tier key, so no manual setup is required.
### GeoLite2 auto-update cron
`install.py` `configure()` writes a **daily** `/etc/crontab` entry (`0 4 * * *`, user
`xtreamcodes`) that runs the updater; the old weekly line is removed. The panel's own crontab
also runs it every minute with a 3-day throttle. See section 7.
### Verified for THIS change (on the build host)
- `grep -rn "xtreamtools(dot)org" .` → **0 matches**.
- `php -l` (PHP 8.2.28 — stricter-than-7.4 proxy; panel runs bundled PHP 7.4.33):
  `admin/functions.php`, `admin/settings.php`, `crons/geolite_update.php` →
  all "No syntax errors detected".
- `python3 -m py_compile install.py` → passes.
- `grep -c "0 >= \$level" admin/HTMLPurifier.standalone.php` → 0; two
  `while( $level > 0 );` present (Fix B intact).
- `php/lib/php.ini` has uncommented
  `session.save_path = "/home/xtreamcodes/iptv_xtream_codes/php/var/sessions"` (Fix C intact).
- `install.py` `makeRuntimeDirs()` present, called at top of `configure()` before
  `mount -a`/`start()`, and includes `php/var/sessions` (Fix A intact).

### LIVE-ONLY (retest on a real Ubuntu 24.04 box)
- Actual MaxMind download/extract/replace (needs a real key + network + the Linux
  `php/bin/php`, `tar`, `chattr`, `chown` — not runnable on the macOS build host).
- That Settings shows **"Installed Version R1 ODIN v46"** with no update link.
- That the daily cron fires and refreshes `GeoLite2.mmdb` as `xtreamcodes`.
- A true PHP 7.4 lint (only PHP 8.2 is available here).

---

## 5. Files changed (one line each)

Runtime binaries / config:
- `php/sbin/php-fpm` — replaced with redss PHP 7.4.33 / OpenSSL 3 build.
- `php/bin/*` — replaced with the 7.4.33 CLI/CGI/phar/pear tool set.
- `php/include/php/*` — replaced with the 7.4.33 headers.
- `php/lib/php/extensions/no-debug-non-zts-20190902/*` — added the 7.4 extension set
  (opcache/geoip/mcrypt/igbinary/ioncube_loader_lin_7.4.so .so files).
- `php/lib/php/extensions/no-debug-non-zts-20170718/` — **removed** (stale 7.2 extension dir).
- `php/*.pid` — **removed** (stale pid files).
- `php/lib/php.ini` — IonCube loader line commented out; opt-in JIT lines added; memory_limit 2048M kept.
- `php/etc/streamer.conf` — **added** from redss (dormant LB pool; not launched on MAIN).
- `nginx/sbin/nginx` — replaced with redss nginx 1.27.0.
- `nginx_rtmp/sbin/nginx_rtmp` — replaced with redss nginx 1.27.0 + nginx-http-flv-module.

PHP source (comments/brand only — no logic change):
- `crons/{crl_sync,epg,live_checker,offline_cons,servers_checker,setup_cache,stream_errors,tmp_del,users_checker,vod_cc_checker,vod_checker}.php`
  — stripped the 6-line EasyToYou decoder comment header (11 files).
- `tools/{archive,delay,panel_monitor,pipe_reader,signal_receiver,stream_monitor,watchdog_data}.php`
  — stripped the 6-line EasyToYou decoder comment header (7 files).
- `admin/functions.php` — `$rEarlyAccess` pinned to `" ODIN v"` (reverts the earlier
  `" XtreamUI v"` neutralization); `updatePanel()` gutted to a no-op; `updateGeoLite2()`
  repointed to the local MaxMind updater; all `xtreamtools(dot)org` usage removed.
- `admin/settings.php` — version-check block no longer calls `xtreamtools(dot)org`; version vars
  set locally so no panel/GeoLite "update available" banner renders. (Earlier change:
  settings-tab label `>ODIN<` → `>XtreamUI<`, anchors kept in sync, tab still toggles.)
- `check_geolite.sh` — repointed from `xtreamtools(dot)org` to the local
  `crons/geolite_update.php` (MaxMind) updater.
- `pytools/balancer.py`, `pytools/fsremake.py` — third-party helper/update URLs blanked;
  remote self-overwrite block in `fsremake.start()` removed.
- `wwwdir/configblock_odin.php` — brand comment header neutralised to "XtreamUI Line Scanners
  Blocker" and author/discord lines dropped; filename, `$attempts`, `$ips`, and both `define()`
  lines left byte-identical (load-bearing: included by the client-API endpoints).

Deleted:
- `wwwdir/readme_to_new_odinblocker.txt` — ODIN branding doc.

Scripts / new files:
- `start_services.sh` — added `rm -f php/*.pid` before start; 3 pool launches now use absolute
  `/sbin/start-stop-daemon`; BASE log reset + balancer-json cleanup kept.
- `install.py` — **new** 24.04-only, Python-3-clean hosted installer (no IonCube; placeholder repo
  URLs; pool-of-threads my.cnf; dynamic buffer pool; UFW handling; tmpfs/init.d/cron; :8880 admin
  server (in the shipped nginx.conf); robust no-op index.php sed). This change also added: `rMaxmindKey = ""` placeholder;
  `admin_settings` seed of `panel_version='46'` + `geolite2_version='20210223'` (build date of the shipped mmdb; replaced by the first update) in `mysql()`; a weekly
  GeoLite2 cron in `configure()`.
- `crons/geolite_update.php` — **new** MaxMind GeoLite2-City updater (reads key from env /
  `maxmind.key` / `install.py`; downloads + extracts tar.gz; handles chattr immutability; chowns
  xtreamcodes; no-op if no key).
- `BUILD_NOTES.md` — **new** (this file); §4b added for the ODIN v46 pin / xtreamtools(dot)org removal /
  MaxMind GeoLite2 work.

Intentionally unchanged:
- `bin/` (ffmpeg 2023 + ffmpeg_2018 fallback + ffprobe* + youtube*).
- The 3 kept php-fpm pool configs `php/etc/{VaiIb8,JdlJXm,CWcfSP}.conf`.
- `database.sql`, nginx/rtmp `.conf` files, and the obfuscated `wwwdir` client API.


## 5. Streaming pipeline fixes (verified live on Ubuntu 24.04, 2026-11-04)

The decoded `tools/` and `crons/` PHP came from an online IonCube decoder that emits many loop
conditions inverted, and moves the daemons' "respawn after loop" call inside the loop. Symptoms
before the fix: Start did nothing, ffmpeg never launched, background daemons never stayed up,
and `get.php` returned an empty 404 for every line.

Fixed (each changed line carries a `// fixed:` comment):
- `tools/stream_monitor.php`: restart loop `while (isRunning)` -> `while (!isRunning)` (the reason
  ffmpeg never started), monitoring loop and playlist-wait loop un-inverted, timeout-kill test,
  `sleep(1)` at end of outer loop.
- `tools/delay.php`, `tools/archive.php`, `crons/crl_sync.php`, `crons/offline_cons.php`,
  `crons/epg.php`, `crons/stream_errors.php`, `crons/tmp_del.php`: inverted loop conditions
  (`feof`, `readdir`, `>=` counters); `fclose` moved out of read loops.
- `tools/signal_receiver.php`, `tools/panel_monitor.php`, `tools/pipe_reader.php`,
  `tools/watchdog_data.php`: each respawned itself on every loop pass and every new copy killed
  the others, so none survived. Restored "break when the DB query fails, respawn once after the
  loop". `panel_monitor` writes the per-line marker files (`tmp/md5(username.password)`) that
  `xfirewall.php` requires; without it every line gets 404.
- `start_services.sh`: also launches `panel_monitor.php` and `watchdog_data.php` at boot.
- `admin/HTMLPurifier.standalone.php`: one more inverted `do...while` (matches upstream 4.14.0).
- `admin/functions.php`: `$rRelease = R1;` -> `"R1"` (removes an undefined-constant warning on
  every request).

Verified on the server: Start (panel button / `api.php?action=stream&sub=start&stream_ids[]=1&servers[]=1`)
launches stream_monitor + ffmpeg, segments appear in `streams/`, `get.php` returns the playlist,
and `/live/<user>/<pass>/<id>.ts` delivers h264/aac.

Operator notes:
- In the stream editor, drag **Main Server** under **Stream Source** in the Server Tree. That is
  what creates the `streams_sys` row; without it the Start button sends `server_id=0`.
- `wwwdir/api.php` reads plural parameters: `stream_ids[]` and `servers[]`, not `stream_id`/`server_id`.
- The ODIN blocker in `get.php` (and `player_api`, `portal`, `panel_api`) writes to an `odin_blocker`
  table that `database.sql` does not contain. `install.py` `mysql()` now creates it, so the
  10 failed logins/minute auto-block into `blocked_ips` works (see section 9).


## 6. Full decoder audit (142 decoder-output files) and HTMLPurifier replacement

All 142 files carrying the EasyToYou "Decoded file for php version" header (124 admin, 11 crons,
7 tools) were audited with an independent review. Report: `.agents/tasks/decoder-audit.md`
(not shipped in the zip).

Fixed in admin/ (each line marked `// fixed:`):
- `admin/stream.php`, `admin/radio.php`: on-demand server list was built from array keys
  (0,1,..) instead of the posted server IDs, so on-demand settings were saved wrong.
- `admin/bouquet_order.php`: movie and radio IDs were dropped when saving a bouquet order.
- `admin/database.php`: dropped `break`s and misplaced `gzclose`/`fclose` in the SQL/.gz import
  and the result-table renderer (infinite loop / truncated imports).

Replaced `admin/HTMLPurifier.standalone.php` and `admin/standalone/` with the OFFICIAL
HTMLPurifier 4.12.0 standalone build (same version, generated from the v4.12.0 tag with
`maintenance/generate-standalone.php`). The decoded copy, even after patching, stripped text
(`a & b < c` -> `a &amp; b `, `<b>bold</b>` -> `<b></b>`), let `<script></script>` through and
raised PHP warnings; the panel's `XSS()` runs every form value through it. The official build
reproduces the upstream reference output exactly on the test set and has no PHP 7.4-deprecated
syntax. `install.py` now deletes stale `DefinitionCache/Serializer/*.ser` caches on install.

Left unchanged (uncertain, listed in the audit report): `* 0` factors in bitrate/bandwidth maths
in `crons/users_checker.php`, `crons/servers_checker.php`, `crons/vod_checker.php`,
`crons/vod_cc_checker.php` (likely dropped constants; the original value is unknown), and a few
cosmetic empty branches.

Out of scope: the 33 goto-obfuscated files under `wwwdir/` (not decoder output; verified working
live) and `xfirewall.php`.


## 7. GeoLite2 updates (automatic + Settings button)

- `crons/geolite_update.php` downloads **GeoLite2-Country** (the edition the panel ships and
  uses; it only reads the country code) from MaxMind with the account ID / license key built
  in. A different account can be set in `maxmind.key` as `ACCOUNT_ID:LICENSE_KEY`.
- Automatic: the panel's own crontab runs every `crons/*.php` once a minute. The updater only
  downloads when `GeoLite2.mmdb` is older than 3 days, backs off 24h after HTTP 429 (MaxMind's
  daily GeoLite download limit) and 6h after other failures, and holds a lock so runs never
  overlap. `install.py` also adds a daily `/etc/crontab` entry as a safety net and runs one
  forced update in the background at the end of the install.
- Manual: Settings shows **Update now** next to the GeoLite2 version (`settings.php?geolite2`,
  which runs the updater with `force`). The version shown is MaxMind's build date.
- Each download is validated (tar extracts, file > 1 MB, MaxMind metadata marker present) and
  swapped in atomically; the file stays `chattr +i`. Log: `logs/geolite_update.log`.
- Removed from `crons/servers_checker.php`: the legacy daily `wget` of
  `http://downloads.xtream-codes.com/v2/GeoLite2.mmdb` (defunct third-party domain).


## 8. Clients dropped after a few seconds (connections show 0)

`crons/users_checker.php` (every minute) checks each live connection with
`ps_running(pid, "php-fpm")`, which reads `/proc/<php-fpm worker>/exe`. php-fpm workers run as
`xtreamcodes` after a setuid from root, which makes them non-dumpable, so `/proc/<pid>/exe` is
root-only and the check always failed: every TS client was closed as "Closed UnExp" at the next
cron run. REDSS's pool configs carry `process.dumpable = yes`; it was missing from the three MAIN
pools here (`php/etc/VaiIb8.conf`, `JdlJXm.conf`, `CWcfSP.conf`) and is now added.
## 9. Runtime-configuration parity with the reference builds (REDSS / BASE)

An exhaustive audit compared this tree with REDSS and BASE (php.ini, php-fpm pools, extensions,
nginx, nginx_rtmp, scripts, installer, crons, python helpers, directory layout). Every difference
was classified MUST-APPLY or INTENTIONAL-DIFFERENCE with evidence (no "cosmetic" verdicts). Reports:
`.agents/tasks/parity/` (not shipped).

Applied (missing from this build before):
- `admin/tmdb.php`: removed the gettext `_()` call (the bundled PHP 7.4 has no gettext; it crashed
  the TMDB error path).
- `start_services.sh` and `install.py makeRuntimeDirs()`: create `php/var/{sessions,log,run}`,
  `created_channels`, `movies`, `delay`, `adtools/{backups,balancer}`, `admin/icons`
  (`admin/resize.php` writes its icon cache there; without it every icon request emits a PHP
  warning into the PNG) and `nginx_rtmp/*_temp`, before the recursive chown.
- `php/etc/streamer.conf`: `error_log` on an existing path.
- `nginx_rtmp/conf/nginx.conf`: RTMP hooks use `127.0.0.1` instead of `localhost`.
- `php/lib/php.ini`: removed misleading PHP 8-only JIT comments. `php/lib/php/` PEAR tree and
  `php/php/` synced from REDSS to match the 7.4 binaries.
- `odin_blocker` table created by the installer (`wwwdir/{get,player_api,panel_api,portal}.php`
  insert into it on failed logins; 10 failures/min from a non-whitelisted IP auto-adds the IP to
  `blocked_ips`). It was missing, so ODIN's brute-force protection never worked. `127.0.0.1` is now
  in the `wwwdir/configblock_odin.php` whitelist.
- `/etc/hosts`: the bare `xtream-codes.com` entry was never written (the guard matched the
  `api.`/`downloads.` lines); fixed in `install.py` and `pytools/fsremake.py`.
- nginx ISP server block on `:8805` (what `wwwdir/includes/streaming.php` calls via
  `api.xtream-codes.com:8805`, mapped to 127.0.0.1), MAIN and LB; both locations carry
  `allow 127.0.0.1; deny all;`.
- Packages `iptables cron sudo libfreetype6 libsqlite3-0` plus an `ldd` check of php/php-fpm.
- Python 2 to 3 port of `config.py` and `pytools/{config,balancer,sreload,fsremake,release}.py`
  (24.04 has no Python 2; the balancer/Servers-page jobs depend on them).
- `ulimit -n 262144` in `start_services.sh` (inherited by the daemons it starts).
- `maxmind.key` shipped; Settings "Update now" requires the `adv/settings` permission;
  `check_geolite.sh` runs the updater as `xtreamcodes`.

Deliberately NOT applied:
- No `/etc/sysctl.d` or `/etc/security/limits.d` files and no replacement `/etc/init.d/xtreamcodes`:
  neither REDSS nor BASE has them, they only affect login sessions / are unverified, and the
  services already set their own limits (`worker_rlimit_nofile`, `rlimit_files`).
- No sudoers grant for `nginx -s reload`. `xtreamcodes` owns the nginx binaries (the tree is 0777),
  so the grant would be root-equivalent. The panel's "change port" reload therefore needs a full
  `start_services.sh`, exactly as in BASE/REDSS. To opt in anyway: `XC_SUDO_NGINX_RELOAD=Y python3 install.py`.
- No database prompt. The installer always drops and recreates `xtream_iptvpro`, as every earlier
  version did. To re-run the installer over an existing install without wiping data:
  `XC_DROP_DB=N python3 install.py`.

- `max_statement_time = 0` (was REDSS's `100`). REDSS kills any query over 100s as a runaway guard,
  but a large DB restore/import (2 GB uncompressed here) can legitimately run past that and get
  killed mid-way, leaving a half-loaded database. Set to 0 (unlimited) so backups and imports of a
  big DB complete. Everything else in red's my.cnf is unchanged.

Kept on purpose (differ from REDSS, match BASE): `max_input_vars=5000`, `max_input_time=60`,
`max_execution_time=60`, `memory_limit=2048M`, `file_uploads=On`, `upload_max_filesize=3M`
(REDSS's smaller values truncate big bouquet forms and break stream/backup uploads),
`opcache.blacklist_filename` for the admin dir, and BASE's `php/GeoIP.dat` (REDSS's file is a
GeoLite2 MMDB that `libGeoIP` cannot read).

Performance tuning (admin-only main server; streaming/VOD runs on LB nodes, so ffmpeg is idle here
and was NOT swapped):
- php.ini opcache: `opcache.enable=1` was only an implicit default and is now explicit;
  `opcache.validate_timestamps=1` + `revalidate_freq=2`; `opcache.huge_code_pages=1`. Memory (512M) /
  file count (130987) were already set by BASE.
  IMPORTANT: validate_timestamps MUST stay 1. An earlier build set it to 0 for a small perf gain, but
  the panel caches live/VOD data as PHP files (tmp/*_main.php, bouquets_cache.php, categories_bouq)
  loaded via include(). With timestamps off, php-fpm compiles those once and never re-reads them, so a
  stream/bouquet added in the admin never reaches get.php / player_api until a full php-fpm restart
  (this manifested as "only the first stream shows in the m3u"). revalidate_freq=2 re-stats a file at
  most once every 2 seconds per worker (negligible) and lets admin changes appear within ~2s automatically.
  Changes to PHP files are picked up within about 2 seconds; to apply one instantly run
  `pkill -USR2 -f "php-fpm: master"` as root (graceful reload). It also shortens the playlist delay:
  setup_cache.php (cron, every minute) writes the cache as PHP files that are include()d, so with 60s a
  rebuilt cache could wait up to another 60s; now new streams reach apps within about 1 minute.
  Run setup_cache.php manually to publish new streams instantly.
- php.ini realpath cache: `realpath_cache_size=4096k`, `realpath_cache_ttl=600` (were commented/16k);
  the panel resolves the same long paths every request, so caching cuts syscalls.
- my.cnf `innodb_log_file_size=512M` (red did not set it): larger redo log batches more writes before a
  checkpoint flush under write load. Safe on Ubuntu 24.04's MariaDB 10.11 -- it resizes/recreates the
  redo log on restart (dynamic since 10.9), it does not refuse to start like old MySQL 5.x.
- FPM pools left as `pm=ondemand` with high ceilings on purpose: ondemand spawns workers only when
  needed and reaps them when idle, so the high `max_children` costs nothing at rest and auto-scales to
  the box. Lowering it or switching to `static` would cap concurrency or hold idle workers. Not changed.

Cache refresh cron (fixes "new streams never appear in the m3u"): start_services.sh runs
`crons/setup_cache.php` only ONCE at boot. The playlist/stream cache (tmp/*_main.php,
categories_bouq, bouquets_cache.php) is served by get.php and is NOT rebuilt from the DB on every
request. Without a recurring job, a stream or bouquet added through the admin updates the DB but
never reaches the generated m3u until a full restart. The installer now adds a per-minute
`xtreamcodes` crontab entry for setup_cache.php (stock cadence; it only rewrites a cache file when
its md5 changed, so it is cheap). smoke_test.py checks the entry is present.

Decoder defect - dropped `$rStream = $rArray` fallback (admin save warning): `admin/stream.php`
and `admin/radio.php` warned `Invalid argument supplied for foreach()` when saving a stream/radio
entry on certain POST paths. REDSS source has an unconditional-ish `$rStream = $rArray` fallback
before the `if (isset($_STATUS)) { foreach ($rStream ...) }` normaliser; the decoder dropped it, so
on some save paths the variable was unset and the foreach warned. The save still completed (the
warning is cosmetic) but it was logged on every stream edit. Fixed by guarding the foreach to fall
back to `$rArray` / `array()`. Symptom reported as "editing an on-demand stream throws an error even
though the stream works" - it was this admin-save warning, NOT a streaming/ffmpeg failure.

Systematic decoder-defect sweep (vs REDSS twins + signature scan, two-model reviewed): all 141
decoder-output files (123 admin, 11 crons, 7 tools) were semantic-diffed against the clean REDSS
source (105 twins) or signature-scanned (36 ODIN-only). Result: the build was already clean except
ONE new defect -- `admin/tmdb_release.php` `parseTitle()`: the decoder replaced a loop `break` with
an early `return` and dropped the post-loop `$return = trim($return); return $return;`, so the
function returned null on normal completion (VOD/movie title parsing came back blank for messy
filenames). Also `parseLanguage()` had a dropped inner `break` that could falsely trip MULTI.
Restored to match REDSS. The 4 float crons got the required `// fixed:` markers added (no value
change). All prior fixes re-verified against REDSS and intact. The 33 goto-obfuscated wwwdir runtime
files were not touched. Flagged-not-fixed (ambiguous, no reference): json_decode foreach in
fetch_record.php and movie_info.php (ODIN-only). Report: .agents/tasks/decoder-sweep.md.
NOTE: lint on the mac host used system PHP 8.2 as a proxy; the canonical PHP 7.4 lint
(php/bin/php -l) and runtime tests must still run on the Ubuntu server before production cutover.

Not verifiable from the build machine (macOS): `nginx -t`, `php-fpm -t`, `ldd`, and the runtime
behaviour of every installer step. Server checks: `.agents/tasks/parity/server-commands.md`.
`sub_FINAL.zip` (LB) does not exist yet.

## Custom nginx.conf (new installs only)
BASE `nginx/conf/nginx.conf` is the operator's customised config and is one identical file for every
install (`server_name _;` on the stream and panel blocks). Existing installs are not touched.
- **Default ports:** streams HTTP 8080 + HTTPS 443; panel (admin) HTTP 8880 + HTTPS 2053; ISP 8805
  (localhost only); RTMP 25462 (unchanged); MariaDB 7999. The old 25461, 25463 and 25500 are gone from the
  installer (UFW option, printed URLs, `streaming_servers` ports 8080/443) and from `nginx_rtmp` hooks
  (now `127.0.0.1:8080`).
- **Panel block** has `index index.php index.html index.htm;` so `/` loads.
- **ISP block:** `allow 127.0.0.1; deny all;` in both `location /` and `location ~ \.php$`.
- **TLS:** `ssl_protocols TLSv1.2 TLSv1.3;` on both ssl listeners (443, 2053).
- **Includes:** `nginx/conf/blacklist.conf` (shipped, absolute path include in stream and panel blocks).
- **Certificates:** the config uses `cloud_ssl_cer.cer` / `cloud_ssl_key.key` in `nginx/conf/`. None are shipped.
  If both are missing the installer (MAIN) creates a self-signed placeholder (`openssl req -x509`, 10 years,
  CN=localhost, key mode 600, owner xtreamcodes), prints a reminder and writes it to `/root/credentials.txt`.
  Existing files are never overwritten; if only one exists it warns. Without openssl it falls back to the
  shipped `server.crt`/`server.key` (public key, replace ASAP).
  To replace: copy the Cloudflare Origin certificate and key over those two files, then run
  `/home/xtreamcodes/iptv_xtream_codes/start_services.sh`.
- **Cloudflare SSL mode:** Full works with the placeholder; Full (strict) needs the real Origin certificate (526 otherwise).
- **origin-pull-ca.pem** is unused (no `ssl_client_certificate` / `ssl_verify_client`).
- `smoke_test.py` expects ports 8080, 443, 8880, 2053, 8805, 7999.
- **Cloudflare real IP:** `set_real_ip_from` for the Cloudflare ranges plus `real_ip_header CF-Connecting-IP;`, so logs,
  limits and the ISP lookup see the client IP, not Cloudflare's.
- **Server names:** `server_name _;` on the stream and panel blocks. The blocks are told apart by port, not by name.
- **Differs from REDSS on purpose:** BASE `nginx.conf` no longer matches REDSS (ports, TLS, real IP, blacklist, ISP lock).
- **Existing panels:** the ISP 8805 lock is not applied automatically. Add `allow 127.0.0.1; deny all;` inside the
  `location ~ \.php$` block of the 8805 server, then reload nginx.
- Certificates are per domain and are never shipped in the zip.

## 10. Recent adoptions and improvements (2026-11-12)

### 10.1 Duplicate prevention
Root cause: the `streams` table has no unique key, and the M3U import pages inserted without checking.
- `admin/vod_import.php` and `admin/episode_import.php`: before the INSERT they load the existing `stream_source`
  values for type 2 (movies) / type 5 (episodes), `json_decode` each, and skip the entry if the M3U URL, or its
  space-to-`%20` form, already exists. This is the same method REDSS `movie.php` uses. The URL is appended to the list
  after each insert, so one batch cannot insert the same entry twice. Empty URLs are skipped. The INSERT statements
  are otherwise unchanged.
- `crons/watch_folder.php`: after TMDB resolves the title, a movie (type 2) is skipped if a stream with the same
  `stream_display_name` exists. An episode (type 5) is skipped if `series_episodes` already has the same
  `series_id` + `season_num` + `sort` (episode number). If season/episode are unknown, it falls back to the display name
  within the same series only. Skips are written to `watch_output` with status 1 and the existing stream id.
  The file-path check at the top is unchanged.
- This does NOT remove existing duplicates. Cleanup is a manual SQL step (keep `MAX(id)` per name) after a DB backup.
- `admin/episode.php` (adopted from REDSS, matching `movie.php` / `stream.php`): the column list is wrapped in
  `ESC()`; `enable_transcode` is reset to 0 when the transcode profile is cleared; `probesize_ondemand` defaults to 256000.

### 10.2 isp/api.php rewrite
Rewritten as readable PHP with the same output contract as before.
- Strict IP validation; one cache file per IP at `isp/data/<md5(ip)>`, seeded with 10,340 entries from `apibackup.txt`
  (11 invalid-JSON lines and 5 duplicate IPs skipped).
- JSON is built with `json_encode`; upstream timeout is about 3 s; exact IP match (no substring false match);
  cache writes are atomic; it degrades gracefully if `data/` is not writable.
- Removed the unused `api2.php` .. `api5.php` and `api.php(option two)`. `apibackup.txt` stays in place and is not read.

### 10.3 install.py
- `streaming_servers` defaults: http 8080, https 443, rtmp 25462.
- UFW option 2 opens 22, 80, 443, 8080, 8880, 2053, 25462, 31210 (plus 7999 on MAIN). It no longer opens
  25461, 25463, 25500 or 8805.
- No duplicate admin block (guarded on `listen 8880;`).
- Placeholder `cloud_ssl_cer.cer` / `cloud_ssl_key.key` in `nginx/conf/` are created only if BOTH are missing (never
  overwritten; warns if only one exists). A reminder to replace them with the Cloudflare Origin certificate, then run
  `start_services.sh`, is printed and saved. Cloudflare SSL mode Full works with the placeholder; Full (strict) needs
  the real certificate. `origin-pull-ca.pem` is not used.
- The printed admin URL is `http://IP:8880` (https on 2053).

### 10.4 admin/settings.php speed and Ads/Infos tab
The page was slow because the hidden "Ads and Infos" tab embedded about 3.5 MB of base64 images, and nginx has gzip off.
All Odin ads, links and images were removed from that tab and replaced by one "Contact on Telegram" button
(`https://t.me/prabhjd`, opens in a new tab). File size 3.67 MB to 159 KB. Settings fields, the save handler and the
other tabs are byte-identical.

### 10.5 Decisions recorded (not adopted, on purpose)
- `server_info.url` keeps using the request host (better for several domains / CDN) instead of REDSS's `domain_name`.
- No new DB index on `streams(stream_display_name)`, to avoid touching the live DB.
- PHP `memory_limit` stays 2048M.
- REDSS `file_uploads=Off` and its low `max_input_vars` must not be copied: they break M3U upload, DB restore and big forms.
- The `lbznuff/` LB payload and `sub_FINAL.zip` are out of scope for now.

### 10.6 Release and distribution
- `main_FINAL.zip` is a GitHub release asset; the installer downloads `releases/latest/download/main_FINAL.zip`.
  `install.py` is fetched from raw `main`.
- Zip entries are stored as `iptv_xtream_codes/<path>`. The zip is rebuilt by copying entries from the previous zip and
  replacing only the changed files (Python `zipfile`, `ZIP_DEFLATED`, `allowZip64`), then checking markers and `testzip()`.
- Panel PHP files are NOT committed to the repo. Only the zip asset carries them.

### 10.7 Operations notes
- `rclone-vfs-mount-refresh.timer` moved from every 3 hours to a daily `OnCalendar` at 05:00 UTC, to save Google Drive
  API requests (the mount already has `dir-cache-time 8760h` and `poll-interval 15s`). If the `vod_heal` daily cron
  exists, run it after the refresh (for example 06:30).
- A watch folder with "probe input files" off does not read media from Google Drive.
- Check for Google throttling:
  ```sh
  zgrep -hiE "googleapi|ratelimitexceeded|quotaexceeded|error 403" /var/log/syslog*
  ```
  rclone at `-v` hides retried errors, so the Cloud Console Drive API metrics are the authoritative source.

### 10.8 vod_heal.py
Lives on the `vod-heal` branch (see its README). Current version is R (2026-11-12-R). It reads DB settings from the panel's own config and
loads panel ids/years automatically. On `--apply` it updates `target_container` and `stream_source` in the DB. `--review`
gives interactive decisions, `--cleanup` is available, and the dry run lists every link it would repair.
Versions O to R added:
- Panel years: movies use the year of `movie_propeties` `releasedate`; episodes use the series year (`series.releaseDate`),
  because show folders are named by the series year.
- Panel file type (`target_container`) is now fixed by the normal dry run / `--apply`. The dry run shows a
  "FILE TYPE IN PANEL" section. `--no-fix-containers` skips this step; `--fix-containers` still works on its own
  (whole library).
- pymysql on Ubuntu 24.04: `apt install -y python3-pymysql` (as root). The script prints this hint when pymysql is missing.
### 10.9 Post-install checks
- nginx is running.
- `http://IP:8880` opens the login page.
- A stream plays on port 8080.
- The certificate reminder was shown; replace the placeholder certificates with the real ones.
- Import the same M3U twice: the second import adds nothing.
- Provider/country show on the connections page (`isp/api.php` works).

## 11. EPG auto-assign (links EPG to live channels from the existing providers)
User guide: [EPG_AUTO_ASSIGN.md](EPG_AUTO_ASSIGN.md).

### 11.1 What it does
- Card **Auto-assign EPG** on Management, Service Setups, EPGs. Default Off.
- Links only channels with no working EPG link, and only when the cleaned channel name matches exactly one provider channel
  (country hints respected, provider priority list decides ties). Anything unsure is listed for review, never guessed.
- Works with any number of providers; adding or deleting providers needs no change. Channels linked to a deleted provider are
  re-assigned (Auto-assign On). Dead links (channel gone from a live provider) wait for 3 consecutive cron runs by default.
- Manual fix in the channel editor, EPG tab: Quick Search across all providers, Suggested, Clear EPG. Streams list and mass
  edit have a **No EPG** filter and Clear EPG. Preview, Assign now, CSV report, Review ambiguous, Undo
  (`php tools/epg_assign.php --undo=logs/epg_auto/changes_<time>.tsv`).
- Excluded categories (cameras, CCTV, private) are never touched; a warning counts linked channels in them.

### 11.2 Change set vs the pre-EPG build
- New: `admin/epg_auto.php`, `admin/epg_auto_api.php`, `admin/assets/js/epg_auto.js`, `tools/epg_assign.php`.
- Changed: `admin/api.php`, `admin/epgs.php`, `admin/functions.php`, `admin/stream.php`, `admin/stream_mass.php`,
  `admin/streams.php`, `admin/table_search.php`, `crons/epg.php`, `database.sql` (`epg_data` block only).
- `crons/watch_folder.php`: line endings restored to CRLF (differs from the pre-EPG build by CR bytes only).
- Not touched: `wwwdir/`, `lbznuff/`, `php.ini`, nginx configs, `install.py`, other crons.

### 11.3 Zero impact when the feature is Off
- Admin pages run the same queries as before (statement counts compared old vs new for every touched page).
- The cron stores the same guide as before for channels with a correct language, apart from the intended differences below.
- Streaming and the apps are not involved.

### 11.4 Intended behaviour differences
- The EPG update writes only the difference (window replace) instead of re-inserting everything and de-duplicating. Corrected,
  moved or removed programmes follow the provider; a down or empty provider leaves stored programmes alone.
- **Force EPG Reload** no longer truncates the programme table; it runs the same update.
- Title fallback: if `epg_lang` is not found in a programme, the first title is used instead of an empty one.
- `epg_lang` of `''` or `'NULL'` is treated as no language.
- `admin/stream.php` stores NULL (not the text "NULL") for an empty `epg_lang`.
- `epg_data` gets index `epg_chan_start (epg_id, channel_id, start)` and `id` BIGINT, migrated once by `crons/epg.php`
  (log: `logs/epg_migrate.log`). Exact SQL and dump/restore results are in [EPG_AUTO_ASSIGN.md](EPG_AUTO_ASSIGN.md#upgrade-and-migration).
- With Auto-assign On: cleared channels stay cleared (opt-out list), unused providers' programmes are pruned (max 200,000 rows
  per update), stricter country-aware matching, optional preferred EPG language. The fingerprint format changed once, so
  there is one extra cron run after the upgrade.

### 11.5 Measured numbers (MySQL 8.0 / MariaDB, test machine)
- Daily cron 33% to 62% faster, 7x to 14x fewer rows written; a repeated run with the same feed writes nothing and does not
  consume ids. Only the very first load into an empty table is 0% to 4% slower.
- Programme lookup by channel and time about 2x faster with the new index.
- Bulk assign of 12k streams against 5 providers: about 3 s and 156 MB.
- Migration on about 80,000 rows: about 1 s. Cron peak memory 1.3 to 1.5 GB at 15,000 channels / 571k programmes.

### 11.6 Not implemented, and why
- `xmltv.php` static cache (D4): the file is obfuscated and was not touched. The write side is now small; the read side is unchanged.
- Cron schedule change (D6): kept at `0 1 * * *`. A new run kills the previous one, so keep the interval well above the run time.

### 11.7 Not verified
- PHP 7.4 at runtime (tested on PHP 8.2 plus a 7.4 syntax check).
- MariaDB 10.x (tested on a newer MariaDB and MySQL 8.0; the statements used are standard for 10.x).
- The obfuscated `wwwdir` readers (xmltv, player_api): covered by queries of the same shape.
- A real browser (tested with jsdom only).

### 11.8 Post-install checks for EPG
- The 01:00 EPG update finishes (check `logs/epg_migrate.log` after the first run and time one run on your server).
- The guide shows in an app for a linked channel.
- Exclude camera / CCTV / private categories before the first run.
- Press **Preview** before **Assign now**.
### 11.9 EPG auto-assign: accuracy round
Matching quality was reworked after a test on a real list of 12,651 live channels and two large providers. Docs: [EPG_AUTO_ASSIGN.md](EPG_AUTO_ASSIGN.md#accuracy-update).

**Root causes found**
- Provider tags were never cleaned: names ending in " US", ids ending in `.us2`, `.ca2`, `.us_locals1`. The two sides never produced the same key.
- US local stations (about 1,800 channels) can only be linked by call sign, and the engine had no call-sign logic.
- Country hints were read wrongly: US state codes were read as countries (`CA |` Canada, `IN |` India, `AL |` Albania), `USA`, `US`, `PT`, `BR`, `LA`, `CARIB` were not read, and the category hint was empty for categories like CABLE, NEWS, LOCAL - NBC, ALL LATIN. With no country, the cross-country rule made most matches ambiguous, or picked a wrong-country copy.
- About 47% of the list can never have a normal guide (24/7 loops, event and game slots, PPV, adult, cameras, blank names) and was mixed into the numbers.

**What changed**
- Provider tag cleanup, call-sign matching (US and CA), league/team and alias tiers, feed variants (East/West), country prefixes, state codes read as states, home country (default `us`).
- Not EPG-able classifier (loop, event, PPV, adult, cam, empty). Never linked, shown as its own number.
- Every unsure channel gets a reason, in the Review list and in the CSV (`reason`, `reason_text`). Card shows Assigned / Needs review / No match in your providers / Not EPG-able. Found-vs-written diagnostic when matches were found but not written.
- New settings (same `epg_auto_` prefix and settings table, no schema change): `tag_map`, `cat_map`, `home_cc`, `carib_us`, `noepg_cats`, `noepg_off`, `noepg_suggest`, `last_reasons`.
- One-click category accept is built and tested but dormant (the allowed-reason list is empty until reasons are measured as safe).

**Files changed this round**
- `admin/epg_auto.php`, `admin/epg_auto_api.php`, `admin/assets/js/epg_auto.js`, `tools/epg_assign.php`
- New: `admin/epg_auto_data.php` (data only: tag map, networks, aliases, event words; loaded only when a run starts)
- `crons/epg.php` and all other files are unchanged. No schema change. `epg.data` is unchanged.

**Measured before / after** (12,651 channels, two real providers)
- Assigned 378 -> 3,023. Needs review 335 -> 752. Not EPG-able 5,917.
- Precision 78.9% -> 99.3% on a 342-row labelled set. The rules were tuned on this set, so this is optimistic.
- Coverage of matchable channels 9.7% -> 89.7%; 92.3% if the first review suggestion is accepted per row.
- Existing-link check: 502 of 562 links the engine linked again were the same channel; 31 existing links were flagged as likely wrong.

**Performance**
- Bulk run about 1.2x the old time, about 200 MB. Cron hook with nothing changed: 9 ms, same as before. Feature Off: pages run the same statements (16/16).

**Tests**
- All suites pass. 10 failures in `itest7` are pre-existing and identical with the old engine (cron fixtures, untouched code).
- PHP 7.4 was checked for grammar only, not run.

**Limits**
- An independent hold-out set is not labelled yet, so the precision numbers are not independent.
- One-click category accept is dormant until reasons are measured.
- Very large providers (for example a 1.9 GB XMLTV) are loaded fully by the existing `crons/epg.php` and need several GB of RAM. Smaller per-country files are lighter.

## 12. Gzip for panel list responses (nginx only)
Shipped in `main_FINAL.zip`. Only `nginx/conf/nginx.conf` changed: 81 lines added, 0 removed. No PHP, config, `install.py` or
`database.sql` change.

### 12.1 What changed
- Four exact-match locations in the stream server (ports 8080 / 443): `/player_api.php`, `/get.php`, `/xmltv.php`, `/panel_api.php`.
  Each is a copy of the `location ~ \.php$` block plus: `gzip on; gzip_comp_level 5; gzip_min_length 1024; gzip_proxied any;
  gzip_vary on; gzip_types application/json application/xml application/octet-stream;`.
- `gzip off;` in `http{}` is unchanged. The admin panel (8880 / 2053) and the ISP server (8805) are unchanged.
- `gzip_types` match what the scripts send: `player_api.php` JSON, `xmltv.php` XML, `get.php` `application/octet-stream`,
  `panel_api.php` the PHP default `text/html` (nginx always compresses that). `application/octet-stream` is listed only inside
  these four blocks, so static files are not affected.
- No PHP script compresses its own output and `zlib.output_compression` is Off, so nothing is compressed twice.

### 12.2 Behaviour
- nginx compresses only when the client sends `Accept-Encoding: gzip`. Other clients get identical bytes, `Content-Length` and keep-alive as before.
- Compressed responses have no `Content-Length` (the config has `chunked_transfer_encoding off`), so they end when the
  connection closes. All tested HTTP clients handle this; a progress bar may not know the total size.
- HTTP/1.0 requests and HEAD requests are not compressed.
- Video is never compressed. `/live`, `/movie`, `/series`, `/hls`, `/timeshift` are rewritten to `/streaming/*.php` before location
  matching and cannot match the four exact URLs. All of them and static `.mkv` / `.ts` were tested with gzip, deflate and
  identity: no `Content-Encoding`, body identical to the source. Range requests still return 206 with the right bytes.

### 12.3 Measured (nginx 1.27.0, synthetic data shaped like the panel, level 5)
| Response | Plain | Gzipped |
|---|---|---|
| VOD list (`get_vod_streams`) | 28.9 MB | 5.8 MB |
| M3U (`get.php`) | 57.5 MB | 7.9 MB |
| EPG (`xmltv.php`) | 31.1 MB | 4.6 MB |
- The test data repeats a small vocabulary. Expect about 4-8x on real data, not the 5-12x seen here.
- Level 5 is kept: level 1 is about 17-20% larger for half the CPU, level 6 saves only 5-12% more for about twice the CPU.
  Expect roughly 0.5-0.7 s of one core per full M3U download. If CPU gets tight during mass refreshes, `gzip_comp_level 1` still gives about 4-6x.
- The bundled nginx is a Linux binary, so the test used nginx 1.27.0 built from source (same version), PHP-FPM with stub scripts
  that send the same headers as the real ones, and real OkHttp, Apple URLSession, python-requests and curl clients.

### 12.4 Cloudflare
- Cloudflare asks the origin for gzip; `gzip_proxied any` lets nginx answer it.
- Cloudflare does not compress `application/octet-stream`, so `get.php` (M3U) is now compressed through Cloudflare for the first time.
- Traffic from the origin to Cloudflare is about 5x lower for all four URLs.

### 12.5 App support
- Benefit (send `Accept-Encoding: gzip` and unpack it): IPTV Smarters Android / iOS, XCIPTV, TiviMate, OTT Navigator, Kodi (PVR IPTV Simple), XStreamity.
- Unaffected (send no `Accept-Encoding`): e2m3u2bouquet, MAG / Stalker boxes, old smart-TV apps.
- Unverified: VLC, GSE, Smart IPTV, SS IPTV, Flix IPTV.
- No app was found that breaks. That is a search result, not a guarantee. The only possible failure is an app that sets
  `Accept-Encoding: gzip` by hand and then does not unpack the reply. Use the diagnostic and the rollback below if one shows up.

### 12.6 WARNING: nginx upgrades
On nginx 1.30 and later, `fastcgi_keep_conn on;` combined with gzip made PHP-FPM workers hang (each gzip request leaked one FPM
connection until all workers were stuck; seen on 1.31.8). The panel ships nginx **1.27.0**, tested OK: 0 stalls in 120 mixed requests.
**Before any nginx upgrade, remove `fastcgi_keep_conn on;` from the four new blocks.** With it removed, 1.31.8 also showed 0 stalls.

### 12.7 Apply to an existing panel
In `/home/xtreamcodes/iptv_xtream_codes/nginx/conf/nginx.conf`, in the first `server {}` block (the one with `listen 8080;`),
paste the four blocks right after `location /statusvideo { ... }` and before `location ~ \.php$ {`. The shipped file has them;
copy them from there. Each block looks like this (repeat for `/get.php`, `/xmltv.php`, `/panel_api.php`):
```nginx
location = /player_api.php {
	limit_req zone=one burst=8;
	try_files $uri =404;
	gzip on;
	gzip_comp_level 5;
	gzip_min_length 1024;
	gzip_proxied any;
	gzip_vary on;
	gzip_types application/json application/xml application/octet-stream;
	# the remaining lines are the same as in the location ~ \.php$ block
	# (fastcgi_pass, fastcgi_buffers, fastcgi_keep_conn, fastcgi_param ...)
}
```
Then reload (no downtime, running streams are not cut):
```sh
/home/xtreamcodes/iptv_xtream_codes/nginx/sbin/nginx -t && /home/xtreamcodes/iptv_xtream_codes/nginx/sbin/nginx -s reload
```

### 12.8 Live checks
```sh
curl -s -o /dev/null -D - -H 'Accept-Encoding: gzip' 'http://HOST:8080/player_api.php?username=U&password=P&action=get_live_streams' | grep -iE 'content-encoding|vary'
curl -s -o /dev/null -D - -H 'Accept-Encoding: gzip' 'http://HOST:8080/movie/U/P/123.mkv' | grep -ic content-encoding
```
The first must show `Content-Encoding: gzip` and `Vary: Accept-Encoding`. The second (a movie URL) must print 0.

### 12.9 Rollback
Delete the four blocks, or change `gzip on;` to `gzip off;` inside them, then run the same `nginx -t && nginx -s reload` command.

### 12.10 Optional one-day diagnostic: which apps send Accept-Encoding
- Add `log_format gzdiag '$time_local|$uri|$http_accept_encoding|$http_user_agent|$sent_http_content_encoding|$body_bytes_sent';`
  inside `http {}`, and `access_log /home/xtreamcodes/iptv_xtream_codes/logs/gzdiag.log gzdiag;` inside each of the four blocks. Reload.
- Only `$uri` is logged, not the query string, so no passwords are written.
- After a day, count by app (user agent) and by whether it sent gzip and got `Content-Encoding`. Then remove the `log_format`
  and the four `access_log` lines, reload, and delete the log file.

## 13. Streaming settings guidance (advice, no code change)
- **VOD Download Speed** (`vod_bitrate_plus`) is a **percent** added on top of each movie's known bitrate, not kbps, despite its
  tooltip. Confirmed in `clients_movie.php`: the base rate is `bitrate * 125` bytes/s, then `+= bitrate * vod_bitrate_plus * 0.01`.
  - `0` = the movie is sent at exactly its own bitrate, so the player's buffer never builds.
  - For a 1 Gbps VOD server with about 50 busy-hour viewers: start at **50**, raise to **100** if network out stays well below
    about 800 Mbps at peak. Avoid 200.
  - Movies with no known bitrate are not throttled at all.
- **VOD Download Limit** (`vod_limit_at`) sets the point (a percentage of the file) after which throttling starts. What `0` means is unverified.
- **Live:** Client Prebuffer 30, Use Nginx Buffer off. Change and test one at a time.
- **Live Connections status colour** shows divergence: green up to 10%, yellow 11-50%, red over 50% of data delivered below the
  stream bitrate. Streams with no known bitrate always show green.
- **High-bitrate files** (20-90 Mbps 4K): give them separate 4K categories / packages. Per-viewer adaptive quality is not supported
  by the apps or the panel for VOD without heavy transcoding.

## 14. Roadmap (planned, NOT built)

### 14.1 Planned: multi-provider restream sources
Nothing here is implemented. The plain-English challenge list is in `PROVIDER_CHALLENGES.md`; the technical findings live outside this repo.

Problems to solve:
1. Finding a channel on each provider is manual.
2. We do not know if a provider's copy plays until it is tested by hand.
3. The panel always tries source 1 first.
4. We do not know which provider is good for a channel until customers complain.
5. Providers differ in size and connection limits.
6. Providers add and remove channels.
7. Connections are used unevenly (one provider full, another idle).
8. We do not know which channels are watched most (cold starts on on-demand channels, idle always-on channels).
9. The panel only fails over on hard failures, not on buffering or freezing.
10. We cannot tell when a provider is full.

Phases (built like EPG auto-assign: Preview first, undo, nothing touches manual links):
- **P0:** most-viewed report and provider usage view (read-only).
- **P1:** provider M3U import; auto-fill sources with the EPG matcher; channel checker that uses only spare connections; dead-source cleanup and alerts.
- **P2:** best source first, ordered from passive health scores.
- **P3:** load spreading by free provider connections; on-demand / always-on switching.
- **P4:** auto-switch when a playing source stalls.

Open questions: is "Save closed connection logs to database" on and how many days of history exist; what one provider M3U line looks like
(use XXXX placeholders); does a full provider give an error or a "limit reached" video; should new provider channels be created or only listed;
main server upload speed and number of LBs pulling from it. Choosing the provider at the exact start moment needs a change in an obfuscated file or a workaround.

### 14.2 minimus.tv comparison
Items worth adopting later: compressed lists (done, section 12); better attack blocking (shared-IP aware, temporary escalating blocks
on all servers, real client IP, count failures on `get.php` / `portal.php`); adding a server to all channels in one step.

## 15. GTB mods rebrand, cleanup and series duplicate fix
Shipped in the zip only (panel PHP is never committed). Zip rebuilt from the previous build: 284,829,606 bytes (was 285,139,019), `testzip()` clean.
- **Rebrand to "GTB mods":** Settings shows "Installed Version GTB v8" (was R1 ODIN v46). The footer reads "Xtream UI - GTB mods v8". `panel_version` logic is untouched. The ODIN names in the settings tab, login 2FA issuer, tables, radio/stream pages, language files (en, fr, es, pt, it), `database.sql` default server name, SecTools text and `install.py` banners became GTB mods / Xtream UI.
- **Logo:** the 666x172 "odin" wordmark with the Viking (header, login, sidebar, 146x172 small logo, 1025x257 wide logo, 48x48 favicon) was replaced by the Ghostbusters logo. The outer white is transparent and the ghost stays white. The wide logos add red "GTB mods" text. The small logo and favicon are icon only. Pixel sizes are unchanged.
- **Community tab:** new Settings tab with Telegram and Discord (https://discord.gg/xYPWB2Gysd) buttons, an optional Videos button and a short feature list. The links are editable (`community_telegram`, `community_discord`, `community_videos` in `admin_settings`, http(s) only).
- **Cleanup:** the unused leftover `isp/api.php(don t work with https certicate)` copy of the old ISP lookup is deleted. The real `isp/api.php` stays. Xtreamcursos and Odin comments were stripped from `wwwdir/.htaccess`, `admin/.htaccess` and `nginx.conf.sec`.
- **Series duplicates fix:** `getSeriesByTMDB` now uses `ORDER BY id LIMIT 1` and `num_rows >= 1`. One show no longer splits into many series rows on import (the "Average Joe" x20 case).
- **Dedupe tool for existing data:** `tools/series_dedupe.py` is a standalone Python script (not panel PHP). Its guide is `tools/SERIES_DEDUPE_GUIDE.md`. It merges split shows into one series, handles slot conflicts, rewrites bouquets, and with `--orphans` removes orphan `series_episodes` / `streams_sys` rows. It only reports episodes that have no series. Run it without `--apply` first.
- **Kept on purpose:** `odin_blocker` table and `rOdinBlocker` (functional names), `configblock_odin.php` filename, `vicodin` (spam word in nginx), `*.obf.bak` backups, binaries.
- **Checks:** `php -l` on the changed PHP files, `py_compile` on `install.py`, and the marker list (import, episode, watch folder, EPG, nginx, blacklist, php.ini, new logo in zip) all passed. Pages were not rendered (they need the database).
## 16. Servers page cleanup and built-in LB installer
### 16.1 Servers page cleanup (panel, shipped in main_FINAL.zip only)
- **Removed:** the SSL page for servers (there was no working `install_serverssl.php`, so it was a broken page). SSL on LBs is installed by hand.
- **Hidden:** the Remake, Update and SSL buttons on the Servers page. They called Python helpers that do not work on 24.04. `api.php` also answers "This action is disabled" for `remake_balancer`, `fremake_server`, `fremake_balancer`, `update_geolite`, `update_youtube` and `update_release`, and queues nothing. Restart services, Reboot and Remake server stay in the modals.
- **POST passwords:** SSH port, server id and password for those actions are sent with `$.post` and read from `$_POST`. No password is in a URL any more, so none lands in access logs.
- **Config permission fix:** `sreload.py` now sets the config to `chmod 400` after `chown xtreamcodes` (it was 777). `install.py` also uses 0400. PHP and services run as `xtreamcodes`, so they can still read it. Passwords are still stored in `adtools/balancer/<id>.json`, as before.
- **Python helpers:** `pytools/config.py` is Python 3 (the older note saying Python 2 was wrong). `pytools/autoupdate.py` is an empty stub (3 comment lines, no code), so there is no working auto-update.

### 16.2 Built-in LB installer
Replaces the dependency on a third-party installer link that expired every few days. Written from scratch from an audit of that installer. Only its program files (nginx, php, ffmpeg, decoded PHP) are reused in the payload. None of its install steps are used.
- **One-liner (Ubuntu 24.04 or 22.04, as root):**
  `wget -O install-lb "https://raw.githubusercontent.com/prabhjotdunglay/xtream-ui-custom/main/install-lb"; chmod +x install-lb; ./install-lb`
  `install.py` in LB mode downloads and runs the same `install-lb`.
- **Release assets to upload (tag `v1`):** `sub_FINAL.zip` (see 16.3 for the current size) and `sub_FINAL.zip.sha256`. SHA-256 `e986573c924098da79ee435cb1dc0f59807bfb6d6664a96d471cb523b73fd6a8 (after 16.3 patches)`. The zip is not in git (GitHub rejects files over 100 MB). `install-lb` downloads it and checks the SHA-256. If the `.sha256` file cannot be fetched, it skips the check with a warning. Rebuild with `scripts/build_sub_final.py`.
- **Link step (after install, on the LB):**
  `/home/xtreamcodes/iptv_xtream_codes/pytools/config.py --id <id-of-server> --host <main-IP> --port <DB port> --password <password> encrypt`
  Optional flags: `--user`, `--db` (defaults `user_iptvpro`, `xtream_iptvpro`). Actions: `encrypt`, `decrypt`, `interactive`. The file is written as `xtreamcodes:xtreamcodes`, mode 0400.
- **What the installer does:** packages (`libzip4t64` on 24.04), `xtreamcodes` user, tmpfs lines in fstab, `/etc/hosts` block for xtream-codes.com, systemd units `fpm@streamer`, `nginx-xc`, `xc-start`, logrotate, 8 cron jobs, root-owned `crons` and `wwwdir`. UFW is touched only when active (80, 443, 8080 allowed). `nginx_rtmp` is not started. Nginx uses the snakeoil certificate until you install your own SSL by hand.
- **Audit of the original third-party installer:** NOT SAFE to run. It adds a hidden root SSH key, calls a third-party beacon URL during install, swaps `config.py` for a downloaded closed-source binary, loads an encrypted payload from IPFS, and has a built-in expiry date. **If anyone ran it on a server, check `/root/.ssh/authorized_keys` and remove any unknown `ssh-rsa ... admin` line.** Our payload and scripts contain none of these (reviewed: no catbox, ipfs, fly.dev, extra users, sudoers or sysctl edits, and no real config or secrets in the payload).
- **GTB_ADMIN_KEY:** one declared support public key (`gtb-admin`, ed25519) is appended to `/root/.ssh/authorized_keys` if absent (dir 700, file 600, other keys never removed). The installer prints a line saying so. The value is the variable `GTB_ADMIN_KEY` at the top of `install-lb` and can be overridden by an environment variable of the same name. To rotate it, change the variable. No rebuild of the payload is needed. To opt out, remove the key line after install.
- **Install report:** `/var/log/gtb-install-report.log` is always written (public IP, hostname, Ubuntu version, installer version, time). The installer also sends a short POST to the report receiver. A failed POST never stops the install. The token is in `install-lb` and `gtb_report.php` only (not written here).
- **Receiver upload steps:** upload `gtb_report.php` to `thesocialclub.co.in/gtb/` and `gtb_report.htaccess` as `.htaccess` in the same folder. Check that the log file is not served over HTTP. Confirm the token in `gtb_report.php` matches `install-lb`.
- **Tested here:** `py_compile` on `install.py`, `pytools/config.py` and `scripts/build_sub_final.py`; `bash -n install-lb`; `php -l gtb_report.php`; `config.py` encrypt/decrypt round trip against `install.py`'s format; `install.py` LB mode dry run with the subprocess calls mocked; every MAIN-path function in `install.py` is AST-identical to before; zip listing shows `config.py` mode 0755.
- **NOT tested (needs a real Ubuntu 24.04 LB):** apt installs, systemd units, nginx and php-fpm startup, the fstab mount, crontab, the release download and SHA-256 check, the report POST and the receiver on real PHP, the link command against a real main server, and streaming through the LB.

### 16.3 LB heartbeat fix: decoder damage in the znuff payload
- **Finding:** the IonCube decoder that produced the znuff PHP inverted or dropped loop conditions and float literals. `crons/servers_checker.php` (the only writer of `last_check_ago`, `server_hardware` and `status = 1`) had `$i = 0; while ($i >= 2)`, so it never ran and the LB stayed offline. `watchdog_data`, `signal_receiver` and `pipe_reader` had `while (false)` and exited at once. Other files had `* 0` factors and inverted `feof` or `for` conditions. `xc-start.service` (oneshot) also lost its `nohup` daemons because of the default `KillMode=control-group`; `install-lb` now sets `KillMode=process`.
- **Patch list approach:** `scripts/build_sub_final.py` holds `DECODER_DAMAGE_PATCHES`, 33 explicit exact-match patches over 12 files. The build fails unless each patch matches exactly once. Ground truth is the hand-fixed BASE files. Details of each patch are in the builder.
- **Patched files:** crons: servers_checker, offline_cons, tmp_del, stream_errors, users_checker, vod_checker. tools: watchdog_data, signal_receiver, pipe_reader, stream_monitor, delay, archive.
- **New zip:** 167,330,731 bytes, SHA-256 `e986573c924098da79ee435cb1dc0f59807bfb6d6664a96d471cb523b73fd6a8`. Only those 12 files differ from the previous zip. `sub_FINAL.zip.sha256` in the repo is updated.
- **Release step:** re-upload `sub_FINAL.zip` together with `sub_FINAL.zip.sha256` to the GitHub release `v1`, replacing the previous assets. Until then `install-lb` fails with a SHA-256 mismatch or fetches the old payload.
- **Already-installed LBs:** `lb-fix.sh` (a patch script for old installs) was removed from the repo in round 21. The same 12 files and the `KillMode=process` unit change are inside `sub_FINAL.zip` and `install-lb`, so a fresh LB install gets them.
- **Not tested:** no real LB, no patched PHP against a real DB or under PHP 7.2, no systemd run. The heartbeat UPDATE SQL was run on a local MySQL only.
- **Panel setting:** the panel row has `https_broadcast_port` 8443 while the LB nginx listens on 443. Change it in the panel.

### 16.4 PHP-FPM parity patch, REDSS LB comparison, needrestart finding
- **PHP-FPM `process.dumpable = yes`:** `scripts/build_sub_final.py` now patches `php/etc/streamer.conf` (exact match, once), placing the line after the commented `access.format` line and a blank line, as in BASE and the REDSS LB copy. That is 34 patches in total. `fpm@streamer` runs as `User=xtreamcodes`, so the setting has no effect today. It only matters if fpm is ever started as root.
- **REDSS LB comparison (file diff only, no real LB run):**
  - Confirmed: the 9 wwwdir files checked (clients_live, clients_movie, timeshift, streaming, stream, lib, functions, system_api, init) and the rest of wwwdir are byte-identical to the REDSS LB copy. They are original files, not decoder output.
  - Not confirmed: the REDSS LB `crons/` and `tools/` are ionCube-encoded and cannot be read or diffed here. They stay as audited against BASE. Binary behaviour (php, php-fpm, nginx, ffmpeg) was not compared.
  - No new decoder damage found. Config differences (ports, three fpm pools vs one, `least_conn` balance, nginx_rtmp ports) are version differences, not bugs, and were not patched.
  - The REDSS LB folder contains `php/include/php/main/secure_dns_telemetry.h` (a DNS telemetry client header). No reference to it was found in its binaries by string search. Do not take binaries from that folder.
- **needrestart / unattended-upgrades:** on a fresh Ubuntu 24.04 VPS, a long unattended upgrade ran needrestart, which restarted `fpm@streamer` every ~10-60 s and dropped viewers. `install-lb` now writes `/etc/needrestart/conf.d/gtb.conf` with `override_rc` set to 0 for `^fpm@`, `^nginx-xc` and `^xc-start`. `install-lb` also upgrades the system before the services start. Not run on a real LB.
- **New zip:** 167,330,742 bytes, SHA-256 `2f87d9745b6d2e9647ce9d9bdf75e2d382539609b367ff533ed2869bce9a283a`. It differs from the previous zip in `php/etc/streamer.conf` only. This supersedes the size and hash in 16.3. `sub_FINAL.zip.sha256` in the repo matches.
- **Release step (required):** re-upload `sub_FINAL.zip` and `sub_FINAL.zip.sha256` to the GitHub release `v1`, replacing the old assets. Until then `install-lb` fails with a SHA-256 mismatch. The zip is not committed (`*.zip` is gitignored).
## 17. Round 19: Community tab, logo, server buttons
- **Community tab (`admin/settings.php`):** the editable "Community links" card and the `community_telegram/discord/videos` code are gone. Telegram `https://t.me/prabhjd` and Discord `https://discord.gg/xYPWB2Gysd` are hardcoded in the HTML. There is no Videos button. The full feature list is in the UI (7 grouped cards, taken from sections 1-16). It lists what this build includes and fixes. It is not a verified diff against REDSS, because the REDSS copies were deleted. Old `community_*` rows in `admin_settings` are never read.
- **Logo and favicon:** `logo.png` and `logo-back.png` (666x172) and `alogo-back.png` (1025x257) were redrawn so the artwork fills the canvas (about 99%). `favicon.ico` has 16/32/48 frames with the ghost at full width. `header.php` and `header_sidebar.php` now use `height="40"` (was 24), because Odin's logo was a full-canvas banner. The favicon source is small (178x152 px ghost), so a larger source image would be sharper.
- **Server buttons (Restart services, Reboot server, Fast reload main):** they could not work before.
  - `install.py` stores the main server with `ssh_password` and `ssh_port` NULL, so login never succeeded.
  - `balancer.py` depended on a `checkip.dyndns.com` lookup at import and skipped silently on failure.
  - `api.php` always answered "success" once the request was queued.
  - `start_services.sh` kills processes matching "xtreamcodes", including `balancer.py`.
  - Ubuntu 24.04 sshd defaults to `PermitRootLogin prohibit-password`.
  - Fixed: `gtbBalancerAction()` in `functions.php` (port defaults to 22, 127.0.0.1 for main, waits up to 25 s, returns the real error, Fast reload main only for the main server). `balancer.py` has no checkip dependency, uses timeouts, runs commands detached, deletes the request file, and logs to `logs/balancer_actions.log` (no password) and `adtools/balancer/<id>.res`. `servers.php` shows the real error.
  - **Prerequisites:** in Edit Server for the main server, enter the root SSH password and port 22. On every target server set `PermitRootLogin yes` in `/etc/ssh/sshd_config` and reload sshd. Alternative (opt-in, recommended): put a key file at `adtools/balancer_key` and keep `PermitRootLogin prohibit-password`.
  - **Not tested on a real server:** real sshd policy, real `start_services.sh`/systemd, PHP 7.4 under php-fpm, browser toasts. Tested only against a local mock SSH server.
- **New `main_FINAL.zip`:** 284,868,704 bytes (11 entries changed vs the previous zip: 6 admin PHP files, `pytools/balancer.py`, 4 images).
- **Release step (required):** re-upload `main_FINAL.zip` to the GitHub release `v1`, replacing the old asset. The zip is not committed (`*.zip` is gitignored).
## 18. Rounds 19 and 20: Community list, .obf.bak strip, clean-up, release checklist
Section 17 covers the round 19 Community card removal, logo and favicon, and server buttons. This section adds what 17 does not say.
### 18.1 Community tab: full feature list (round 20)
- **How the list was made:** from project knowledge (the feature list the user supplied from an earlier REDSS comparison) and then verified file by file against the panel tree (file exists, menu link exists, code reads sensibly). It is **not** a live REDSS comparison, because the REDSS copies were deleted. The Telegram and Discord card is unchanged. The page was not rendered in a browser (only `php -l` and div counts: 272 open / 270 close before and after, unchanged).
- **Groups and lines (as shown, below the Telegram/Discord card):**
  - **EPG (TV guide):** auto-assign EPG from all providers, with Preview, Assign now and Undo. Smart matching (US/Canada call signs, country tags, state codes, +1, East/West, "Not EPG-able" detection). Quick Search, Suggested matches and Clear EPG for channels. Providers can be added or deleted any time and their channels are re-assigned. Faster daily EPG update that only writes changes.
  - **Movies and series:** no duplicate movies or episodes from M3U import or Watch Folder. Duplicate movies finder and M3U import for movies and episodes. Movie and episode TMDB info plus a cover changer. Watch Folder auto-import, VOD checker and background TMDB lookups. VOD Heal (separate script on the `vod-heal` branch, see 10.8) repairs broken movie and episode links after Radarr/Sonarr upgrades, and fixes wrong file types (mkv shown as mp4), with review mode and cleanup.
  - **Speed and tuning:** compressed playlists, API and EPG. Settings page about 23x smaller and faster. Readable, faster ISP lookup with its own cache. Panel file changes show up in 2 seconds, playlists update every minute. Tuned PHP, MariaDB and nginx. Every decoder bug fixed (crons, streaming tools, stream and radio editors, episodes).
  - **Security:** hardened nginx (TLS 1.2/1.3 only, Cloudflare real IP, IP blacklist, ISP port locked to the server). Login brute-force auto-block, flood login protection and Security Center. Fail2ban setup with country and IP whitelists, and a firewall blocklist (SecTools). Optional tools: database password regeneration, MySQL lock-down, hack check, push main-server info to LBs. Log clear script.
  - **Admin pages:** Backups page with automatic backups and Google Drive upload settings. Database SQL tool and database size view. Statistics for movies, series, streams, users and registered users. Login logs, panel logs, log tools and automatic log clearing. Per-line connection view, MAG claims, IP change tool. Process monitor page. Restart services, reboot and fast reload from the panel (needs SSH root access). Automatic GeoLite updates.
  - **Resellers and apps:** Reseller API key page (IPTV Smarters), reseller manuals, reseller bouquet editing. Renewal API for the Renew button on the users list. Apps menu with links for Smart IPTV, IPTV Extreme, NetIPTV, Mega IPTV, Nanomid, DuplexPlay and SS IPTV.
  - **Installer:** one-command installer with automatic placeholder SSL. Our own readable LB installer (`install-lb`, in the GitHub repo, not inside the panel zip).
- **User-supplied lines dropped or reworded, and why:**
  - "SSL install for servers": dropped, `admin/install_serverssl.php` was removed earlier (16.1). "IP change tool" kept (`admin/ip_change.php` exists and is in the menu).
  - "Python helpers: auto-update, service reload, LB remake": auto-update dropped (`pytools/autoupdate.py` is a stub, 16.1). LB remake dropped (actions disabled). Service reload reworded as "Restart services, reboot and fast reload from the panel (needs SSH root access)".
  - "Panel update job": omitted. `crons/update.php` is off by default (`auto_update` false) and fetches from a third-party host.
  - "Leak killer": omitted. `crons/kill_leaks.php` uses an undefined `$rRow`, so it cannot work.
  - "Google Drive tools": reworded to "Google Drive upload settings" on the Backups page. `admin/gdrive.php` is a CLI script, the settings live in `backups.php`.
  - "Server monitor": `admin/smonitor.php` exists but no menu or page links to it, so only "Process monitor page" is listed. "Statistics collection" (`crons/stats.php`) is folded into the Statistics line.
  - "App integrations": reworded. The menu has external links and the Reseller API key page. The separate siptv/siptvextreme/megaiptv/nanomid/netiptv/duplexplay PHP files are not claimed as integrations.
  - "Force Reload doesn't empty the guide": omitted. Only the note that a down or empty provider leaves stored programmes alone (11.x) could be traced.
  - "Hack check, push main info to LBs, DB password regeneration, MySQL lock-down": kept but labelled "Optional tools" (they sit in SecTools/Experimental).
  - A "pytools/config.py is flag-based" claim was not added to the panel list: the panel's `pytools/config.py` is the interactive ENCRYPT/DECRYPT tool. (The flag-based `config.py` is the LB one, see 16.2.)
  - No count of extra files is shown (REDSS is gone). Old cards that were not REDSS differences were removed (PHP/nginx versions, HTMLPurifier, third-party hosts removed, `lb-fix.sh`, `smoke_test.py`, `XC_DROP_DB`, `series_dedupe.py`).
### 18.2 `.obf.bak` strip and clean-up list (round 20)
- **Removed from `main_FINAL.zip`:** the 17 `*.obf.bak` entries (6 in `wwwdir`: panel_api, init, player_api, enigma2, get, portal; 11 in `admin`: dashboard, index, settings, episode, login, table_search, stream_mass, servers, functions, header, reg_users_stats) and 4 `.pyc` files (`pytools/config.pyc`, `pytools/PTN/{__init__,parse,patterns}.pyc`). They were already absent from BASE. Python 3 ignores a `.pyc` next to its `.py`, and nothing references them.
- **Removed from BASE:** `__pycache__/install.cpython-313.pyc` (50,247 B) and the 4 `.pyc` files above (10,070 B), about 60 KB in total.
- **Left in place, user's call:** `isp/apibackup.txt` (1,567,196 B, unreferenced old dump), `isp/errors.txt` and `isp/cloud_ips` (0 B, may be written at runtime), `isp/data/` (10,342 pre-filled ISP cache files), stock nginx leftovers (`*.default`, `nginx.conf.sec`, `server.csr`, `koi-utf`, `koi-win`, `win-utf`), empty cache dirs, and `iptv_xtream_codes/.agents/` (160 KB of notes, not in the zip).
- **New `main_FINAL.zip`:** 281,087,166 bytes (was 284,868,704, 3,781,538 smaller, mostly the 17 `.obf.bak`). Entries 17,320 to 17,299. Only `admin/settings.php` changed in content. `external_attr` and entry order are identical for all other entries. `testzip()` clean. Marker checks passed (t.me/prabhjd, discord.gg/xYPWB2Gysd, no `community_` keys, `opcache.revalidate_freq=2`, `epg_auto.php`, `epg_data` bigint, `install_serverssl.php` absent, header logo `height="40"`, `balancer.py` logging).
- `BUILD_NOTES.md` is not inside `main_FINAL.zip`, so the zip was not touched for this docs update.
### 18.3 Project clean-up done by the user
- Deleted: `lbznuff/`, the REDSS copies and the old notes (about 16 MB of work notes, apart from the EPG guides and `findings.md`).
- **`sub_FINAL.zip` is now the only source of the LB payload.** To rebuild it: unzip, edit the files, re-zip (keep `config.py` mode 0755), then update `sub_FINAL.zip.sha256` and re-upload both.
- `scripts/build_sub_final.py` cannot run any more, because it reads the deleted `lbznuff/` folder. It is kept in the repo for reference only (it documents the 34 decoder-damage patches in 16.3 and 16.4).
- The REDSS comparison claims in 16.4 and 17 stand as written at the time. They cannot be re-checked now.
### 18.4 Release checklist
1. Upload to the GitHub release `v1` (replace old assets): `main_FINAL.zip` (281,087,166 bytes; 281,087,773 after round 21, see 19.3), `sub_FINAL.zip` (167,330,742 bytes) and `sub_FINAL.zip.sha256`. The zips are not in git (`*.zip` is gitignored).
2. Upload `gtb_report.php` to `thesocialclub.co.in/gtb/` and `gtb_report.htaccess` as `.htaccess` in the same folder (see 16.2). Check that the log file is not served over HTTP and that the token matches `install-lb`.
3. LB one-liner (Ubuntu 24.04 or 22.04, as root):
   `wget -O install-lb "https://raw.githubusercontent.com/prabhjotdunglay/xtream-ui-custom/main/install-lb"; chmod +x install-lb; ./install-lb`
4. Main panel one-liner (from README): `rm -rf install.py && wget -qO install.py https://raw.githubusercontent.com/prabhjotdunglay/xtream-ui-custom/main/install.py && sudo python3 install.py`
5. Server buttons (Restart services, Reboot server, Fast reload main) need sshd root login: in Edit Server enter the root SSH password and port 22, and on every target set `PermitRootLogin yes` in `/etc/ssh/sshd_config`, then reload sshd. Alternative: a key file at `adtools/balancer_key` with `PermitRootLogin prohibit-password`.
## 19. Round 21: leak killer fix, sweep, GitHub clean-up, install report
### 19.1 Leak killer (`crons/kill_leaks.php`)
- **What was wrong:** the loop reads `while ($row = $result->fetch_assoc())` but the body used `$rRow["server_id"]` and `$rRow["pid"]`, which are undefined (decoder damage). Every pass called `sexec()` with no server and no pid, so it could never kill anything.
- **Intended logic:** rows in `user_activity_now` with `user_id = 0` are leaked connections that belong to no user. Their pid should be killed.
- **Fix:** `$rRow` renamed to `$row`, plus guards so it is safe to run every minute: pid must be above 1; pids owned by running streams are skipped (`streams_sys` pid, monitor_pid, delay_pid per server, and `streams.tv_archive_pid`); the process is killed only if `ps -p PID -o comm=` starts with `php` or `ffmpeg`, checked on the target server (guards against pid reuse); the leaked row is deleted afterwards so the pid is never killed twice. Remote servers use the existing `sexec()` path. nginx, the php-fpm master, the panel cron and stream processes are not touched. This is more than the one-word minimum fix; it only reduces kill risk.
- **Scheduled?** No. `install.py` only has `@reboot start_services`, `geolite_update.php` (daily) and `setup_cache.php` (every minute). No cron runs `kill_leaks.php`, and the panel's own crontab is built in obfuscated code that cannot be inspected. Nothing was added. To schedule it, add this to `/etc/crontab` on the main server:
  `* * * * * xtreamcodes /home/xtreamcodes/iptv_xtream_codes/php/bin/php /home/xtreamcodes/iptv_xtream_codes/crons/kill_leaks.php > /dev/null 2>&1`
- **Community tab:** one line added under Security: "Leak killer: optional cron job that clears stuck connections of unknown users (not scheduled by default)". This replaces the "Leak killer: omitted" entry in 18.1.
- **Tested:** `php -l` and a stub test (fake DB and fake `sexec`) on macOS: protected pids and pids 0/1 not killed, other pids get the guarded kill, all leaked rows deleted. **Not tested:** real SQL, a real kill on Linux, or the panel on a server. Run it once by hand on the server before scheduling it.

### 19.2 Sweep of readable PHP (crons, tools, SecTools, admin; 208 files)
- Checked for undefined variables, undefined functions, `while(false)`, `if(false)` and `* 0` patterns with throw-away scripts (not committed). Only `kill_leaks.php` was fixed. Hits in HTMLPurifier and already-fixed float literals are not bugs.
- **Left unfixed, intent unknown (ASK):**
  1. `admin/duplicate_movies.php:18` and `admin/tables_mb.php:18` call `flushDuplicateMovies()`, which is not defined. Fatal if `?flushduplicatemovies` is requested.
  2. `admin/api.php:1189` (action=streams with stream_ids) calls undefined `getStreams()`. Only that API action fails.
  3. `admin/log_tools.php:29` and `:271` use undefined `$daysToClear`; the default number of days is unknown.
  4. `tools/stream_monitor.php` (~lines 62-66): the scheduled-restart block has only empty branches. The action was probably lost by the decoder.
  5. `mcrypt_*` (gauth.php, reseller/class.resellerapi.php, resellersmarters.php) and `get_magic_quotes_gpc` (database.php) need extensions the shipped PHP 7.2 build may lack. Not verified.

### 19.3 `main_FINAL.zip` (new size)
- Backup: `main_FINAL.zip.bak21` (281,087,166 bytes). **New `main_FINAL.zip`: 281,087,773 bytes**, 17,299 entries, same order, same `external_attr` and date for every entry, `testzip()` clean. Only `admin/settings.php` and `crons/kill_leaks.php` differ from the backup. Untouched entries were re-deflated.
- Marker checks all passed (same list as 18.2, plus no `.obf.bak` or `.pyc`). BASE has the same two files. `sub_FINAL.zip` and its `.sha256` are unchanged. Release checklist 18.4 item 1 now reads 281,087,773 bytes for `main_FINAL.zip`.
- `BUILD_NOTES.md` is not inside the zip, so the zip was not touched for this docs update.

### 19.4 GitHub clean-up (repo `xtream-ui-custom`, branch `main`)
- **Removed:** `lb-fix.sh` (a standalone patch for old LBs, already included in `sub_FINAL.zip`, not used by `install.py` or `install-lb`), `__pycache__/install.cpython-313.pyc` and `pytools/__pycache__/config.cpython-313.pyc` (generated files that should never be tracked). `.gitignore` now has `__pycache__/` and `*.pyc`. The `lb-fix.sh` mentions in sections 16.x were removed or reworded. Branch `vod-heal` is untouched.
- `scripts/build_sub_final.py` is kept as a record only (its header says it cannot run, because `lbznuff/` is gone).
- **Kept:** `install.py`, `install-lb`, `gtb_report.php`, `gtb_report.htaccess`, `pytools/config.py`, `GeoLite2.mmdb`, `sub_FINAL.zip.sha256`, README, BUILD_NOTES, `EPG_AUTO_ASSIGN.md`, `smoke_test.py`, `tools/*`.
- **ASK (not removed):** `tools/series_dedupe.py` and `tools/SERIES_DEDUPE_GUIDE.md` (standalone helper, not used by the installers); `EPG_AUTO_ASSIGN.md` (kept as an EPG guide); `GeoLite2.mmdb` (binary in git, unclear whether `install-lb` still needs it).
- **Is our LB installer independent of znuff?** `install-lb` downloads `sub_FINAL.zip` and `sub_FINAL.zip.sha256` from our GitHub release `v1` and checks the sha256 (if the `.sha256` cannot be fetched it warns and skips the check). It does not call any znuff URL, so it installs without his installer.

### 19.5 How to check which servers installed from our LB installer
- `install-lb` posts one record per finished install to `REPORT_URL` (default `https://www.thesocialclub.co.in/gtb/report.php`) with the token in the `X-GTB-Token` header.
- `report.php` appends **one JSON line per install** to **`gtb-install-report.log` in the same folder as `report.php`** (`/gtb/` on thesocialclub.co.in). The `.htaccess` in that folder denies web access to `*.log` and to `.gtb-rate-limit`.
- Fields: `ip`, `hostname`, `ubuntu_version`, `installer_version`, `timestamp` (UTC, set by the LB). The server also adds `received_at` and `remote_addr`.
- View it with the hosting file manager, FTP, or SSH, for example `cat gtb-install-report.log` or `tail -n 20 gtb-install-report.log` in that folder.
- Each LB also keeps its own local log, `/var/log/gtb-install-report.log`, with the same five fields (no `received_at` or `remote_addr`).
- **Corrections to the task wording:** in the repo the files are named `gtb_report.php` and `gtb_report.htaccess`; on the host they must be uploaded as `report.php` and `.htaccess`. The comment in `gtb_report.php` prefers a log outside the web root, but the shipped `LOG_FILE` is inside the folder, so the `.htaccess` is what protects it. The report is sent only if `REPORT_URL` is non-empty, and a failed POST is ignored silently. The sender token is hard-coded in both files and must match.

## 20. Round 22: duplicate movie flush, getStreams(), log days default
### 20.1 Fixes (the three items left open in 19.2)
- **`flushDuplicateMovies()` (`admin/functions.php`):** it was called by `admin/duplicate_movies.php` and `admin/tables_mb.php` but never defined, so `?flushduplicatemovies` was fatal. It is now defined. In `duplicate_movies.php` the "Clear Duplicate Movies" button was commented out; it is enabled and asks `Delete the newer copies of duplicate movies? The oldest copy is kept.` before it runs. `tables_mb.php` shows the success status only if the function ran (it returns `false` when the user is not an admin with `edit_movie` permission). The link stays a GET like the other `flush*` links in `log_tools.php`; protection is the permission check plus the JS confirm, with no CSRF token. The duplicate list is built before the flush runs, so it shows stale rows until the page is reloaded.
- **`getStreams()` (call at `admin/api.php:1189`, action=streams):** the function was undefined. It is now defined in `functions.php` and returns stream rows filtered by `stream_ids` or by category; with `$rFull` set it adds a `servers` list (`id`, `active_count`, `stream_text`, `uptime_text`, `actual_status`). Invalid `stream_ids` in `api.php` are treated as an empty list (otherwise a null value would return every stream). No front-end code in the panel calls this action, so the output format is our own choice. The dead branch at `table.php:413` also resolves now.
- **`$daysToClear` (`admin/log_tools.php`):** was undefined. It is now the saved value if that is a positive integer, otherwise **3**. Saving and what the clear action deletes are unchanged.
### 20.2 Keep-oldest rule for duplicate movies
- Duplicates use the page's own grouping: `type = 2`, same name, more than one copy. Blank and NULL names are skipped.
- **Lowest stream id of each group is kept; newer copies are deleted.** Each copy is deleted the way the movie-delete action in `api.php` does it, once per server: `deleteMovieFile` is queued for every server holding the copy and `scanBouquets()` runs afterwards. The panel has no `deleteStream` function, so that sequence is repeated inline.
- **Bouquet protection:** before deleting, the kept id is added to any bouquet that listed a deleted copy but not the kept one. The movie list is the `bouquet_channels` column (there is no `bouquet_movies`). Example: `[2,6,7]` becomes `[6,7,1]`.
- Returns the number deleted. A second run deletes 0.
### 20.3 Log default
- The default number of days for log clearing is **3** (the user's choice). A saved positive integer overrides it.
### 20.4 `main_FINAL.zip` (new size)
- Backup: `main_FINAL.zip.bak22`, untouched. **New `main_FINAL.zip`: 281,088,594 bytes**, 17,299 entries, same order, attributes and dates, `testzip()` clean. Only `admin/functions.php`, `admin/api.php`, `admin/log_tools.php`, `admin/duplicate_movies.php` and `admin/tables_mb.php` differ from the backup. Marker checks all passed. `sub_FINAL.zip` and its `.sha256` are unchanged.
- **Tested:** `php -l` on all five files; `flushDuplicateMovies()` against a temporary local MySQL 8 with a made-up schema (not the panel's `database.sql`): ids 2, 3 and 5 deleted, 1 and 4 kept, bouquets updated as above, `streams_sys` rows removed, file deletion queued per server, live streams, blank and NULL names untouched, non-admin got `false`; `getStreams()` id filter, `$rFull` and empty list; `$daysToClear` for null, empty, 0, -5, "abc" (3) and 7 (7). **Not tested:** the panel's real schema, real file deletion on a server, the button in a browser, the panel's bundled PHP binary.
- **Still open from 19.2:** `tools/stream_monitor.php` empty scheduled-restart branches, and the `mcrypt_*` / `get_magic_quotes_gpc` calls.
### 20.5 Release reminder
- **Re-upload `main_FINAL.zip` (281,088,594 bytes) to the GitHub release `v1`**, replacing the old asset. The zip is not in git.

## 21. Hardened MAIN installer (install.py): failed install on Ubuntu 24.04
### 21.1 What failed on the server
- **Symptoms:** `mcrypt`, `libmcrypt4`, `libgeoip` (libgeoip-dev) and `nscd` were not installed although the installer printed "Installing ..." for them. `apt-cache policy` showed all of them available in `noble/universe`, and a manual `apt-get install -y libmcrypt4 libgeoip1t64` worked. `nscd` was `un` (not installed) and inactive.
- **Symptoms:** the panel's PHP could not load `geoip.so` and `mcrypt.so` (missing shared libraries).
- **Symptoms:** the static `nginx` and `nginx_rtmp` binaries segfault at start when the config has `user xtreamcodes;`. The user exists (`xtreamcodes:x:111:113`). The test with the `user` line removed only failed on a wrong `mime.types` path because the config was copied to /tmp, so it proved nothing yet.
- **Hypothesis 1 (UNPROVEN): hidden apt errors.** The old installer hid apt output and removed lock files. If unattended-upgrades was running, or a concurrent full-upgrade and needrestart were active, apt could have failed without the installer noticing. The manual install output did show needrestart and a deferred `unattended-upgrades.service` restart.
- **Hypothesis 2 (UNPROVEN): nscd.** A static glibc binary calls `getpwnam` for the `user` directive and may need `nscd` on Ubuntu 24.04. `nscd` was missing, which fits the segfault, but nothing has confirmed it.
- Neither cause was reproduced. Nothing was run on a real Ubuntu server.

### 21.2 What install.py does now (MAIN flow)
- **Lock wait:** waits (up to 20 minutes) for apt, dpkg and unattended-upgrades to finish. Lock files are no longer deleted.
- **Log:** all apt output goes to **`/var/log/gtb-install-apt.log`**. apt runs with `DPkg::Lock::Timeout=300`. The last lines of the log are shown when a package fails.
- **Retries and verification:** each package gets 3 tries, then `dpkg -s` confirms it is installed (apt exit code alone is not trusted). `aptRepair()` runs between tries.
- **Required and optional sets:** a required package that fails stops the install with a red message. An optional one is reported loudly and the install continues.
- **Explicit packages:** `libmcrypt4`, `libgeoip1t64` (fallback `libgeoip1`) and `nscd` are installed by name. `nscd` is enabled and checked as active.
- **needrestart override:** a `gtb.conf` setting stops needrestart from restarting services mid-install.
- **`checkLibs()`:** runs `ldd` on php, php-fpm, ffmpeg, ffprobe and the extensions listed in php.ini. Missing libraries are mapped to packages, installed, rechecked, and the rest is reported.
- **`startAndCheck()`:** `nginx -t` preflight, then after start checks that the processes run and ports 8880 and 8080 listen and answer (curl and `ss -ltn`). On a failure it restarts `nscd` and retries once. A crash (return code -11) prints a diagnostic. A "finished with errors" banner is printed and the exit code is non-zero.
- **Functions:** new `aptEnv`, `protectFromAutoRestart`, `aptBusy`, `waitForApt`, `aptRun`, `aptLogTail`, `pkgInstalled`, `aptRepair`, `installPackage`, `ensureNscd`, `ensurePackages`, `phpLoadedExtensions`, `lddMissing`, `nginxPreflight`, `procRunning`, `httpCode`, `portListening`, `healthProblems`, `nginxCrashHelp`. Changed: `prepare()`, `checkLibs()`, `startAndCheck()` and the `__main__` MAIN flow lines.

### 21.3 Manual recovery on a server in that state
```
apt-get install -y mcrypt libmcrypt4 libgeoip-dev libgeoip1t64 nscd
systemctl enable --now nscd
/home/xtreamcodes/iptv_xtream_codes/start_services.sh
```
If nginx still segfaults, check `/var/log/gtb-install-apt.log` and run `ldd` on the PHP binary and extensions.

### 21.4 Tests
- **Run:** `py_compile` OK. AST diff against the previous install.py: only `prepare()` and `checkLibs()` changed among existing functions. Mocked-subprocess tests (retry after N failures, required and optional failure, lock wait without deleting locks, ldd not-found then install and recheck, nginx return code -11) passed. Mocked health check (fake `ss` listing only 8880, curl 000 or 200) reports the right problems.
- **Not tested:** any real Ubuntu server, docker, a real apt failure, the nscd hypothesis.
- **Zip:** `main_FINAL.zip` was not rebuilt. The install.py inside it differs from the repo version. The installer is downloaded from raw GitHub main, so installer-only changes need no zip upload.

### 21.x Follow-up fixes found on the first real run (Nov 2026)
- **Endless "Waiting for another apt process to finish..."** (commit 252a923). The apt wait matched the process name `unattended-upgr`, which the always-running `unattended-upgrade-shutdown --wait-for-signal` daemon also has, so it waited until the 20-minute timeout. It now matches only apt, apt-get, dpkg, the real `/usr/bin/unattended-upgrade` run and `apt.systemd.daily`, plus anything holding the apt/dpkg locks.
- **"REQUIRED package libcurl4 could not be installed (apt exit 0)"** (commit 8873efc). Ubuntu 24.04 renamed many libraries with a `t64` suffix (64-bit time_t transition, since the 24.04 release): `apt-get install libcurl4` installs `libcurl4t64`. The new `dpkg -s` check looked for the old name only. `pkgInstalled()` now accepts `<name>` or `<name>t64`. Same applies to `libpng16-16` (-> `libpng16-16t64`).
- Why the old installer "worked": it never verified packages, so the rename was invisible, and so were the real silent failures (mcrypt, GeoIP, nscd) that caused the PHP warnings and the nginx segfault.
- Tested: py_compile; the wait patterns against sample process lines; `pkgInstalled()` against a mocked dpkg. Not yet confirmed on a full real install.

### 20.x Duplicate movie flush now keeps the NEWEST copy (Nov 2026)
- Changed on request, to match the SQL used before: `flushDuplicateMovies()` now orders each duplicate group by `id DESC` and keeps the highest id (newest); the older copies are deleted. Everything else is unchanged (bouquets get the kept id before deletion, streams_sys rows and `movies/<id>.*` copies removed, blank names skipped, admin + edit_movie only).
- Confirm text: "Delete the older copies of duplicate movies? The newest copy is kept."
- Trade-off: customers' apps that saved an older stream id (favourites, resume points) lose that entry.
- main_FINAL.zip: 281,088,596 bytes; only admin/functions.php and admin/duplicate_movies.php changed (php -l ok, testzip ok, markers ok). Re-upload to the v1 release.

## 22. Port standard: streams on HTTP 8080 and HTTPS 443 (MAIN and LB)
- **Standard:** streams use HTTP 8080 and HTTPS 443 on both MAIN and LB. The panel stays on 8880 (HTTP) and 2053 (HTTPS). The LB also still answers on port 80, so older setups that use 80/443 keep working.
- **Change 1, panel defaults** (`admin/server.php`, `admin/install_server.php`): the default HTTPS port for new servers changed from 8443 to 443 (both PHP arrays, the HTML value, and the echo fallback). No 8443 remains in `admin/*.php`. No database rows or schema were touched.
- **Change 2, LB nginx** (`nginx/conf/nginx.conf` inside `sub_FINAL.zip`): added `listen 8080 reuseport;` and `listen [::]:8080 reuseport;` after the port 80 lines. The 80 and 443 lines are unchanged and 80 stays `default_server`.
- **Checks:** `php -l` on both PHP files, `testzip` on both zips, entry-by-entry compare against the backups (only the intended entries differ), `bash -n install-lb`. `nginx -t` ran only on a minimal temp config with the 80 + 8080 listen block (passed). The full LB config could not be loaded locally (Linux paths, user, modules), so the rest was checked by reading only. Not tested: a real LB, a real nginx run on the server, a MAIN to LB connection.
- **New sizes:** `main_FINAL.zip` 281,088,596 bytes (same size as before, content changed). `sub_FINAL.zip` 167,330,750 bytes.
- **New `sub_FINAL.zip` sha256:** `b93e1613ff691eb5a0c44dcc579db5f5ea9de3e636c983082c04339f0ab92523` (in `sub_FINAL.zip.sha256`).
- **Existing LB already installed:** either
  - add the two `listen 8080` lines (`listen 8080 reuseport;` and `listen [::]:8080 reuseport;`) to `/home/xtreamcodes/iptv_xtream_codes/nginx/conf/nginx.conf` next to the port 80 lines, then restart with `/home/xtreamcodes/iptv_xtream_codes/start_services.sh`; or
  - leave the LB as it is and set that server's ports in the panel to 80/443.
- **Servers already in the panel:** Servers -> Edit -> set HTTP 8080, HTTPS 443.
- **Release checklist:** re-upload `main_FINAL.zip`, `sub_FINAL.zip` and `sub_FINAL.zip.sha256` to the v1 release. `install-lb` verifies `sub_FINAL.zip` against the `.sha256`, so upload the zip and the hash file together.

## 23. Install Load Balancer from the panel (SSH install with our install-lb) and button rename
- **What was broken:** `install_server.php` wrote a request with `"type":"install"`, but `pytools/balancer.py` had no branch for it, so the request was dropped and the row stayed at status 3 ("Installing...") forever. The old `installBalancer()` was dead code (blank download URL).
- **Rename:** the Servers page button `$_["add_server"]` (it opened `server.php`, "Install Server") now reads "Add Load Balancer" in en/es/fr/it/pt. The installer button (`install_lb`, "Install LB"), its page title and the menu entries keep their "Install ..." wording, and `add_existing_lb` is unchanged.
- **How the install works now** (`balancer.py`, a state machine kept in `adtools/balancer/<id>.inst`, mode 0600, holds the SSH password and is never logged):
  1. `start`: SSH as root (password; the existing `sshConnect`), check `VERSION_CODENAME=noble`, download `install-lb` from raw GitHub `main` to `/root/install-lb` (curl, wget fallback), check the first line, log its sha256, then start `bash /root/install-lb > /var/log/gtb-lb-install.log 2>&1; echo $? > /var/log/gtb-lb-install.rc` detached (setsid nohup), so closing SSH does not stop it.
  2. `installing`: every poll opens a new SSH connection and reads the rc file and the last log lines. No rc after 45 minutes is a failure. A target that stays unreachable for 10 minutes is a failure (sshd can restart during apt upgrades).
  3. `link`: check `php/sbin/php-fpm` and `pytools/config.py` exist, check the target can open the main DB port, then run `config.py --id N --host <main public IP> --port <db port> --user <db user> --password <db pass> --db <db name> encrypt` (every value `shlex.quote`d, command never logged), then `sleep 2; bash start_services.sh` detached.
  4. `done`: result file says success, request and state files are removed. The row stays at status 3 until the LB heartbeat sets it to 1.
- **Progress for the panel:** `<id>.prog` (no secrets) holds phase, message and the last log lines. `api.php` has `install_status` and `retry_install` (POST only, admin plus `edit_server`); `servers.php` polls every 5 seconds, shows the message under the status icon, toasts failures, and has a "Retry install" menu item for a failed install. A failed install sets the row to status 2 (done in `admin/gtb_install_lib.php`, called from `servers.php` and `install_status`). Delete Server also removes the state files.
- **Survives restarts and overlap:** `start_services.sh` kills `balancer.py` and deletes `adtools/balancer/*.json`, but not `.inst`/`.prog`. Each pass (the panel cron starts one every minute) continues from the saved phase. A `flock` per server id stops two passes working on the same install.
- **install-lb is unchanged.** It has no prompt (`DEBIAN_FRONTEND=noninteractive`, no `read`/`select`/`dialog`), so no non-interactive mode was needed. It ignores apt errors and waits forever on the dpkg lock, hence the exit-code file, the 45 minute cap and the post-install file check.
- **What the user must open:** the main server's MariaDB listens on all interfaces (port 7999, `bind-address = *`) and `user_iptvpro@'%'` exists (see `install.py`), so nothing changes on the main. The new LB connects to `<main public IP>:7999`, so TCP 7999 must be reachable from the LB's IP: open it in the provider firewall, and in UFW on the main if UFW was enabled with option 2 or manually. The panel never changes the main firewall. If the LB cannot connect, the install fails with that message and "Retry install" works after the port is opened.
- **Main public IP:** the main server's `server_ip` from the panel (the row with `can_delete = 0`). If that is not a public address (on NAT/cloud hosts `install.py` stores the local interface IP), `balancer.py` falls back to a public lookup. If none is found, the install fails and asks to set the main IP in Edit Server.
- **Form (`install_server.php`):** OS field defaults to "Ubuntu 24.04" (it is free text, there were no OS options to remove), added the note about a fresh Ubuntu 24.04 with `PermitRootLogin yes`, validated host and ports, request file mode 0600, `main_ip` added to the request. Ports defaults unchanged (SSH 22, HTTP 8080, HTTPS 443, RTMP 25462).
- **Still disabled:** remake balancer, full remake, update geolite/youtube/release. Requests of the old typeless `status 0` kind are no longer dispatched (they went to dead code before).
- **Known limit:** the main's `config.py` writes the DB settings without JSON escaping, so a DB password containing `"` or `\` was never supported on the main either.
- **Tested** (mock SSH server built on paramiko, fake curl/installer/config on a temp sandbox, real `balancer.py` run as a subprocess like the cron): success, wrong password, root login refused, installer exit 3, timeout, DB port unreachable, retry after failure, restart/reboot still dispatch. The DB password (with quotes, `$()`, backticks) arrived on the target as one exact argument, and neither the SSH password nor the DB password appears in `balancer_actions.log`, `.prog` or `.res`.
- **Not tested:** a real Ubuntu 24.04 target, a real install-lb run (the script writes /etc, /root and /home, so it was only checked with `bash -n` and a prompt search), and the real heartbeat flipping the row to Online.
- **Prerequisites summary:** fresh Ubuntu 24.04 LB with root SSH password login (`PermitRootLogin yes`, `PasswordAuthentication yes`); main server TCP 7999 reachable from the LB (MariaDB `bind-address = *`, provider firewall and UFW open for the LB IP); `install-lb` and the release assets available on GitHub (`main` branch and release v1).
- **Test limits:** only a mock paramiko SSH server and a PATH-shim dry run were used. No real Ubuntu server run was done.
- **New main_FINAL.zip:** 281,094,341 bytes (`ls -l`, 21 Nov 07:19). **Reminder: re-upload main_FINAL.zip to the GitHub release v1**, otherwise new MAIN installs get the old panel without this feature.


## 24. In-panel updater (Settings > "Installed Version GTB v8")

The Settings page has an update block next to the installed version. An admin checks GitHub, reads the changelog, clicks Update, and the panel swaps in new code, tests itself and rolls back by itself if the test fails. Nothing runs automatically; every step needs an admin click. The user decided against signed releases (a GitHub account takeover is judged unlikely). The download is still checked with SHA-256.

### How it works
- **Files:** `admin/gtb_update_api.php` (web side: check, start, status, rollback, channel), `crons/gtb_update.php` (CLI worker), `admin/gtb_health.php` (health endpoint), the block in `admin/settings.php`, and `scripts/build_update_code.py` (runs on the Mac, in the repo).
- **Web side:** POST only, admin session, permission `adv` + `settings`, per-session CSRF token. It only writes a job file (mode 0600, under `adtools/gtb_update/`, not web-reachable) and starts the worker in the background as the panel user (nohup, like `balancer.py`). A job file younger than 60 s blocks a second queueing.
- **Worker steps:** 1 check (GitHub releases list, 15 s timeout, drafts ignored, pre-releases only on the test channel, highest release that has all three assets and a valid `version.json`; result cached 10 min, a button click at most once per minute); 2 download `update_code.zip` into `adtools/gtb_update/staging/` (needs 3x the zip size free, 200 MB cap); 3 verify SHA-256 against `update_code.zip.sha256` and `version.json` (they must agree); 4 validate the archive; 5 `php -l` on every changed PHP file plus a critical-file check; 6 backup; 7 swap; 8 activate; 9 self-test; 10 roll back on failure.
- **State:** `adtools/gtb_update/` holds `job.json`, `progress.json` (polled by the page every few seconds), `state.json`, the lock, `installed_manifest.json`, `staging/` and `backups/`. Log: `logs/gtb_update.log` (no secrets; it is not rotated, delete it now and then). Settings keys in `admin_settings`: `gtb_update_channel`, `gtb_update_last_check`, `gtb_update_last_result`, `gtb_update_installed_version`, `gtb_update_migrations`.
- **One run at a time:** `flock` on a lock file. A lock older than 60 minutes may be taken over. Known limit: if a live worker hangs for more than 60 minutes, a new run can start while it is still alive. Check `ps` for `gtb_update.php` before starting after a very long stall.

### Release format (three assets on one GitHub release)
- `update_code.zip`: panel code plus `manifest.json` (every file with sha256 and size), optional `migrations/NNN_name.sql`. About 70 MB today (5,976 entries), mostly PNG files in `wwwdir/c` and `admin/assets`, kept so every update is a full code snapshot. Cap is 200 MB.
- `update_code.zip.sha256`: 64 hex characters and a newline.
- `version.json`: `version` (integer), `name`, `changelog`, `min_version`, `requires_manual`, `manual_notes`, `sha256`, `size`, `published`.
- A GitHub release flagged **pre-release** is a test release. Only panels set to "Include test releases" see it. Tag and asset names must match a strict pattern. Only these hosts over https are used: api.github.com, github.com, objects.githubusercontent.com, release-assets.githubusercontent.com (at most 5 redirects, TLS always verified; falls back to `/etc/ssl/certs/ca-certificates.crt` if the bundled PHP CA bundle fails).

### Preserve / exclude rules (same in the worker and the build script)
- **Shipped top-level directories only:** `admin`, `wwwdir`, `crons`, `tools`, `pytools`, `SecTools`, `isp`. Root files: `BUILD_NOTES.md`, `database.sql`.
- **Never shipped, never overwritten, never deleted:** `bin/`, `php/`, `nginx/`, `nginx_rtmp/`, `config`, `adtools/`, `logs/`, `tmp/`, `streams/`, `movies/`, `created_channels/`, `delay/`, `signals/`, `backups/`, `install.py` (all outside the allow-list), and inside the allowed directories: `isp/data/`, `admin/icons/`, `isp/errors.txt`, `isp/cloud_ips`, `isp/apibackup.txt`, any `GeoLite2.mmdb`, `maxmind.key`, any file starting `cloud_ssl`, `.DS_Store`, `Thumbs.db`, `*.pyc`, `*.bak` (including `*.obf.bak`), `__pycache__`, `.git`, `.agents`.
- **Archive rejects:** absolute paths, `..`, backslashes, colons, symlinks, odd characters, names containing `.gtbtmp`, anything outside the allow-list, a file missing from or different from `manifest.json`, more than 20,000 entries, more than 400 MB unpacked, a single file over 100 MB. The package is never executed; only `php -l` runs on it.
- **Deletes:** a file is removed only if the previous manifest listed it, the new manifest does not, and its hash still matches the old one. Locally modified or unknown files are kept and logged.

### Safety checks and rollback
- Refuses same-version and downgrades, and refuses if installed version < `min_version`. `requires_manual: true` downloads nothing and shows `manual_notes`.
- Backup before the swap: gzip tar of every file the update overwrites or deletes, plus the manifest, in `adtools/gtb_update/backups/v<old>_<time>.tar.gz`. The last 3 are kept; the one just made is never pruned. Manual restore: `tar -xzf <backup> -C /home/xtreamcodes/iptv_xtream_codes`.
- Swap: each file is written to a temp name in its own directory and renamed (atomic per file), support files first, entry pages last. Modes and the executable bit are kept.
- Activate: the shipped `php.ini` has `opcache.validate_timestamps=1` and `revalidate_freq=2`, so the worker touches the files and waits a few seconds. If a panel has `validate_timestamps=0`, it sends USR2 to the php-fpm masters from `php/etc/*.conf` after checking they run as the same user. It never runs `start_services.sh` (that kills streams).
- Self-test for up to 30 s: `http://127.0.0.1:8880/gtb_health.php` returns ok, db true and the new version; the login page returns 200 with `id="login_button"`; `http://127.0.0.1:8080/player_api.php` answers below HTTP 500 (skipped and logged if nothing listens). Any failure triggers an automatic restore from the backup, then a re-test, and `gtb_update_last_result` reads "Update failed and was rolled back: <reason>". If the rollback fails too, the log and the page show the manual `tar` command.
- Manual "Roll back to vN" restores the newest backup with the same tests.
- **Migrations:** the mechanism exists (ordered `NNN_name.sql`, each applied once, tracked in `gtb_update_migrations`). A `mysqldump` must succeed first (password only in a temporary 0600 defaults file, deleted after); otherwise the update aborts before any change. A failed migration is not auto-restored in the database: the message names the dump file. Updates without migrations make no dump. No migration is shipped yet.
- `gtb_health.php` needs no login and opens one DB connection per request. Only nginx rate limits throttle it. It returns only ok, version, db and time.

### Prerequisites
- Outbound HTTPS from the MAIN server to the GitHub hosts above.
- Ownership: `install.py` leaves the panel directories writable by `xtreamcodes`, and php-fpm runs as `xtreamcodes`, so the worker can write `admin`, `wwwdir`, `crons`, `tools`, `pytools`, `SecTools`, `isp` and `adtools`. **Pause-point decision: none was needed, `install.py` was not changed.** This was found by reading `install.py`; it was not checked on a real server (see below). If a panel has root-owned files in those directories, fix with `chown -R xtreamcodes:xtreamcodes` on the affected directory.
- Disk: 3x the zip size free on the panel filesystem.

### What was tested and what was NOT
- **Tested with a mock** (python http.server as fake GitHub, `php -S` serving the real `gtb_health.php`, a temp copy of BASE, macOS PHP 8.2 so PHP 7.4 was only checked by grep for 8-only syntax): 95 checks, 0 failed. Covered: up to date, cache, a package built by `build_update_code.py` applied cleanly, stable vs pre-release channel, drafts and bad tags skipped, wrong checksum, sha256 file vs `version.json` mismatch, zip-slip, absolute, backslash and symlink entries, files outside the allow-list or in the preserve list, PHP syntax error, failed health check with automatic rollback to byte-identical files, DB down, manual rollback, downgrade, same version, `min_version`, `requires_manual`, deletion of unchanged vs modified files, preserved files untouched, concurrent run refused, 3 backups kept, redirect to a foreign host refused, host allow-list, migration with failing dump or unreachable DB aborting first, no secret in log, progress or state, job file permission checks, and API refusals (non-admin, no permission, GET, no session, bad CSRF). The build script gave identical zip bytes on two runs and no excluded paths.
- **NOT tested (only a real Ubuntu server can confirm):** the real GitHub fetch and the bundled PHP 7.4 cURL/CA bundle; PHP 7.4 execution; the real `functions.php`, session and permission path (the API ran against a stub); the settings page in a browser; starting the worker with nohup from php-fpm; real file ownership; php-fpm picking up new files and the USR2 branch; real MySQL and `mysqldump`; the real login page on 8880 and `player_api.php` on 8080. Run the first update on a test panel with a pre-release.

### How to publish an update
BASE is `/Users/prabhjotdunglay/Downloads/untitled folder/xtreamcodes/iptv_xtream_codes`.
1. Change the code in BASE.
2. Bump `$rGTBVersion` in `admin/functions.php` (for example `"9"`). The build refuses a version that does not match.
3. Build the assets from the repo folder:
   `python3 scripts/build_update_code.py "/Users/prabhjotdunglay/Downloads/untitled folder/xtreamcodes/iptv_xtream_codes" 9 /tmp/gtb_v9 --changelog-file changelog.txt --min-version 8`
   (add `--requires-manual --manual-notes-file notes.txt` if needed). Output: `update_code.zip`, `update_code.zip.sha256`, `version.json` in `/tmp/gtb_v9`.
4. On GitHub create a release on a new tag (for example `v9`), tick **This is a pre-release**, and upload all three assets.
5. On a test panel open Settings, choose "Include test releases", click Check, Update, and verify the panel works.
6. Edit the release and untick pre-release. It is now stable and customers see it.
7. If binaries, nginx config or the database schema change, build with `--requires-manual` (the panel then only shows the notes) and also upload a fresh `main_FINAL.zip`.

### Fresh installs, first install of the updater
- Fresh installs still use `main_FINAL.zip` from release v1.
- **`main_FINAL.zip` must be re-uploaded to the v1 release now** because it contains the updater itself. New size: 281,115,860 bytes.
- **The first install of the updater has to come from the new `main_FINAL.zip`.** Old panels have no updater and need the manual route (reinstall, or copy the new files by hand).
- The displayed version stays GTB v8 until you publish v9.

## 25. New GTB ghost logo and favicon set (Odin branding removed)
- **Source:** the user's `ghost.jpg`. The outer black was removed (flood fill on a cleaned mask, 1px erode, 0.6px feather) so the images are transparent. Thin ghost arm outlines that touch the outside are partly lost, so the white edge is faint on light backgrounds.
- **Master:** `assets/ghost_master.png` in this repo (812x707 RGBA). Rebuild all derived images from it; do not depend on a Downloads folder.
- **Replaced** (BASE = `xtreamcodes/iptv_xtream_codes/`, old -> new bytes):
  - `admin/assets/images/logo.png` and `logo-back.png`: 35018 -> 43494 (666x172)
  - `alogo-back.png`: 66216 -> 74125 (1025x257)
  - `logo-sm.png`: 15032 -> 13533 (146x172)
  - `admin/assets/images/favicon.ico`: 7227 -> 20620 (frames 16, 32, 48, 64, 128)
  - `admin/favicon.ico` and `wwwdir/favicon.ico`: 15406 -> 20620, same bytes as the file above. These two were Odin leftovers and are now replaced.
  - Eight Odin/Viking wallpapers (`bg_odin.png`, `bgpro_odin.png`, `bgodin2/3/4.png`, `bgproodin2/3/4.png`), same names, 1920x1080, all 223595 bytes (ghost centred on a dark gradient).
- **ASK (open):**
  - The 8 `bg*odin*` wallpapers are not referenced by any PHP/HTML/CSS/JS. They were replaced rather than deleted. Delete them if preferred.
  - No `apple-touch-icon.png` or `icon.png` is referenced by any page, so none was created.
  - `wwwdir/client_area` and `wwwdir/c/template` art is Xtream Codes / Stalker / IPTV, not Odin, and was left alone.
- **Zip:** `main_FINAL.zip` is now 272,991,030 bytes (was 281,115,860). The drop comes from recompressing at default deflate level; content is identical apart from the 15 replaced files. `testzip` passes and all marker checks pass.
- **Not tested:** the images were not viewed in a real browser or on a live panel.
- **Reminder:** re-upload `main_FINAL.zip` to the v1 release.
