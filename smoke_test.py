#!/usr/bin/env python3
"""
Read-only smoke test for the custom Xtream-UI panel. Run on the server:

    python3 smoke_test.py                          # admin / admin on :25500
    python3 smoke_test.py --pass 'NEWPASSWORD'
    python3 smoke_test.py --line user:pass         # also checks the client playlist

It only issues GET requests (plus the login POST). It never follows logout/delete style links.
Checks: services + ports, adopted binary versions, live MariaDB settings, every page linked from
the admin menu (HTTP status, redirect to login, response time), and the new PHP errors that
those requests wrote to nginx's error.log (grouped per file).
"""
import argparse, http.cookiejar, os, re, subprocess, sys, time, urllib.parse, urllib.request, urllib.error

ap = argparse.ArgumentParser()
ap.add_argument("--url", default="http://127.0.0.1:25500")
ap.add_argument("--client", default="http://127.0.0.1:25461")
ap.add_argument("--dir", default="/home/xtreamcodes/iptv_xtream_codes")
ap.add_argument("--user", default="admin")
ap.add_argument("--pass", dest="pw", default="admin")
ap.add_argument("--line", default="", help="USER:PASS of a test line to check the playlist")
ap.add_argument("--max-pages", type=int, default=250)
a = ap.parse_args()

fails, infos = [], []
def ok(msg): print("  PASS  " + msg)
def bad(msg): print("  FAIL  " + msg); fails.append(msg)
def info(msg): print("  info  " + msg); infos.append(msg)
def head(t): print("\n== " + t)
def run(cmd, timeout=15):
    try:
        r = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, timeout=timeout)
        return r.stdout.strip()
    except Exception as e:
        return ""

# ---------------------------------------------------------------- services
head("Services and ports")
ps = run("ps -eo args")
wanted = {
    "nginx master": "nginx: master process " + a.dir + "/nginx/sbin/nginx",
    "nginx_rtmp master": "nginx: master process " + a.dir + "/nginx_rtmp/sbin/nginx_rtmp",
    "php-fpm VaiIb8": "VaiIb8.conf", "php-fpm JdlJXm": "JdlJXm.conf", "php-fpm CWcfSP": "CWcfSP.conf",
    "signal receiver": "XC Signal Receiver", "pipe_reader": "pipe_reader.php",
    "panel monitor": "XC Panel Monitor", "watchdog": "Server WatchDog",
}
for name, needle in wanted.items():
    n = sum(1 for l in ps.splitlines() if needle in l and "grep" not in l)
    (ok if n >= 1 else bad)("%s running (%d process%s)" % (name, n, "" if n == 1 else "es"))
listen = run("ss -ltn")
for port, what in [(25461, "client HTTP"), (25463, "client HTTPS"), (25500, "admin"), (8805, "ISP lookup"), (7999, "MariaDB")]:
    (ok if re.search(r":%d\b" % port, listen) else bad)("port %d (%s) listening" % (port, what))

# ---------------------------------------------------------------- versions / settings
head("Adopted components (installed versions)")
for label, cmd in [("PHP", a.dir + "/php/bin/php -v | head -1"), ("nginx", a.dir + "/nginx/sbin/nginx -v 2>&1"),
                   ("nginx_rtmp", a.dir + "/nginx_rtmp/sbin/nginx_rtmp -v 2>&1"), ("ffmpeg", a.dir + "/bin/ffmpeg -version 2>&1 | head -1")]:
    out = run(cmd)
    info("%-10s %s" % (label, out.splitlines()[0] if out else "(could not run)"))
head("MariaDB settings that are live right now")
want = "'max_connections','innodb_buffer_pool_size','innodb_flush_log_at_trx_commit','thread_handling','thread_pool_size','performance_schema','query_cache_type','max_statement_time'"
out = run("mysql -u root -N -e \"SHOW VARIABLES WHERE Variable_name IN (%s)\"" % want)
if out:
    for l in out.splitlines():
        info(l.replace("\t", " = "))
    if "pool-of-threads" in out: ok("thread pool enabled")
    else: bad("thread_handling is not pool-of-threads (my.cnf not applied?)")
else:
    info("could not query MariaDB as root (skipped)")
for t in ("odin_blocker", "signals", "streams_sys", "admin_settings"):
    r = run("mysql -u root -N -e \"SHOW TABLES FROM xtream_iptvpro LIKE '%s'\"" % t)
    (ok if r else bad)("table %s exists" % t)

# ---------------------------------------------------------------- admin crawl
head("Admin panel: login and every menu page")
log_path = a.dir + "/logs/error.log"
log_off = os.path.getsize(log_path) if os.path.exists(log_path) else 0
jar = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
def get(url, data=None, timeout=40):
    t = time.time()
    try:
        req = urllib.request.Request(url, data=data, headers={"User-Agent": "xc-smoke-test"})
        with op.open(req, timeout=timeout) as r:
            return r.getcode(), r.geturl(), r.read().decode("utf-8", "replace"), time.time() - t
    except urllib.error.HTTPError as e:
        return e.code, url, e.read().decode("utf-8", "replace"), time.time() - t
    except Exception as e:
        return 0, url, str(e), time.time() - t

get(a.url + "/login.php")
code, final, body, _ = get(a.url + "/login.php", urllib.parse.urlencode({"username": a.user, "password": a.pw, "referrer": ""}).encode())
code, final, dash, _ = get(a.url + "/dashboard.php")
if code != 200 or urllib.parse.urlparse(final).path.endswith("/login.php") or 'name="password"' in dash:
    bad("login failed (HTTP %s, ended at %s). Pass the real password with --pass" % (code, final))
    print("\nCannot crawl without a session."); sys.exit(1)
ok("logged in as %s" % a.user)

skip = re.compile(r"logout|delete|remove|kill|flush|clear|reset|install_server|mass_delete|db_sql|restore|backup=|download", re.I)
links, seen = [], set()
for html in (dash,):
    for m in re.finditer(r'href=["\'](?:\./|/)?([A-Za-z0-9_]+\.php(?:\?[^"\'#]*)?)["\']', html):
        l = m.group(1)
        if skip.search(l) or l in seen: continue
        seen.add(l); links.append(l)
links = links[:a.max_pages]
info("%d distinct menu pages found on the dashboard" % len(links))
rows, relogin = [], 0
for l in links:
    code, final, body, dt = get(a.url + "/" + l)
    lost = urllib.parse.urlparse(final).path.endswith("/login.php") and not l.startswith("login")
    if lost: relogin += 1
    rows.append((l, code, dt, lost, body))
    if code >= 500 or code == 0: bad("%-34s HTTP %s" % (l, code))
    elif lost: bad("%-34s sent back to login (session or permission problem)" % l)
    elif code == 404: bad("%-34s HTTP 404 (if a --line check: 404 means no such line; the firewall has no marker for it)" % l)
good = sum(1 for r in rows if r[1] == 200 and not r[3])
(ok if good == len(rows) else info)("%d of %d pages returned 200 with a valid session" % (good, len(rows)))
slow = sorted(rows, key=lambda r: -r[2])[:5]
info("slowest pages: " + ", ".join("%s %.2fs" % (r[0], r[2]) for r in slow))

# ---------------------------------------------------------------- new PHP errors
head("PHP errors written during the crawl (nginx error.log)")
new = ""
if os.path.exists(log_path):
    with open(log_path, "rb") as f:
        f.seek(log_off); new = f.read().decode("utf-8", "replace")
pat = re.compile(r"PHP (Fatal error|Parse error|Warning|Notice|Deprecated):\s+(.*?) in (/\S+?\.php)(?: on line (\d+))?(?=PHP message|\"|$)")
groups = {}
for m in pat.finditer(new):
    level, msg, path, line = m.groups()
    key = (level, os.path.basename(path), re.sub(r"\s+", " ", msg)[:110], line)
    groups[key] = groups.get(key, 0) + 1
fatal = {k: v for k, v in groups.items() if k[0] in ("Fatal error", "Parse error")}
if fatal:
    for (lv, f, msg, line), n in sorted(fatal.items()): bad("%s in %s:%s x%d  %s" % (lv, f, line, n, msg))
else:
    ok("no PHP fatal or parse errors")
warn = {k: v for k, v in groups.items() if k[0] not in ("Fatal error", "Parse error")}
if warn:
    info("%d distinct warnings/notices (not failures; review the top ones):" % len(warn))
    for (lv, f, msg, line), n in sorted(warn.items(), key=lambda kv: -kv[1])[:15]:
        print("          %-8s %s:%s x%d  %s" % (lv, f, line, n, msg))
else:
    ok("no PHP warnings either")

# ---------------------------------------------------------------- client playlist
if a.line:
    head("Client side")
    u, p = a.line.split(":", 1)
    code, _, body, dt = get(a.client + "/get.php?username=%s&password=%s&type=m3u_plus&output=ts" % (urllib.parse.quote(u), urllib.parse.quote(p)))
    if code == 200 and body.startswith("#EXTM3U"):
        ok("playlist for %s: %d channels (%.2fs)" % (u, body.count("#EXTINF"), dt))
    else:
        bad("playlist for %s returned HTTP %s (%s)" % (u, code, body[:60].replace("\n", " ")))

head("Summary")
print("  %d failure%s, %d info line%s" % (len(fails), "" if len(fails) == 1 else "s", len(infos), "" if len(infos) == 1 else "s"))
sys.exit(1 if fails else 0)
