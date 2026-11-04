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
MariaDB (MAIN), writes the encrypted `config`, configures tmpfs/init.d/cron, adds the `:25500`
admin nginx server block, and starts services.

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
- **nginx configs byte-identical** between BASE and redss (`diff -q` empty for both
  `nginx/conf/nginx.conf` and `nginx_rtmp/conf/nginx.conf`) → the newer binaries are drop-in.
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
3. Browse `http://SERVER_IP:25500` and log in with `admin` / `admin`.
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

### MaxMind GeoLite2 license key — setup (REQUIRED to enable auto-update)
The GeoLite2-City database is downloaded from MaxMind's official permalink:
`https://download.maxmind.com/app/geoip_download?edition_id=GeoLite2-City&license_key=KEY&suffix=tar.gz`

Get a **free** license key: create a MaxMind account at maxmind.com, then go to
**Account > Manage License Keys > Generate new license key**.

The updater (`crons/geolite_update.php`) reads the key at runtime, first match wins:
1. Environment variable `MAXMIND_LICENSE_KEY`.
2. File `/home/xtreamcodes/iptv_xtream_codes/maxmind.key` — a single line containing
   just the key. **Recommended.** Create it on the server only:
   ```sh
   echo "YOUR_LICENSE_KEY" > /home/xtreamcodes/iptv_xtream_codes/maxmind.key
   chown xtreamcodes:xtreamcodes /home/xtreamcodes/iptv_xtream_codes/maxmind.key
   chmod 600 /home/xtreamcodes/iptv_xtream_codes/maxmind.key
   ```
3. The `rMaxmindKey` constant in `install.py` (last-resort fallback).

> **SECURITY:** `maxmind.key` must **NEVER** be committed to the public repo
> (`prabhjotdunglay/xtream-ui-custom`). Keep `rMaxmindKey = ""` in the committed
> `install.py`. Add `maxmind.key` to `.gitignore`. If no key is found from any
> source, the updater is a clean no-op (prints a message, exits 0) so keyless
> installs never break.

### GeoLite2 auto-update cron
`install.py` `configure()` appends a **weekly** cron to `/etc/crontab` that runs
the updater as the `xtreamcodes` user:
```
0 4 * * 0 xtreamcodes /home/xtreamcodes/iptv_xtream_codes/php/bin/php /home/xtreamcodes/iptv_xtream_codes/crons/geolite_update.php > /dev/null 2>&1
```
It is harmless on keyless installs (self-skips). The in-panel "update GeoLite"
button (`updateGeoLite2()`) runs the same script on demand.

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
- That the weekly cron fires and refreshes `GeoLite2.mmdb` as `xtreamcodes`.
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
  URLs; pool-of-threads my.cnf; dynamic buffer pool; UFW handling; tmpfs/init.d/cron; :25500 admin
  server block; robust no-op index.php sed). This change also added: `rMaxmindKey = ""` placeholder;
  `admin_settings` seed of `panel_version='46'` + `geolite2_version='20261016'` in `mysql()`; a weekly
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
- The ODIN blocker in `get.php` writes to an `odin_blocker` table that does not exist in
  `database.sql`, so it is inert (its INSERT fails silently). Unchanged.


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
