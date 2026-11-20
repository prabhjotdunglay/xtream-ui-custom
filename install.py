#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# GTB mods Installer (Ubuntu 24.04 only, PHP 7.4, no IonCube)
#
# Structure is based on a community Xtream-UI installer but has been
# neutralised and hardened for this custom build:
#   - 24.04 ONLY (hard refusal on any other release)
#   - No IonCube loader is installed or referenced (admin is decoded plaintext PHP)
#   - GitHub release URLs for prabhjotdunglay/xtream-ui-custom
#   - Keeps the pool-of-threads MariaDB my.cnf, dynamic buffer pool sizing,
#     UFW handling, tmpfs fstab entries, init.d + @reboot cron, and the
#     :8880 admin nginx server block (shipped in nginx.conf; ssl on :2053).
#   - Parity with the reference builds (see .agents/tasks/parity/plan.md):
#       * ISP lookup nginx server block on :8805 (MAIN and LB); access restricted to 127.0.0.1 via allow/deny in both locations
#       * odin_blocker table (login brute-force auto-block)
#       * /etc/hosts entries incl. bare xtream-codes.com
#       * optional sudoers nginx-reload grant (OFF by default; XC_SUDO_NGINX_RELOAD=Y)
#       * complete runtime directory list (created_channels, movies, delay, ...)
#       * GeoLite2 auto-update (daily /etc/crontab + panel cron + Settings button)
#
import subprocess, os, time, random, string, sys, shutil, socket, zipfile, urllib.request, urllib.error, urllib.parse, json, base64
from itertools import cycle
from zipfile import ZipFile
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

# Prevent apt / needrestart from hanging on Ubuntu 24.04 (non-interactive).
os.environ['DEBIAN_FRONTEND'] = 'noninteractive'
os.environ['NEEDRESTART_MODE'] = 'a'
os.environ['NEEDRESTART_SUSPEND'] = '1'

# Release assets (main_FINAL.zip as "latest", sub_FINAL.zip under tag v1)
# must be uploaded to the GitHub release. See BUILD_NOTES.md.
rDownloadURL = {
    "main": "https://github.com/prabhjotdunglay/xtream-ui-custom/releases/latest/download/main_FINAL.zip",
    "sub": "https://github.com/prabhjotdunglay/xtream-ui-custom/releases/download/v1/sub_FINAL.zip",
}

# Raw fallbacks for assets the panel expects at runtime.
# GeoLite2.mmdb already ships inside the release ZIP; it is only fetched if missing.
rRawBaseURL = "https://raw.githubusercontent.com/prabhjotdunglay/xtream-ui-custom/main"
rGeoLiteURL = rRawBaseURL + "/GeoLite2.mmdb"
rPidMonitorURL = rRawBaseURL + "/pid_monitor.php"
# LB mode does not reimplement the znuff-style LB steps here; it downloads and
# runs the standalone install-lb script (same file as the one-liner uses), so
# the two cannot drift. See install-lb for what it does.
rInstallLBURL = rRawBaseURL + "/install-lb"

# GeoLite2: crons/geolite_update.php ships with the MaxMind account ID / license key
# built in, keeps GeoLite2.mmdb current automatically (checked every minute by the
# panel's own crontab, downloads only when the file is older than 3 days), and is
# what Settings > "Update now" runs. To use a different MaxMind account, write
# "ACCOUNT_ID:LICENSE_KEY" to /home/xtreamcodes/iptv_xtream_codes/maxmind.key.

rPackages = ["curl", "libcurl4", "libxslt1-dev", "libgeoip-dev", "libonig-dev", "e2fsprogs", "wget", "mcrypt", "nscd", "htop", "zip", "unzip", "mc", "mariadb-server", "libpng16-16", "python3-paramiko", "python-is-python3", "libzip4t64", "iptables", "cron", "sudo", "libfreetype6", "libsqlite3-0", "libfcgi-bin"]
rInstall = {"MAIN": "main", "LB": "sub"}
rApplied = []  # steps that completed; printed at the end so a failed step is visible
rErrors = []   # problems found by the package / library / health checks; any entry = "finished with errors"

# Package handling (apt output goes to this log; see aptRun()).
rAptLog = "/var/log/gtb-install-apt.log"
# These must be installed or the installation stops. Everything else in rPackages (htop, mc) only warns.
rRequiredPackages = ["libcurl4", "libxslt1-dev", "libgeoip-dev", "libonig-dev", "mcrypt", "nscd", "zip", "unzip", "mariadb-server", "libpng16-16", "python3-paramiko", "python-is-python3", "libzip4t64", "cron", "sudo", "libfreetype6", "libsqlite3-0", "libfcgi-bin", "iptables", "curl", "wget", "e2fsprogs"]
# Runtime libraries the shipped PHP extensions / binaries load, installed by exact name.
rRuntimePackages = [["libmcrypt4"], ["libgeoip1t64", "libgeoip1"]]
# soname -> Debian/Ubuntu 24.04 package, used when ldd reports "not found".
rLibPackages = {
    "libmcrypt.so.4": "libmcrypt4",
    "libGeoIP.so.1": "libgeoip1t64",
    "libonig.so.5": "libonig5",
    "libzip.so.4": "libzip4t64",
    "libpng16.so.16": "libpng16-16",
    "libfreetype.so.6": "libfreetype6",
    "libxslt.so.1": "libxslt1.1",
    "libsqlite3.so.0": "libsqlite3-0",
    "libcurl.so.4": "libcurl4",
}
rBaseDir = "/home/xtreamcodes/iptv_xtream_codes"

# MariaDB my.cnf tuned for Xtream Codes (pool-of-threads, {BUFFER_POOL_SIZE} template,
# max_connections=8192, innodb_flush_log_at_trx_commit=0, max_statement_time=0, innodb_log_file_size=512M, port 7999).
rMySQLCnf = base64.b64decode("IyBYdHJlYW0gQ29kZXMKW2NsaWVudF0KcG9ydCAgICAgICAgICAgICAgICAgICAgICAgICAgICA9IDMzMDYKCltteXNxbGRfc2FmZV0KbmljZSAgICAgICAgICAgICAgICAgICAgICAgICAgICA9IDAKI21hbGxvYyBzZXR0aW5ncwojbWFsbG9jLWxpYj0vdXNyL2xpYi94ODZfNjQtbGludXgtZ251L2xpYnRjbWFsbG9jLnNvLjQuMy4wCgpbbXlzcWxkXQp1c2VyICAgICAgICAgICAgICAgICAgICAgICAgICAgID0gbXlzcWwKcG9ydCAgICAgICAgICAgICAgICAgICAgICAgICAgICA9IDc5OTkKYmFzZWRpciAgICAgICAgICAgICAgICAgICAgICAgICA9IC91c3IKZGF0YWRpciAgICAgICAgICAgICAgICAgICAgICAgICA9IC92YXIvbGliL215c3FsCnRtcGRpciAgICAgICAgICAgICAgICAgICAgICAgICAgPSAvdG1wCmxjLW1lc3NhZ2VzLWRpciAgICAgICAgICAgICAgICAgPSAvdXNyL3NoYXJlL215c3FsCnNraXAtZXh0ZXJuYWwtbG9ja2luZwpza2lwLW5hbWUtcmVzb2x2ZSAgICAgICAgICAgICAgID0xCmJpbmQtYWRkcmVzcyAgICAgICAgICAgICAgICAgICAgPSAqCgprZXlfYnVmZmVyX3NpemUgICAgICAgICAgICAgICAgID0gMTI4TQpteWlzYW1fc29ydF9idWZmZXJfc2l6ZSAgICAgICAgID0gNE0KbWF4X2FsbG93ZWRfcGFja2V0ICAgICAgICAgICAgICA9IDY0TQpteWlzYW0tcmVjb3Zlci1vcHRpb25zICAgICAgICAgID0gQkFDS1VQCm1heF9sZW5ndGhfZm9yX3NvcnRfZGF0YSAgICAgICAgPSA4MTkyCnF1ZXJ5X2NhY2hlX2xpbWl0ICAgICAgICAgICAgICAgPSAwCnF1ZXJ5X2NhY2hlX3NpemUgICAgICAgICAgICAgICAgPSAwCnF1ZXJ5X2NhY2hlX3R5cGUgICAgICAgICAgICAgICAgPSAwCmV4cGlyZV9sb2dzX2RheXMgICAgICAgICAgICAgICAgPSAxMAptYXhfYmlubG9nX3NpemUgICAgICAgICAgICAgICAgID0gMTAwTQptYXhfY29ubmVjdGlvbnMgICAgICAgICAgICAgICAgID0gODE5MgpiYWNrX2xvZyAgICAgICAgICAgICAgICAgICAgICAgID0gNDA5NgpvcGVuX2ZpbGVzX2xpbWl0ICAgICAgICAgICAgICAgID0gMjAyNDAKaW5ub2RiX29wZW5fZmlsZXMgICAgICAgICAgICAgICA9IDIwMjQwCm1heF9jb25uZWN0X2Vycm9ycyAgICAgICAgICAgICAgPSAzMDcyCnRhYmxlX29wZW5fY2FjaGUgICAgICAgICAgICAgICAgPSA0MDk2CnRhYmxlX2RlZmluaXRpb25fY2FjaGUgICAgICAgICAgPSA0MDk2CnRtcF90YWJsZV9zaXplICAgICAgICAgICAgICAgICAgPSAxRwptYXhfaGVhcF90YWJsZV9zaXplICAgICAgICAgICAgID0gMUcKCm1heF9zdGF0ZW1lbnRfdGltZSA9IDAKCmlubm9kYl9idWZmZXJfcG9vbF9zaXplICAgICAgICAgPSB7QlVGRkVSX1BPT0xfU0laRX0KaW5ub2RiX3JlYWRfaW9fdGhyZWFkcyAgICAgICAgICA9IDY0Cmlubm9kYl93cml0ZV9pb190aHJlYWRzICAgICAgICAgPSA2NAojaW5ub2RiX3RocmVhZF9jb25jdXJyZW5jeSAgICAgICA9IDAKaW5ub2RiX2ZsdXNoX2xvZ19hdF90cnhfY29tbWl0ICA9IDAKaW5ub2RiX2ZsdXNoX21ldGhvZCAgICAgICAgICAgICA9IE9fRElSRUNUCmlubm9kYl9sb2dfZmlsZV9zaXplICAgICAgICAgICAgPSA1MTJNCnBlcmZvcm1hbmNlX3NjaGVtYSAgICAgICAgICAgICAgPSAwCmlubm9kYi1maWxlLXBlci10YWJsZSAgICAgICAgICAgPSAxCmlubm9kYl9pb19jYXBhY2l0eSAgICAgICAgICAgICAgPSAyMDAwMAppbm5vZGJfdGFibGVfbG9ja3MgICAgICAgICAgICAgID0gMAppbm5vZGJfbG9ja193YWl0X3RpbWVvdXQgICAgICAgID0gMAoKc3FsX21vZGUgICAgICAgICAgICAgICAgICAgICAgICA9ICJOT19FTkdJTkVfU1VCU1RJVFVUSU9OIgoKW21hcmlhZGJdCgp0aHJlYWRfY2FjaGVfc2l6ZSAgICAgICAgICAgICAgID0gODE5Mgp0aHJlYWRfaGFuZGxpbmcgICAgICAgICAgICAgICAgID0gcG9vbC1vZi10aHJlYWRzCnRocmVhZF9wb29sX3NpemUgICAgICAgICAgICAgICAgPSAxMgp0aHJlYWRfcG9vbF9pZGxlX3RpbWVvdXQgICAgICAgID0gMjAKdGhyZWFkX3Bvb2xfbWF4X3RocmVhZHMgICAgICAgICA9IDEwMjQKCltteXNxbGR1bXBdCnF1aWNrCnF1b3RlLW5hbWVzCm1heF9hbGxvd2VkX3BhY2tldCAgICAgICAgICAgICAgPSAxMjhNCmNvbXBsZXRlLWluc2VydAoKW215c3FsXQoKW2lzYW1jaGtdCmtleV9idWZmZXJfc2l6ZSAgICAgICAgICAgICAgICAgPSAxNk0K")

rVersions = {
    "24.04": "noble"
}

class col:
    BLACK = '\033[30m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    LIGHT_GRAY = '\033[37m'
    DARK_GRAY = '\033[90m'
    BRIGHT_RED = '\033[91m'
    BRIGHT_GREEN = '\033[92m'
    BRIGHT_YELLOW = '\033[93m'
    BRIGHT_BLUE = '\033[94m'
    BRIGHT_MAGENTA = '\033[95m'
    BRIGHT_CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    ENDC = '\033[0m'

def generate(length=19): return ''.join(random.choice(string.ascii_letters + string.digits) for i in range(length))

def getIP():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    return s.getsockname()[0]

def getVersion():
    try: return os.popen("lsb_release -d").read().split(":")[-1].strip()
    except: return ""

def printc(rText, rColour=col.BRIGHT_GREEN, rPadding=0, rLimit=46):
    print("%s +-------------------------------------------------+ %s" % (rColour, col.ENDC))
    for i in range(rPadding): print("%s |                                                 | %s" % (rColour, col.ENDC))
    array = [rText[i:i+rLimit] for i in range(0, len(rText), rLimit)]
    for i in array : print("%s | %s%s%s | %s" % (rColour, " "*round(23-(len(i)/2)), i, " "*round(46-(22-(len(i)/2))-len(i)), col.ENDC))
    for i in range(rPadding): print("%s |                                                 | %s" % (rColour, col.ENDC))
    print("%s +-------------------------------------------------+ %s" % (rColour, col.ENDC))
    print(" ")

def is_installed(package_name):
    try:
        subprocess.run(['dpkg', '-s', package_name], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True
    except subprocess.CalledProcessError:
        return False

def aptEnv():
    rEnv = dict(os.environ)
    rEnv["DEBIAN_FRONTEND"] = "noninteractive"
    rEnv["NEEDRESTART_MODE"] = "a"
    rEnv["NEEDRESTART_SUSPEND"] = "1"
    return rEnv

def protectFromAutoRestart():
    # Same override as install-lb. The MAIN install creates no systemd units (start_services.sh via
    # /etc/init.d + @reboot cron), so these rules only keep needrestart away from nginx/php-fpm
    # processes and any LB-style units that may exist on the box. Must exist before the first apt call.
    try:
        os.makedirs("/etc/needrestart/conf.d", exist_ok=True)
        with open("/etc/needrestart/conf.d/gtb.conf", "w") as rFile:
            rFile.write("$nrconf{override_rc}{qr(^fpm@)} = 0;\n$nrconf{override_rc}{qr(^nginx-xc)} = 0;\n$nrconf{override_rc}{qr(^xc-start)} = 0;\n")
    except OSError as e:
        printc("Could not write needrestart override: %s" % e.strerror, col.BRIGHT_YELLOW)

def aptBusy():
    # True while any process holds an apt/dpkg lock or an apt/dpkg/unattended-upgrades process runs.
    rLocks = [f for f in ["/var/lib/dpkg/lock-frontend", "/var/lib/dpkg/lock", "/var/lib/apt/lists/lock", "/var/cache/apt/archives/lock"] if os.path.exists(f)]
    try:
        if rLocks and subprocess.run(["fuser"] + rLocks, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
            return True
    except OSError: pass
    for rName in ["apt", "apt-get", "dpkg", "unattended-upgr"]:
        try:
            if subprocess.run(["pgrep", "-x", rName], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
                return True
        except OSError: pass
    return False

def waitForApt(rTimeout=1200, rInterval=5):
    # Never deletes lock files: they are flock-based and harmless when no process holds them.
    rStart = time.time()
    rShown = False
    while aptBusy():
        if not rShown:
            printc("Waiting for another apt process to finish...", col.BRIGHT_YELLOW)
            rShown = True
        if time.time() - rStart > rTimeout:
            printc("Another apt process still running after %d min; continuing (apt will wait on its own lock)." % (rTimeout // 60), col.BRIGHT_YELLOW)
            return False
        time.sleep(rInterval)
    return True

def aptRun(rArgs):
    # Runs apt-get/dpkg with all output appended to rAptLog. Returns the exit code.
    rCmd = list(rArgs)
    if rCmd[0] == "apt-get":
        rCmd = ["apt-get", "-y", "-o", "DPkg::Lock::Timeout=300", "-o", "Dpkg::Options::=--force-confdef", "-o", "Dpkg::Options::=--force-confold"] + rCmd[1:]
    try:
        with open(rAptLog, "a") as rLog:
            rLog.write("\n$ %s\n" % " ".join(rCmd))
            rLog.flush()
            return subprocess.run(rCmd, stdin=subprocess.DEVNULL, stdout=rLog, stderr=subprocess.STDOUT, env=aptEnv()).returncode
    except OSError as e:
        printc("Cannot run %s: %s" % (rCmd[0], e.strerror), col.BRIGHT_RED)
        return 127

def aptLogTail(rLines=8):
    try:
        with open(rAptLog, "r", errors="replace") as rLog: return [l.rstrip() for l in rLog.readlines()[-rLines:] if l.strip()]
    except OSError: return []

def pkgInstalled(rPackage):
    try:
        rOut = subprocess.run(["dpkg", "-s", rPackage], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, universal_newlines=True)
    except OSError: return False
    return rOut.returncode == 0 and "Status: install ok installed" in rOut.stdout

def aptRepair():
    waitForApt()
    aptRun(["dpkg", "--configure", "-a"])
    aptRun(["apt-get", "install", "-f"])

def installPackage(rPackage, rRequired=True, rTries=3):
    # Install one package, verify it with dpkg -s, retry (with update + repair in between).
    if pkgInstalled(rPackage): return True
    printc("Installing %s" % rPackage)
    for rTry in range(1, rTries + 1):
        waitForApt()
        rRet = aptRun(["apt-get", "install", rPackage])
        if rRet == 0 and pkgInstalled(rPackage): return True
        printc("%s: install attempt %d/%d failed (apt exit %d)" % (rPackage, rTry, rTries, rRet), col.BRIGHT_YELLOW)
        for rLine in aptLogTail(4): print("    " + rLine)
        if rTry < rTries:
            time.sleep(5)
            aptRepair()
            aptRun(["apt-get", "update"])
    if rRequired:
        printc("REQUIRED package %s could not be installed. See %s" % (rPackage, rAptLog), col.BRIGHT_RED)
    else:
        printc("Optional package %s could not be installed (continuing). See %s" % (rPackage, rAptLog), col.BRIGHT_YELLOW)
    return False

def ensureNscd():
    # The panel's static nginx resolves the "user xtreamcodes" directive through glibc/nscd; make sure nscd runs.
    if not pkgInstalled("nscd"): return False
    os.system("systemctl enable --now nscd > /dev/null 2>&1")
    rActive = subprocess.run(["systemctl", "is-active", "nscd"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, universal_newlines=True).stdout.strip() == "active"
    if not rActive:
        printc("Warning: nscd is installed but not active (systemctl status nscd)", col.BRIGHT_YELLOW)
    return rActive

def ensurePackages():
    # Runs after the system upgrade. Returns False if a REQUIRED package is missing.
    for rPackage in rPackages:
        if not installPackage(rPackage, rPackage in rRequiredPackages) and rPackage in rRequiredPackages:
            return False
    waitForApt()
    aptRun(["apt-get", "install", "-f"])
    for rCandidates in rRuntimePackages:
        if not any(installPackage(rCand) for rCand in rCandidates):
            printc("None of %s could be installed. See %s" % (", ".join(rCandidates), rAptLog), col.BRIGHT_RED)
            return False
    ensureNscd()
    return True

def prepare(rType="MAIN"):
    global rPackages
    if rType != "MAIN":
        rPackages = [p for p in rPackages if p != "mariadb-server"]

    # UFW handling
    ufw_active = os.system("ufw status 2>/dev/null | grep -q 'Status: active'") == 0
    if ufw_active:
        printc("UFW Firewall detected active!", col.BRIGHT_YELLOW)
        printc("[1] Disable UFW (recommended for performance)", col.WHITE)
        printc("[2] Allow required ports only (22, 80, 443, 8080, 8880, 2053, 25462, 7999, 31210)", col.WHITE)
        rUFW = input("  Choice [1/2] (default: 1): ").strip() or "1"
        if rUFW == "2":
            for port in ["22", "80", "443", "8080", "8880", "2053", "25462", "31210"]:
                os.system("ufw allow %s > /dev/null 2>&1" % port)
            if rType.upper() == "MAIN":
                os.system("ufw allow 7999 > /dev/null 2>&1")
            printc("UFW: required ports allowed", col.GREEN)
        else:
            os.system("ufw disable > /dev/null 2>&1")
            os.system("systemctl stop ufw > /dev/null 2>&1")
            os.system("systemctl disable ufw > /dev/null 2>&1")
            os.system("systemctl mask ufw > /dev/null 2>&1")
            printc("UFW: disabled", col.GREEN)
    else:
        os.system("ufw disable > /dev/null 2>&1")
        os.system("systemctl stop ufw > /dev/null 2>&1")
        os.system("systemctl disable ufw > /dev/null 2>&1")
        os.system("systemctl mask ufw > /dev/null 2>&1")
    printc("Preparing Installation")

    if os.path.isfile('/home/xtreamcodes/iptv_xtream_codes/config'):
        shutil.copyfile('/home/xtreamcodes/iptv_xtream_codes/config', '/tmp/config.xtmp')

    if os.path.isfile('/home/xtreamcodes/iptv_xtream_codes/config'):
        os.system('chattr -i /home/xtreamcodes/iptv_xtream_codes/GeoLite2.mmdb > /dev/null')

    # Lock files are never deleted (that corrupts a running apt/unattended-upgrades). Wait for the
    # holder to finish instead; if none is running, finish any half-configured packages.
    protectFromAutoRestart()
    waitForApt()
    aptRun(["dpkg", "--configure", "-a"])

    printc("Updating Operating System")
    waitForApt()
    if aptRun(["apt-get", "update"]) != 0:
        printc("apt-get update reported an error (see %s)" % rAptLog, col.BRIGHT_YELLOW)
    waitForApt()
    if aptRun(["apt-get", "full-upgrade"]) != 0:
        printc("System upgrade reported an error, continuing (see %s)" % rAptLog, col.BRIGHT_YELLOW)

    if not ensurePackages():
        printc("Installation stopped: a required package is missing. Log: %s" % rAptLog, col.BRIGHT_RED, 1)
        return False

    try:
        subprocess.run("getent passwd xtreamcodes > /dev/null 2>&1", shell=True, check=True)
    except subprocess.CalledProcessError:
        printc("Creating user xtreamcodes")
        subprocess.run("adduser --system --shell /bin/false --group --disabled-login xtreamcodes > /dev/null 2>&1", shell=True)
    # nscd may have cached a failed lookup; flush it, then verify the user really resolves.
    os.system("nscd -i passwd > /dev/null 2>&1")
    ensureNscd()
    if subprocess.run("getent passwd xtreamcodes > /dev/null 2>&1", shell=True).returncode != 0:
        printc("User xtreamcodes does not resolve (getent passwd xtreamcodes)", col.BRIGHT_RED)
        return False

    if not os.path.exists("/home/xtreamcodes"):
        os.mkdir("/home/xtreamcodes")

    return True

def install(rType="MAIN"):
    global rInstall, rDownloadURL
    printc("Downloading Software")

    try:
        rURL = rDownloadURL[rInstall[rType]]
    except KeyError:
        printc("Invalid download URL!", col.BRIGHT_RED)
        return False

    zip_file_path = "/tmp/xtreamcodes.zip"
    try:
        subprocess.run(['curl', '-L', '-s', '-o', zip_file_path, rURL], check=True)
    except subprocess.CalledProcessError:
        printc("Failed to download installation file!", col.BRIGHT_RED)
        return False

    if os.path.exists(zip_file_path):
        printc("Installing Software")
        try:
            with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
                # ZIP top-level dir is iptv_xtream_codes/, extracting into /home/xtreamcodes/
                zip_ref.extractall("/home/xtreamcodes/")
        except zipfile.BadZipFile:
            printc(f"Error: {zip_file_path} is not a valid zip file!", col.BRIGHT_RED)
            return False

        try:
            os.remove(zip_file_path)
        except OSError as e:
            printc(f"Error removing file {zip_file_path}: {e.strerror}")
        checkLibs()
        return True

    printc("Failed to download installation file!", col.BRIGHT_RED)
    return False

def phpLoadedExtensions(rBase=rBaseDir):
    # .so files php.ini loads (extension= / zend_extension=), resolved in the extension dir.
    import glob, re
    rFiles = []
    try: rIni = open(rBase + "/php/lib/php.ini").read()
    except OSError: rIni = ""
    rDirs = glob.glob(rBase + "/php/lib/php/extensions/no-debug-non-zts-*")
    for rName in re.findall(r"^\s*(?:zend_)?extension\s*=\s*\"?([^\s\";]+)", rIni, re.M):
        if not rName.endswith(".so"): rName += ".so"
        if os.path.isabs(rName): rFiles.append(rName); continue
        for rDir in rDirs:
            if os.path.exists(os.path.join(rDir, rName)): rFiles.append(os.path.join(rDir, rName)); break
        else: rFiles.append(os.path.join(rDirs[0], rName) if rDirs else rName)
    return rFiles

def lddMissing(rTargets):
    # {soname: [files that need it]} for every "not found" line ldd prints.
    rMissing = {}
    for rBin in rTargets:
        if not os.path.exists(rBin): continue
        try:
            rOut = subprocess.run(["ldd", rBin], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True).stdout
        except OSError:
            continue
        for rLine in rOut.splitlines():
            if "not found" in rLine and "=>" in rLine:
                rMissing.setdefault(rLine.split("=>")[0].strip(), []).append(os.path.basename(rBin))
    return rMissing

def checkLibs():
    # Check shared libraries of the bundled PHP, its loaded extensions and ffmpeg/ffprobe (nginx is static).
    # Known missing libraries are installed by package name and re-checked; anything left is reported
    # in red, recorded in rErrors, and the step is NOT listed as applied.
    rBase = rBaseDir
    rTargets = [rBase + "/php/sbin/php-fpm", rBase + "/php/bin/php", rBase + "/bin/ffmpeg", rBase + "/bin/ffprobe"] + phpLoadedExtensions(rBase)
    rMissing = lddMissing(rTargets)
    if rMissing:
        rWanted = sorted(set(rLibPackages[l] for l in rMissing if l in rLibPackages))
        for rPackage in rWanted:
            printc("Missing library, installing %s" % rPackage, col.BRIGHT_YELLOW)
            installPackage(rPackage)
        if rWanted:
            os.system("ldconfig > /dev/null 2>&1")
            rMissing = lddMissing(rTargets)
    if rMissing:
        printc("Missing libraries for PHP/ffmpeg:", col.BRIGHT_RED)
        for rLib in sorted(rMissing):
            printc("%s (needed by %s)%s" % (rLib, ", ".join(sorted(set(rMissing[rLib]))), "" if rLib in rLibPackages else " - unknown package"), col.BRIGHT_RED)
        rErrors.append("missing libraries: " + ", ".join(sorted(rMissing)))
    else:
        rApplied.append("library check (ldd)")

def finalize(rType="MAIN"):
    # Custom: does NOT download any upstream admin release nor overwrite the
    # admin tree. Only fixes permissions/ownership. Creates permissions.sh if missing.
    printc("Finalizing (custom - bundled admin kept)")
    rPerm = "/home/xtreamcodes/iptv_xtream_codes/permissions.sh"
    rNeed = True
    if os.path.exists(rPerm):
        try:
            if "chmod 400 /home/xtreamcodes/iptv_xtream_codes/config" in open(rPerm).read():
                rNeed = False
        except: pass
    if rNeed:
        rLines = [
            "#!/bin/bash",
            "sudo chmod -R 777 /home/xtreamcodes 2>/dev/null",
            "sudo find /home/xtreamcodes/iptv_xtream_codes/admin/ -type f -exec chmod 644 {} \\; 2>/dev/null",
            "sudo find /home/xtreamcodes/iptv_xtream_codes/admin/ -type d -exec chmod 755 {} \\; 2>/dev/null",
            "sudo find /home/xtreamcodes/iptv_xtream_codes/wwwdir/ -type f -exec chmod 644 {} \\; 2>/dev/null",
            "sudo find /home/xtreamcodes/iptv_xtream_codes/wwwdir/ -type d -exec chmod 755 {} \\; 2>/dev/null",
            "sudo chmod +x /home/xtreamcodes/iptv_xtream_codes/nginx/sbin/nginx 2>/dev/null",
            "sudo chmod +x /home/xtreamcodes/iptv_xtream_codes/nginx_rtmp/sbin/nginx_rtmp 2>/dev/null",
            "sudo chmod 400 /home/xtreamcodes/iptv_xtream_codes/config 2>/dev/null",
        ]
        with open(rPerm, "w") as rf:
            rf.write("\n".join(rLines) + "\n")
    os.system("chmod +x %s > /dev/null" % rPerm)
    os.system("%s > /dev/null" % rPerm)
    os.system("chown -R xtreamcodes:xtreamcodes /home/xtreamcodes/ > /dev/null")
    if os.path.exists("/home/xtreamcodes/iptv_xtream_codes/GeoLite2.mmdb"):
        os.system("chattr +i /home/xtreamcodes/iptv_xtream_codes/GeoLite2.mmdb > /dev/null")
    return True

def getBufferPoolSize():
    # Use 50% of total RAM, minimum 1G, maximum 12G.
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal"):
                    kb = int(line.split()[1])
                    gb = max(1, min(12, int(kb / 1024 / 1024 / 2)))
                    return "%dG" % gb
    except: pass
    return "1G"

# odin_blocker: wwwdir/{get,player_api,portal,panel_api}.php INSERT here on every failed login;
# the 10 attempts/min brute-force auto-block (blocked_ips) reads it.
rOdinBlocker = "CREATE TABLE IF NOT EXISTS odin_blocker (id int(11) NOT NULL AUTO_INCREMENT, timestamp datetime DEFAULT NULL, ip varchar(255) DEFAULT NULL, PRIMARY KEY (id)) ENGINE=InnoDB DEFAULT CHARSET=latin1;"

def mysql(rUsername, rPassword):  # handles db setup
    global rMySQLCnf
    printc("Configuring MySQL")
    rCreate = True
    if os.path.exists("/etc/mysql/my.cnf"):
        if open("/etc/mysql/my.cnf", "r").read(14) == "# Xtream Codes": rCreate = False
    if rCreate:
        shutil.copy("/etc/mysql/my.cnf", "/etc/mysql/my.cnf.xc")
        rFile = open("/etc/mysql/my.cnf", "w")
        rFile.write(rMySQLCnf.decode("utf-8").replace("{BUFFER_POOL_SIZE}", getBufferPoolSize()))
        rFile.close()
        os.system("systemctl restart mariadb > /dev/null")
    for i in range(5):
        rMySQLRoot = ""
        print(" ")
        if len(rMySQLRoot) > 0: rExtra = " -p%s" % rMySQLRoot
        else: rExtra = ""
        # Default (as in every earlier version of this installer): drop and recreate the database.
        # To re-run the installer over an existing install WITHOUT wiping its data, run it as
        #   XC_DROP_DB=N python3 install.py
        # No prompt on purpose: an Enter press must never skip creating the database on a fresh box.
        rDrop = os.environ.get("XC_DROP_DB", "Y").strip().upper() != "N"
        try:
            if rDrop:
                os.system('mysql -u root%s -e "DROP DATABASE IF EXISTS xtream_iptvpro; CREATE DATABASE IF NOT EXISTS xtream_iptvpro;" > /dev/null' % rExtra)
                os.system('mysql -u root%s -e "USE xtream_iptvpro; DROP USER IF EXISTS \'%s\'@\'%%\';" > /dev/null' % (rExtra, rUsername))
                os.system("mysql -u root%s xtream_iptvpro < /home/xtreamcodes/iptv_xtream_codes/database.sql > /dev/null" % rExtra)
                os.system('mysql -u root%s -e "USE xtream_iptvpro; DROP TABLE IF EXISTS odin_blocker; %s" > /dev/null' % (rExtra, rOdinBlocker))
                os.system('mysql -u root%s -e "USE xtream_iptvpro; UPDATE settings SET live_streaming_pass = \'%s\', unique_id = \'%s\', crypt_load_balancing = \'%s\';" > /dev/null' % (rExtra, generate(20), generate(10), generate(20)))
                # Pin the displayed version to "GTB v8" (the "46" below stays the internal panel_version; the label
                # comes from $rRelease="GTB" + $rEarlyAccess=" v" + $rGTBVersion="8" in functions.php).
                # panel_version / geolite2_version live in the admin_settings key/value
                # table (type/value), not in `settings`, so seed them there. Seed a
                # current-ish geolite2_version so no GeoLite "update available" nag shows.
                os.system('mysql -u root%s -e "USE xtream_iptvpro; CREATE TABLE IF NOT EXISTS admin_settings (type varchar(255) NOT NULL, value text, PRIMARY KEY (type)) ENGINE=InnoDB DEFAULT CHARSET=latin1; REPLACE INTO admin_settings (type, value) VALUES (\'panel_version\', \'46\'), (\'geolite2_version\', \'20210223\');" > /dev/null' % rExtra)
                os.system('mysql -u root%s -e "USE xtream_iptvpro; REPLACE INTO streaming_servers (id, server_name, domain_name, server_ip, vpn_ip, ssh_password, ssh_port, diff_time_main, http_broadcast_port, total_clients, system_os, network_interface, latency, status, enable_geoip, geoip_countries, last_check_ago, can_delete, server_hardware, total_services, persistent_connections, rtmp_port, geoip_type, isp_names, isp_type, enable_isp, boost_fpm, http_ports_add, network_guaranteed_speed, https_broadcast_port, https_ports_add, whitelist_ips, watchdog_data, timeshift_only) VALUES (1, \'Main Server\', \'\', \'%s\', \'\', NULL, NULL, 0, 8080, 1000, \'%s\', \'eth0\', 0, 1, 0, \'[]\', 0, 0, \'{}\', 3, 0, 25462, \'low_priority\', \'\', \'low_priority\', 0, 1, \'\', 1000, 443, \'\', \'[\"127.0.0.1\",\"\"]\', \'{}\', 0);" > /dev/null' % (rExtra, getIP(), getVersion()))
                os.system('mysql -u root%s -e "USE xtream_iptvpro; REPLACE INTO reg_users (id, username, password, email, member_group_id, verified, status) VALUES (1, \'admin\', \'\\$6\\$rounds=20000\\$xtreamcodes\\$XThC5OwfuS0YwS4ahiifzF14vkGbGsFF1w7ETL4sRRC5sOrAWCjWvQJDromZUQoQuwbAXAFdX3h3Cp3vqulpS0\', \'admin@website.com\', 1, 1, 1);" > /dev/null'  % rExtra)
                os.system('mysql -u root%s -e "CREATE USER \'%s\'@\'%%\' IDENTIFIED BY \'%s\'; GRANT ALL PRIVILEGES ON xtream_iptvpro.* TO \'%s\'@\'%%\' WITH GRANT OPTION; GRANT SELECT, LOCK TABLES ON *.* TO \'%s\'@\'%%\';FLUSH PRIVILEGES;" > /dev/null' % (rExtra, rUsername, rPassword, rUsername, rUsername))
                os.system('mysql -u root%s -e "USE xtream_iptvpro; CREATE TABLE IF NOT EXISTS dashboard_statistics (id int(11) NOT NULL AUTO_INCREMENT, type varchar(16) NOT NULL DEFAULT \'\', time int(16) NOT NULL DEFAULT \'0\', count int(16) NOT NULL DEFAULT \'0\', PRIMARY KEY (id)) ENGINE=InnoDB DEFAULT CHARSET=latin1; INSERT INTO dashboard_statistics (type, time, count) VALUES(\'conns\', UNIX_TIMESTAMP(), 0),(\'users\', UNIX_TIMESTAMP(), 0);\" > /dev/null' % rExtra)
            else:
                # keep existing data, but make sure the brute-force table exists
                os.system('mysql -u root%s -e "USE xtream_iptvpro; %s" > /dev/null' % (rExtra, rOdinBlocker))
            try: os.remove("/home/xtreamcodes/iptv_xtream_codes/database.sql")
            except: pass
            return True
        except: printc("Invalid password! Try again", col.BRIGHT_RED)
    return False

def encrypt(rHost="127.0.0.1", rUsername="user_iptvpro", rPassword="", rDatabase="xtream_iptvpro", rServerID=1, rPort=7999):
    if os.path.isfile('/home/xtreamcodes/iptv_xtream_codes/config'):
        rDecrypt = decrypt()
        rHost = rDecrypt["host"]
        rPassword = rDecrypt["db_pass"]
        rServerID = int(rDecrypt["server_id"])
        rUsername = rDecrypt["db_user"]
        rDatabase = rDecrypt["db_name"]
        rPort = int(rDecrypt["db_port"])
    printc("Encrypting...")
    try: os.remove("/home/xtreamcodes/iptv_xtream_codes/config")
    except: pass

    rf = open('/home/xtreamcodes/iptv_xtream_codes/config', 'wb')
    lestring=''.join(chr(ord(c)^ord(k)) for c,k in zip('{\"host\":\"%s\",\"db_user\":\"%s\",\"db_pass\":\"%s\",\"db_name\":\"%s\",\"server_id\":\"%d\", \"db_port\":\"%d\"}' % (rHost, rUsername, rPassword, rDatabase, rServerID, rPort), cycle('5709650b0d7806074842c6de575025b1')))
    rf.write(base64.b64encode(bytes(lestring, 'ascii')))
    rf.close()


def decrypt():
    rConfigPath = "/home/xtreamcodes/iptv_xtream_codes/config"
    try: return json.loads(''.join(chr(c^ord(k)) for c,k in zip(base64.b64decode(open(rConfigPath, 'rb').read()), cycle('5709650b0d7806074842c6de575025b1'))))
    except: return None

def makeRuntimeDirs():
    # Empty runtime dirs are NOT stored in the release ZIP, so recreate them here.
    # Missing these causes: tmpfs mount failures (streams/tmp), nginx/nginx_rtmp
    # log-open failures (logs/), and php-fpm "failed to open error_log" (php/var/log).
    rBase = "/home/xtreamcodes/iptv_xtream_codes"
    rDirs = [
        rBase + "/streams",        # tmpfs mount point (live segments)
        rBase + "/tmp",            # tmpfs mount point (nginx client_temp etc.)
        rBase + "/logs",           # nginx/rtmp/panel logs
        rBase + "/tv_archive",     # catchup
        rBase + "/php/var/log",    # php-fpm error_log
        rBase + "/php/var/run",    # php-fpm pid/sockets
        rBase + "/php/var/sessions",  # PHP session.save_path (admin login sessions)
        rBase + "/created_channels",  # CREATED_CHANNELS
        rBase + "/movies",         # MOVIES_PATH
        rBase + "/delay",          # DELAY_STREAM
        rBase + "/adtools/backups",
        rBase + "/adtools/balancer",  # start_services.sh clears *.json here
        rBase + "/admin/icons",    # admin/resize.php writes its resized-icon cache here (REDSS ships it)
        rBase + "/nginx_rtmp/client_body_temp",
        rBase + "/nginx_rtmp/fastcgi_temp",
        rBase + "/nginx_rtmp/proxy_temp",
        rBase + "/nginx_rtmp/scgi_temp",
        rBase + "/nginx_rtmp/uwsgi_temp",
    ]
    for d in rDirs:
        os.makedirs(d, exist_ok=True)
    # Pre-create the log files start_services.sh truncates, so the echo> redirects
    # and nginx log opens succeed on a first run.
    for f in ["error.log", "rtmp_error.log", "rtmp_access.log", "access.log", "php-fpm.log"]:
        rPath = rBase + "/logs/" + f
        try: open(rPath, "a").close()
        except OSError: pass
    try: open(rBase + "/php/var/log/php-fpm.log", "a").close()
    except OSError: pass
    rApplied.append("runtime directories")

def writeSudoers():
    # OPT-IN ONLY (XC_SUDO_NGINX_RELOAD=Y). Neither BASE nor REDSS grants this. It would let the
    # xtreamcodes user run "nginx -s reload" as root, but that user owns (and can overwrite) the
    # nginx binaries in the panel tree, so the grant is effectively root for anything that
    # compromises a panel worker. The default sudoers entries (iptables, chattr) are written
    # by configure() exactly as in the earlier installers.
    if os.environ.get("XC_SUDO_NGINX_RELOAD", "N").strip().upper() != "Y":
        return False
    rBase = "/home/xtreamcodes/iptv_xtream_codes"
    rLine = "xtreamcodes ALL=(root) NOPASSWD: %s/nginx/sbin/nginx -s reload, %s/nginx_rtmp/sbin/nginx_rtmp -s reload\n" % (rBase, rBase)
    import tempfile
    rFd, rTmp = tempfile.mkstemp(prefix="xc_sudoers_")
    try:
        os.makedirs("/etc/sudoers.d", exist_ok=True)
        with os.fdopen(rFd, "w") as rFile: rFile.write(rLine)
        os.chmod(rTmp, 0o440)
        if os.system("visudo -cf %s > /dev/null 2>&1" % rTmp) != 0:
            printc("sudoers drop-in failed validation, left untouched", col.BRIGHT_RED)
            os.remove(rTmp)
            return False
        shutil.move(rTmp, "/etc/sudoers.d/xtreamcodes-nginx")
        os.chmod("/etc/sudoers.d/xtreamcodes-nginx", 0o440)
        os.system("chown root:root /etc/sudoers.d/xtreamcodes-nginx > /dev/null")
        rApplied.append("sudoers nginx reload (opt-in)")
        return True
    except OSError as e:
        printc("sudoers drop-in failed: %s" % e.strerror, col.BRIGHT_RED)
        return False
def configure():
    printc("Configuring System")
    # Must run BEFORE `mount -a` (mount points must exist) and BEFORE start().
    makeRuntimeDirs()
    # HTMLPurifier caches built definitions as DefinitionCache/Serializer/*/4.12.0,<hash>,1.ser.
    # Caches written by the old decoded library would be reused by the official build (same
    # file name), so clear them on every install. ConfigSchema/schema.ser is NOT a cache; keep it.
    os.system("find /home/xtreamcodes/iptv_xtream_codes/admin/standalone/HTMLPurifier/DefinitionCache/Serializer -type f -name '*.ser' -delete 2>/dev/null")
    if not "/home/xtreamcodes/iptv_xtream_codes/" in open("/etc/fstab").read():
        rFile = open("/etc/fstab", "a")
        rFile.write("tmpfs /home/xtreamcodes/iptv_xtream_codes/streams tmpfs defaults,noatime,nosuid,nodev,noexec,mode=1777,size=90% 0 0\ntmpfs /home/xtreamcodes/iptv_xtream_codes/tmp tmpfs defaults,noatime,nosuid,nodev,noexec,mode=1777,size=2G 0 0")
        rFile.close()
    if not "xtreamcodes" in open("/etc/sudoers").read():
        os.system('echo "xtreamcodes ALL = (root) NOPASSWD: /sbin/iptables, /usr/bin/chattr" >> /etc/sudoers')
    writeSudoers()  # no-op unless XC_SUDO_NGINX_RELOAD=Y
    if not os.path.exists("/etc/init.d/xtreamcodes"):
        rFile = open("/etc/init.d/xtreamcodes", "w")
        rFile.write("#! /bin/bash\n/home/xtreamcodes/iptv_xtream_codes/start_services.sh")
        rFile.close()
        os.system("chmod +x /etc/init.d/xtreamcodes > /dev/null")
        os.system("systemctl daemon-reload > /dev/null")
    try: os.remove("/usr/bin/ffmpeg")
    except: pass
    if not os.path.exists("/home/xtreamcodes/iptv_xtream_codes/tv_archive"): os.mkdir("/home/xtreamcodes/iptv_xtream_codes/tv_archive/")
    # Symlink the bundled (2023) ffmpeg kept in this build's bin/ directory.
    os.system("ln -s /home/xtreamcodes/iptv_xtream_codes/bin/ffmpeg /usr/bin/")
    # GeoLite2.mmdb already ships in the release ZIP; only fetch if missing.
    if not os.path.exists("/home/xtreamcodes/iptv_xtream_codes/GeoLite2.mmdb"):
        os.system("curl -L -s -o /home/xtreamcodes/iptv_xtream_codes/GeoLite2.mmdb %s" % rGeoLiteURL)
    if not os.path.exists("/home/xtreamcodes/iptv_xtream_codes/crons/pid_monitor.php"):
        os.system("curl -L -s -o /home/xtreamcodes/iptv_xtream_codes/crons/pid_monitor.php %s" % rPidMonitorURL)
    os.system("chown xtreamcodes:xtreamcodes -R /home/xtreamcodes > /dev/null")
    os.system("chmod -R 0777 /home/xtreamcodes > /dev/null")
    # make sure every binary/script the stack executes keeps its exec bit
    rBase = "/home/xtreamcodes/iptv_xtream_codes"
    for rExec in ["start_services.sh", "kill_pids", "permissions.sh", "check_geolite.sh", "bin/ffmpeg", "bin/ffprobe", "bin/youtube", "nginx/sbin/nginx", "nginx_rtmp/sbin/nginx_rtmp", "php/bin/php", "php/sbin/php-fpm"]:
        os.system("chmod +x %s/%s > /dev/null 2>&1" % (rBase, rExec))
    os.system("chattr -ai /home/xtreamcodes/iptv_xtream_codes/GeoLite2.mmdb > /dev/null")
    os.system("sudo chmod 0777 /home/xtreamcodes/iptv_xtream_codes/GeoLite2.mmdb > /dev/null")
    os.system("sed -i 's|chown -R xtreamcodes:xtreamcodes /home/xtreamcodes|chown -R xtreamcodes:xtreamcodes /home/xtreamcodes 2>/dev/null|g' /home/xtreamcodes/iptv_xtream_codes/start_services.sh")
    os.system("chmod +x /home/xtreamcodes/iptv_xtream_codes/start_services.sh > /dev/null")
    os.system("mount -a")
    os.system("chmod 0400 /home/xtreamcodes/iptv_xtream_codes/config > /dev/null")
    # Robust index.php rewrite: this build's wwwdir/index.php already redirects to
    # google.com, so the legacy "Xtream Codes Reborn" echo may be absent. Only run
    # the sed if that exact string is present, otherwise do nothing (no-op).
    rIndexPath = "/home/xtreamcodes/iptv_xtream_codes/wwwdir/index.php"
    try:
        rIndexData = open(rIndexPath).read()
    except OSError:
        rIndexData = ""
    if 'echo "Xtream Codes Reborn";' in rIndexData:
        os.system("sed -i 's|echo \"Xtream Codes Reborn\";|header(\"Location: https://www.google.com/\");|g' %s" % rIndexPath)
    if not "api.xtream-codes.com" in open("/etc/hosts").read(): os.system('echo "127.0.0.1    api.xtream-codes.com" >> /etc/hosts')
    if not "downloads.xtream-codes.com" in open("/etc/hosts").read(): os.system('echo "127.0.0.1    downloads.xtream-codes.com" >> /etc/hosts')
    # leading space: plain "xtream-codes.com" also matches the api./downloads. lines written above
    if not " xtream-codes.com" in open("/etc/hosts").read(): os.system('echo "127.0.0.1    xtream-codes.com" >> /etc/hosts')
    rApplied.append("hosts entries")
    if not "@reboot root /home/xtreamcodes/iptv_xtream_codes/start_services.sh" in open("/etc/crontab").read(): os.system('echo "@reboot root /home/xtreamcodes/iptv_xtream_codes/start_services.sh" >> /etc/crontab')
    # Daily GeoLite2 check (safety net in case the panel's own per-minute crontab is not
    # built yet). The updater throttles itself, so extra runs never re-download early.
    rCrontab = open("/etc/crontab").read()
    if "0 4 * * 0 xtreamcodes" in rCrontab and "geolite_update.php" in rCrontab:
        os.system("sed -i '\\|geolite_update.php|d' /etc/crontab")
        rCrontab = open("/etc/crontab").read()
    if not "geolite_update.php" in rCrontab: os.system('echo "0 4 * * * xtreamcodes /home/xtreamcodes/iptv_xtream_codes/php/bin/php /home/xtreamcodes/iptv_xtream_codes/crons/geolite_update.php > /dev/null 2>&1" >> /etc/crontab')
    # Rebuild the playlist/stream cache every minute. start_services.sh only runs setup_cache.php
    # ONCE at boot; without this recurring job, streams/bouquets added through the admin never
    # appear in get.php / the m3u until the next full restart (the tmp cache stays frozen).
    # This is the stock cache-refresh cadence; setup_cache.php is cheap and idempotent (it only
    # rewrites a cache file when its md5 changed).
    if not "setup_cache.php" in rCrontab: os.system('echo "* * * * * xtreamcodes /home/xtreamcodes/iptv_xtream_codes/php/bin/php /home/xtreamcodes/iptv_xtream_codes/crons/setup_cache.php > /dev/null 2>&1" >> /etc/crontab')

def updateGeoLite():
    # The shipped GeoLite2.mmdb is old; fetch the current one from MaxMind in the
    # background so the install does not wait on the download.
    printc("Updating GeoLite2 (background)")
    # run as the service user so log, state file and lock end up owned by xtreamcodes
    os.system("sudo -u xtreamcodes /home/xtreamcodes/iptv_xtream_codes/php/bin/php /home/xtreamcodes/iptv_xtream_codes/crons/geolite_update.php force > /dev/null 2>&1 &")
    rApplied.append("GeoLite2 update started")

def start(first=True):
    if first: printc("Starting GTB mods")
    else: printc("Restarting GTB mods")
    os.system("/home/xtreamcodes/iptv_xtream_codes/start_services.sh > /dev/null")

def nginxPreflight():
    # nginx -t as root before starting. Returns (returncode, output); a negative code is a crash by signal.
    try:
        rRun = subprocess.run([rBaseDir + "/nginx/sbin/nginx", "-t"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    except OSError as e:
        return 127, str(e)
    return rRun.returncode, rRun.stdout

def procRunning(rName):
    try: return subprocess.run(["pgrep", "-x", rName], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    except OSError: return False

def httpCode(rPort):
    try:
        rOut = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "5", "http://127.0.0.1:%d/" % rPort], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, universal_newlines=True).stdout.strip()
    except OSError: return "000"
    return rOut or "000"

def healthProblems(rWait=30):
    # Waits up to rWait seconds for nginx, nginx_rtmp, php-fpm and the :8880 / :8080 ports; returns what is still wrong.
    rProblems = []
    for rTry in range(max(1, rWait // 3)):
        rProblems = [rName + " is not running" for rName in ["nginx", "nginx_rtmp", "php-fpm"] if not procRunning(rName)]
        if not rProblems:
            rProblems = ["port %d does not answer" % rPort for rPort in [8880, 8080] if httpCode(rPort) == "000"]
        if not rProblems: break
        time.sleep(3)
    return rProblems

def nginxCrashHelp():
    printc("nginx crashed at start. Most likely cause: the name-service cache (nscd) is not running or the xtreamcodes user lookup failed.", col.BRIGHT_RED)
    printc("Check: systemctl status nscd; getent passwd xtreamcodes", col.BRIGHT_RED)

def startAndCheck():
    # Runs start() (unchanged) and verifies the stack really came up. Returns True when healthy.
    rCode, rOut = nginxPreflight()
    if rCode != 0:
        printc("nginx -t failed (exit %d)" % rCode, col.BRIGHT_RED)
        for rLine in rOut.strip().splitlines()[-6:]: print("    " + rLine)
        if rCode < 0 or rCode == 139: nginxCrashHelp()
    start()
    rProblems = healthProblems()
    if any(p.startswith("nginx") for p in rProblems):
        nginxCrashHelp()
        if pkgInstalled("nscd") and subprocess.run(["systemctl", "is-active", "--quiet", "nscd"]).returncode != 0:
            printc("nscd is installed but not running: restarting it and starting the panel once more", col.BRIGHT_YELLOW)
            os.system("systemctl restart nscd > /dev/null 2>&1")
            os.system("nscd -i passwd > /dev/null 2>&1")
            start(False)
            rProblems = healthProblems()
    if rProblems:
        for rProblem in rProblems: printc("Health check: " + rProblem, col.BRIGHT_RED)
        rErrors.append("health check: " + "; ".join(rProblems))
        return False
    rApplied.append("health check (nginx, php-fpm, :8880, :8080)")
    return True

def insertNginxBlock(rPath, rGuard, rBlock):
    # Insert rBlock before the closing brace of http { ... } unless rGuard is already present.
    rPrevData = open(rPath, "r").read()
    if rGuard in rPrevData: return False
    if not os.path.exists(f"{rPath}.xc"): shutil.copy(rPath, f"{rPath}.xc")
    http_start_index = rPrevData.find("http {")
    if http_start_index == -1: return False
    http_end_index = rPrevData.rfind("}", http_start_index)
    rData = rPrevData[:http_end_index] + rBlock + "\n}" + rPrevData[http_end_index+1:]
    with open(rPath, "w") as rFile:
        rFile.write(rData)
    return True

def modifyNginx(rAdmin=True):
    # rAdmin=True: MAIN (admin :8880 + ISP :8805; both already shipped in nginx.conf). rAdmin=False: LB (ISP :8805 only).
    printc("Modifying Nginx")
    rPath = "/home/xtreamcodes/iptv_xtream_codes/nginx/conf/nginx.conf"

    if rAdmin:
        new_server_block = """
    server {
        listen 8880;
        index index.php index.html index.htm;
        root /home/xtreamcodes/iptv_xtream_codes/admin/;

        location ~ \\.php$ {
            limit_req zone=one burst=8;
            try_files $uri =404;
            fastcgi_index index.php;
            fastcgi_pass php;
            include fastcgi_params;
            fastcgi_buffering on;
            fastcgi_buffers 96 32k;
            fastcgi_buffer_size 32k;
            fastcgi_max_temp_file_size 0;
            fastcgi_keep_conn on;
            fastcgi_param SCRIPT_FILENAME $document_root$fastcgi_script_name;
            fastcgi_param SCRIPT_NAME $fastcgi_script_name;
        }
    }
"""
        insertNginxBlock(rPath, "listen 8880;", new_server_block)

    # ISP lookup endpoint: wwwdir/includes/streaming.php calls http://api.xtream-codes.com:8805/api.php
    # (api.xtream-codes.com is mapped to 127.0.0.1 in /etc/hosts), so it must listen locally.
    isp_server_block = """
    #ISP CONFIGURATION
    server {
        listen 8805;
        root /home/xtreamcodes/iptv_xtream_codes/isp/;

        location / {
            allow 127.0.0.1;
            deny all;
        }

        location ~ \\.php$ {
            allow 127.0.0.1;
            deny all;
            limit_req zone=one burst=8;
            try_files $uri =404;
            fastcgi_index index.php;
            fastcgi_pass php;
            include fastcgi_params;
            fastcgi_buffering on;
            fastcgi_buffers 96 32k;
            fastcgi_buffer_size 32k;
            fastcgi_max_temp_file_size 0;
            fastcgi_keep_conn on;
            fastcgi_param SCRIPT_FILENAME $document_root$fastcgi_script_name;
            fastcgi_param SCRIPT_NAME $fastcgi_script_name;
        }
    }
"""
    if insertNginxBlock(rPath, "listen 8805;", isp_server_block) or "listen 8805;" in open(rPath).read():
        rApplied.append("nginx ISP :8805 block")

def ensureCloudCert(rConf="/home/xtreamcodes/iptv_xtream_codes/nginx/conf"):
    # nginx.conf references cloud_ssl_cer.cer / cloud_ssl_key.key (relative to nginx/conf).
    # nginx will not start without them, so create a self-signed placeholder if BOTH are missing.
    # Existing files are never overwritten. Returns "generated", "fallback", "present", "partial" or "failed".
    rCer = os.path.join(rConf, "cloud_ssl_cer.cer")
    rKey = os.path.join(rConf, "cloud_ssl_key.key")
    rHasCer, rHasKey = os.path.exists(rCer), os.path.exists(rKey)
    if rHasCer and rHasKey: return "present"
    if rHasCer or rHasKey:
        printc("Only one of cloud_ssl_cer.cer / cloud_ssl_key.key exists - NOT overwriting. nginx will not start until both are present!", col.BRIGHT_RED)
        return "partial"
    rResult = "failed"
    if shutil.which("openssl"):
        rRet = subprocess.call(["openssl", "req", "-x509", "-nodes", "-newkey", "rsa:2048", "-days", "3650", "-subj", "/CN=localhost", "-keyout", rKey, "-out", rCer], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if rRet == 0 and os.path.exists(rCer) and os.path.exists(rKey): rResult = "generated"
    if rResult != "generated":
        for rFile in (rCer, rKey):
            if os.path.exists(rFile): os.remove(rFile)
        rSrcCer, rSrcKey = os.path.join(rConf, "server.crt"), os.path.join(rConf, "server.key")
        if os.path.exists(rSrcCer) and os.path.exists(rSrcKey):
            shutil.copy(rSrcCer, rCer)
            shutil.copy(rSrcKey, rKey)
            rResult = "fallback"
            printc("openssl failed/missing: copied shipped server.crt/server.key (PUBLIC key, replace ASAP)", col.BRIGHT_RED)
        else:
            printc("Could not create placeholder certificate!", col.BRIGHT_RED)
            return "failed"
    os.chmod(rKey, 0o600)
    try:
        shutil.chown(rCer, "xtreamcodes", "xtreamcodes")
        shutil.chown(rKey, "xtreamcodes", "xtreamcodes")
    except (LookupError, PermissionError, OSError): pass
    return rResult

def installLB():
    # LB mode reuses the standalone install-lb script (readable bash, no opaque
    # binary) instead of a separate code path here, so the one-liner install
    # and this menu option can never drift apart. install-lb does its own
    # package/user/systemd/cron/payload steps and prints the config.py link
    # command at the end; see install-lb for the full step list.
    printc("Downloading install-lb")
    rScriptPath = "/tmp/install-lb"
    try:
        subprocess.run(['curl', '-L', '-s', '-o', rScriptPath, rInstallLBURL], check=True)
    except subprocess.CalledProcessError:
        printc("Failed to download install-lb!", col.BRIGHT_RED)
        return False
    if not os.path.exists(rScriptPath) or os.path.getsize(rScriptPath) == 0:
        printc("Failed to download install-lb!", col.BRIGHT_RED)
        return False
    os.chmod(rScriptPath, 0o755)
    printc("Running install-lb")
    rRet = subprocess.run(["bash", rScriptPath])
    if rRet.returncode != 0:
        printc("install-lb exited with an error.", col.BRIGHT_RED)
        return False
    return True


def offerLinkLB():
    # Prints the exact config.py link command, and optionally runs it for the
    # user if they want to enter the details now instead of doing it by hand.
    rCmd = "/home/xtreamcodes/iptv_xtream_codes/pytools/config.py --id <server-id> --host <main-IP> --port <DB port> --password <password> encrypt"
    printc("Link this LB to the main server with:", col.BRIGHT_YELLOW)
    print("  %s" % rCmd)
    print(" ")
    if input("  Run it now interactively? [y/N]: ").strip().upper() != "Y":
        return
    rServerID = input("  Server ID: ").strip()
    rHost = input("  Main Server IP Address: ").strip()
    rPort = input("  DB Port [7999]: ").strip() or "7999"
    rPassword = input("  MySQL Password: ").strip()
    if not (rServerID and rHost and rPassword):
        printc("Missing details, skipped.", col.BRIGHT_RED)
        return
    subprocess.run([
        "/home/xtreamcodes/iptv_xtream_codes/pytools/config.py",
        "--id", rServerID, "--host", rHost, "--port", rPort,
        "--password", rPassword, "encrypt",
    ])


CERT_REMINDER = [
    "Temporary self-signed SSL certificate created.",
    "Replace with your Cloudflare Origin certificate:",
    "/home/xtreamcodes/iptv_xtream_codes/nginx/conf/cloud_ssl_cer.cer",
    "/home/xtreamcodes/iptv_xtream_codes/nginx/conf/cloud_ssl_key.key",
    "then run start_services.sh to restart.",
    "Cloudflare SSL mode Full works with the placeholder;",
    "Full (strict) needs the real certificate.",
]

if __name__ == "__main__":
    try: rVersion = os.popen('lsb_release -sr').read().strip()
    except: rVersion = None
    if not rVersion in rVersions:
        printc("This installer supports Ubuntu 24.04 ONLY.", col.BRIGHT_RED)
        sys.exit(1)
    printc("GTB mods Installer - Ubuntu %s" % rVersion, col.GREEN, 2)
    print(" ")
    rType = input("  Installation Type [MAIN, LB]: ")
    print(" ")
    if rType.upper() == "LB":
        # LB mode: delegates everything to the standalone install-lb script
        # (see installLB()). It does not touch MAIN's prepare()/install()/
        # mysql()/configure() flow below at all.
        printc("Start LB installation? Y/N", col.BRIGHT_YELLOW)
        if input("  ").upper() == "Y":
            print(" ")
            if not installLB(): sys.exit(1)
            print(" ")
            offerLinkLB()
        else:
            printc("Installation cancelled", col.BRIGHT_RED)
    elif rType.upper() == "MAIN":
        rHost = "127.0.0.1"
        rPassword = generate()
        rServerID = 1
        rUsername = "user_iptvpro"
        rDatabase = "xtream_iptvpro"
        rPort = 7999
        if len(rHost) > 0 and len(rPassword) > 0 and rServerID > -1:
            printc("Start installation? Y/N", col.BRIGHT_YELLOW)
            if input("  ").upper() == "Y":
                print(" ")
                if not prepare(rType.upper()): sys.exit(1)
                if not install(rType.upper()): sys.exit(1)
                if not mysql(rUsername, rPassword): sys.exit(1)
                encrypt(rHost, rUsername, rPassword, rDatabase, rServerID, rPort)
                configure()
                modifyNginx(True)
                rCert = ensureCloudCert()
                if rCert in ("generated", "fallback"):
                    for rLine in CERT_REMINDER: printc(rLine, col.BRIGHT_YELLOW)
                finalize()
                startAndCheck()
                updateGeoLite()
                printc("Applied: " + ", ".join(rApplied), col.BRIGHT_GREEN)
                if rErrors:
                    printc("Installation finished with errors", col.BRIGHT_RED, 2)
                    for rErr in rErrors: printc(rErr, col.BRIGHT_RED)
                    printc("Next: systemctl status nscd; getent passwd xtreamcodes; ldd php/bin/php; log %s" % rAptLog, col.BRIGHT_RED)
                    printc("Fix the above, then run /home/xtreamcodes/iptv_xtream_codes/start_services.sh", col.BRIGHT_RED)
                else:
                    printc("Installation completed!", col.GREEN, 2)
                printc("Please store your MySQL password: %s" % rPassword, col.BRIGHT_YELLOW)
                printc("Admin UI Wan IP: http://%s:8880 (https on 2053)" % getIP(), col.BRIGHT_YELLOW)
                printc("Admin UI default login is admin/admin", col.BRIGHT_YELLOW)
                printc("Credentials saved to /root/credentials.txt", col.BRIGHT_YELLOW)
                rFile = open("/root/credentials.txt", "w")
                rFile.write("MySQL password: %s\n" % rPassword)
                rFile.write("Admin UI Wan IP: http://%s:8880 (https on 2053)\n" % getIP())
                rFile.write("Admin UI default login is admin/admin\n")
                if rCert in ("generated", "fallback"):
                    rFile.write("\nNOTE: " + " ".join(CERT_REMINDER) + "\n")
                rFile.close()
                if rErrors: sys.exit(1)
                printc("Installation done. It is recommended to REBOOT the server now: reboot", col.BRIGHT_YELLOW)
            else: printc("Installation cancelled", col.BRIGHT_RED)
        else: printc("Invalid entries", col.BRIGHT_RED)
    else: printc("Invalid installation type", col.BRIGHT_RED)
