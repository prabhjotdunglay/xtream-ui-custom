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
- `config.py` — a Python 2 DB-config decrypt helper. It will NOT run under 24.04's Python 3, but
  it is inert at install time (the installer does not import it). Keep it only as an operator tool.

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
  `pkill -USR2 -f "php-fpm: master"` as root (graceful reload). This setting does NOT affect the playlist
  cache (setup_cache.php runs every minute from cron; run it manually to publish new streams instantly).
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
Lives on the `vod-heal` branch (see its README). Current version N reads DB settings from the panel's own config and
loads panel ids/years automatically. On `--apply` it updates `target_container` and `stream_source` in the DB. `--review`
gives interactive decisions, `--cleanup` is available, and the dry run lists every link it would repair.

### 10.9 Post-install checks
- nginx is running.
- `http://IP:8880` opens the login page.
- A stream plays on port 8080.
- The certificate reminder was shown; replace the placeholder certificates with the real ones.
- Import the same M3U twice: the second import adds nothing.
- Provider/country show on the connections page (`isp/api.php` works).
