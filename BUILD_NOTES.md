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
- `admin/functions.php` — `$rEarlyAccess` brand string `" ODIN v"` → `" XtreamUI v"`.
- `admin/settings.php` — visible settings-tab label `>ODIN<` → `>XtreamUI<` (`#odin`/`id="odin"`
  anchors kept in sync, tab still toggles).
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
  server block; robust no-op index.php sed).
- `BUILD_NOTES.md` — **new** (this file).

Intentionally unchanged:
- `bin/` (ffmpeg 2023 + ffmpeg_2018 fallback + ffprobe* + youtube*).
- The 3 kept php-fpm pool configs `php/etc/{VaiIb8,JdlJXm,CWcfSP}.conf`.
- `database.sql`, nginx/rtmp `.conf` files, and the obfuscated `wwwdir` client API.
