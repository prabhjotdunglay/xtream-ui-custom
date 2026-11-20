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
#   - decoder damage in znuff's decoded PHP (see DECODER_DAMAGE_PATCHES below):
#     exact-match patches applied to the bytes that go into the zip; the build
#     fails if any patch does not match exactly once
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



# ---------------------------------------------------------------------------
# DECODER-DAMAGE PATCHES
#
# The znuff PHP in lbznuff/ was decoded by a third-party IonCube decoder that
# inverted or dropped loop conditions and float literals. lbznuff/ stays
# untouched (read-only); these exact-match patches are applied to the bytes
# that go into the zip. Each (old, new) pair must match exactly once in its
# file, otherwise the build fails. Ground truth for the correct code is the
# hand-fixed equivalent file in the main panel BASE.
# Evidence per patch: .agents/tasks/lb-heartbeat/findings.md
# ---------------------------------------------------------------------------
DECODER_DAMAGE_PATCHES = [
    # ---- crons/servers_checker.php: the heartbeat ----
    ("crons/servers_checker.php", "heartbeat loop never ran ('>= 2' after '= 0')",
     "    $Ced112d15c5a3c9e5ba92478d0228e93 = 0;\n    while ($Ced112d15c5a3c9e5ba92478d0228e93 >= 2) {\n",
     "    $Ced112d15c5a3c9e5ba92478d0228e93 = 0;\n    while ($Ced112d15c5a3c9e5ba92478d0228e93 < 2) {\n"),
    ("crons/servers_checker.php", "leave the retry loop after a successful heartbeat",
     "                $F30ccc8fd3427f97ca35bc6ba6610d01->query(\"UPDATE `streaming_servers` SET `status` = 1 WHERE `id` = '%d'\", SERVER_ID);\n            }\n",
     "                $F30ccc8fd3427f97ca35bc6ba6610d01->query(\"UPDATE `streaming_servers` SET `status` = 1 WHERE `id` = '%d'\", SERVER_ID);\n            }\n            $Ced112d15c5a3c9e5ba92478d0228e93 = 2;\n"),
    ("crons/servers_checker.php", "tx speed multiplied by 0",
     "$Beb6ceea731b15c6247663ffaf271acc = round(($c44045e903b082b586bd303b9f72055d - $e669ee4257a084768605838ae9ff6680) / 1024 * 0, 2);",
     "$Beb6ceea731b15c6247663ffaf271acc = round(($c44045e903b082b586bd303b9f72055d - $e669ee4257a084768605838ae9ff6680) / 1024 * 0.0078125, 2);"),
    ("crons/servers_checker.php", "rx speed multiplied by 0",
     "$f7a94b7d355ba31690d9f2c50eef75d8 = round(($B39775fc0fe838f1aa5deee1de412a77 - $Fb756cf40e152c410f210c4f33061ba6) / 1024 * 0, 2);",
     "$f7a94b7d355ba31690d9f2c50eef75d8 = round(($B39775fc0fe838f1aa5deee1de412a77 - $Fb756cf40e152c410f210c4f33061ba6) / 1024 * 0.0078125, 2);"),
    ("crons/servers_checker.php", "do not wget the defunct xtream-codes GeoLite2 URL (wget -O truncates our GeoLite2.mmdb)",
     "            passthru(\"wget --no-check-certificate --user-agent \\\"Mozilla/5.0 (Windows NT 10.0; WOW64; rv:46.0) Gecko/20100101 Firefox/46.0\\\" --timeout=40 \\\"http://downloads.xtream-codes.com/v2/GeoLite2.mmdb\\\" -O \\\"\" . GEOIP2_FILENAME . \"\\\" -q 2>/dev/null\");\n",
     "            // removed: legacy GeoLite2 download from a defunct third-party domain (wget -O truncates the shipped database)\n"),

    # ---- tools/watchdog_data.php ----
    ("tools/watchdog_data.php", "kill only our own old watchdog_data php, never EPERM, never unrelated",
     "    shell_exec(\"kill \\$(ps aux | grep watchdog_data | grep -v grep | grep -v \" . getmypid() . \" | awk '{print \\$2}')\");\n",
     "    shell_exec(\"kill \\$(pgrep -u \\$(id -u) -f '^[^ ]*php[^ ]* [^ ]*tools/[w]atchdog_data\\\\.php' | grep -vx \" . getmypid() . \") > /dev/null 2>&1\");\n"),
    ("tools/watchdog_data.php", "while (false) never looped",
     "    while (false) {\n",
     "    while (true) {\n"),
    ("tools/watchdog_data.php", "leave loop when the DB is lost, respawn once after the loop",
     "            sleep(2);\n        }\n        shell_exec(\"(sleep 1; \" . PHP_BIN . \" \" . __FILE__ . \" ) > /dev/null 2>/dev/null &\");\n    }\n",
     "            sleep(2);\n        } else {\n            break;\n        }\n    }\n    shell_exec(\"(sleep 1; \" . PHP_BIN . \" \" . __FILE__ . \" ) > /dev/null 2>/dev/null &\");\n"),

    # ---- tools/signal_receiver.php ----
    ("tools/signal_receiver.php", "kill only our own old signal_receiver php, never EPERM, never unrelated",
     "    shell_exec(\"kill \\$(ps aux | grep signal_receiver | grep -v grep | grep -v \" . getmypid() . \" | awk '{print \\$2}')\");\n",
     "    shell_exec(\"kill \\$(pgrep -u \\$(id -u) -f '^[^ ]*php[^ ]* [^ ]*tools/[s]ignal_receiver\\\\.php' | grep -vx \" . getmypid() . \") > /dev/null 2>&1\");\n"),
    ("tools/signal_receiver.php", "while (false) never looped",
     "    while (false) {\n",
     "    while (true) {\n"),
    ("tools/signal_receiver.php", "leave loop when the DB is lost, respawn once after the loop",
     "            sleep(1);\n        }\n        shell_exec(\"(sleep 1; \" . PHP_BIN . \" \" . __FILE__ . \" ) > /dev/null 2>/dev/null &\");\n    }\n",
     "            sleep(1);\n        } else {\n            break;\n        }\n    }\n    shell_exec(\"(sleep 1; \" . PHP_BIN . \" \" . __FILE__ . \" ) > /dev/null 2>/dev/null &\");\n"),

    # ---- tools/pipe_reader.php ----
    ("tools/pipe_reader.php", "kill only our own old pipe_reader php, never EPERM, never unrelated",
     "    shell_exec(\"kill \\$(ps aux | grep pipe_reader | grep -v grep | grep -v \" . getmypid() . \" | awk '{print \\$2}')\");\n",
     "    shell_exec(\"kill \\$(pgrep -u \\$(id -u) -f '^[^ ]*php[^ ]* [^ ]*tools/[p]ipe_reader\\\\.php' | grep -vx \" . getmypid() . \") > /dev/null 2>&1\");\n"),
    ("tools/pipe_reader.php", "while (false) never looped",
     "    while (false) {\n",
     "    while (true) {\n"),
    ("tools/pipe_reader.php", "empty '!== false' block: DB lost must leave the loop",
     "implode(\",\", $De933f63e54551ecc5d95bc6360ca4f3) . \")\") !== false) {\n            }\n",
     "implode(\",\", $De933f63e54551ecc5d95bc6360ca4f3) . \")\") === false) {\n                break;\n            }\n"),
    ("tools/pipe_reader.php", "respawn once after the loop, not on every pass",
     "            usleep(4000);\n        }\n        shell_exec(\"(sleep 2; \" . PHP_BIN . \" \" . __FILE__ . \" ) > /dev/null 2>/dev/null &\");\n    }\n",
     "            usleep(4000);\n        }\n    }\n    shell_exec(\"(sleep 2; \" . PHP_BIN . \" \" . __FILE__ . \" ) > /dev/null 2>/dev/null &\");\n"),

    # ---- tools/stream_monitor.php ----
    ("tools/stream_monitor.php", "while (false): monitor loop never ran",
     "            while (false) {\n                if (0 >= $c56e34a2166b612653a19b0811c9865d) {\n",
     "            while (true) {\n                if (0 >= $c56e34a2166b612653a19b0811c9865d) {\n"),
    ("tools/stream_monitor.php", "inverted wait-while-alive condition",
     "while (!(f1ca094152763c79018E9F1893Ef1e48::a1ecf5d2A93474B12e622361C656b958($c56e34a2166b612653a19b0811c9865d, $b6497ba71489783c3747f19debe893a4) && file_exists($f0d5508533eaf6452b2b014beae1cc7c))) {\n",
     "while (f1ca094152763c79018E9F1893Ef1e48::a1ecf5d2A93474B12e622361C656b958($c56e34a2166b612653a19b0811c9865d, $b6497ba71489783c3747f19debe893a4) && file_exists($f0d5508533eaf6452b2b014beae1cc7c)) {\n"),
    ("tools/stream_monitor.php", "inverted restart-while-dead condition",
     "                while (F1CA094152763c79018e9f1893Ef1E48::A1eCF5d2a93474b12e622361C656b958($c56e34a2166b612653a19b0811c9865d, $b6497ba71489783c3747f19debe893a4)) {\n                    echo \"Restarting...\\n\";\n",
     "                while (!F1CA094152763c79018e9f1893Ef1E48::A1eCF5d2a93474b12e622361C656b958($c56e34a2166b612653a19b0811c9865d, $b6497ba71489783c3747f19debe893a4)) {\n                    echo \"Restarting...\\n\";\n"),
    ("tools/stream_monitor.php", "inverted playlist-wait for loop",
     "for ($Df462682e370952f75b92da6e62a7293 = 0; !(f1Ca094152763c79018E9f1893EF1e48::a1eCf5D2a93474B12E622361c656b958($c56e34a2166b612653a19b0811c9865d, $b6497ba71489783c3747f19debe893a4) && !file_exists($f0d5508533eaf6452b2b014beae1cc7c) && $Df462682e370952f75b92da6e62a7293 <= e2D73953A5089B9c7983838F61F23aCf::$SegmentsSettings[\"seg_time\"] * 3); $Df462682e370952f75b92da6e62a7293++) {",
     "for ($Df462682e370952f75b92da6e62a7293 = 0; f1Ca094152763c79018E9f1893EF1e48::a1eCf5D2a93474B12E622361c656b958($c56e34a2166b612653a19b0811c9865d, $b6497ba71489783c3747f19debe893a4) && !file_exists($f0d5508533eaf6452b2b014beae1cc7c) && $Df462682e370952f75b92da6e62a7293 <= e2D73953A5089B9c7983838F61F23aCf::$SegmentsSettings[\"seg_time\"] * 3; $Df462682e370952f75b92da6e62a7293++) {"),
    ("tools/stream_monitor.php", "playlist-wait timeout test could never match",
     "if ($Df462682e370952f75b92da6e62a7293 != E2d73953A5089B9c7983838f61F23ACf::$SegmentsSettings[\"seg_time\"] * 3) {",
     "if ($Df462682e370952f75b92da6e62a7293 <= E2d73953A5089B9c7983838f61F23ACf::$SegmentsSettings[\"seg_time\"] * 3) {"),
    ("tools/stream_monitor.php", "avoid a 100% CPU spin when ffmpeg is alive but the playlist is missing",
     "                    } else {\n                        exit;\n                    }\n                }\n            }\n        } else {\n",
     "                    } else {\n                        exit;\n                    }\n                }\n                sleep(1);\n            }\n        } else {\n"),

    # ---- tools/delay.php ----
    ("tools/delay.php", "inverted delay-wait condition",
     "while (!(F1Ca094152763c79018e9F1893EF1E48::A1ECF5d2a93474B12e622361C656b958($c56e34a2166b612653a19b0811c9865d, $b6497ba71489783c3747f19debe893a4) && file_exists($C8d3c577e00f73ecaaed3c2da9396679))) {\n",
     "while (F1Ca094152763c79018e9F1893EF1E48::A1ECF5d2a93474B12e622361C656b958($c56e34a2166b612653a19b0811c9865d, $b6497ba71489783c3747f19debe893a4) && file_exists($C8d3c577e00f73ecaaed3c2da9396679)) {\n"),
    ("tools/delay.php", "inverted segment-copy for loop",
     "for ($Ced112d15c5a3c9e5ba92478d0228e93 = 0; !($Ced112d15c5a3c9e5ba92478d0228e93 < $E886613d3e0b0e8d281253732ef24727 && $Ced112d15c5a3c9e5ba92478d0228e93 < count($Ac4a2d0eeb4ebb52f33538ad6cdc23c9)); $Ced112d15c5a3c9e5ba92478d0228e93++) {",
     "for ($Ced112d15c5a3c9e5ba92478d0228e93 = 0; $Ced112d15c5a3c9e5ba92478d0228e93 < $E886613d3e0b0e8d281253732ef24727 && $Ced112d15c5a3c9e5ba92478d0228e93 < count($Ac4a2d0eeb4ebb52f33538ad6cdc23c9); $Ced112d15c5a3c9e5ba92478d0228e93++) {"),
    ("tools/delay.php", "inverted feof() read loop",
     "        while (feof($b4ad7225f6375fe5d757d3c7147fb034)) {\n",
     "        while (!feof($b4ad7225f6375fe5d757d3c7147fb034)) {\n"),
    ("tools/delay.php", "fclose inside the read loop; missing 'limit reached -> break'",
     "                }\n            }\n            fclose($b4ad7225f6375fe5d757d3c7147fb034);\n        }\n    }\n    return $Ae3016c45dd59a9b881c39a8dfeb6f6f;\n",
     "                }\n            } else {\n                break;\n            }\n        }\n        fclose($b4ad7225f6375fe5d757d3c7147fb034);\n    }\n    return $Ae3016c45dd59a9b881c39a8dfeb6f6f;\n"),

    # ---- tools/archive.php ----
    ("tools/archive.php", "inverted feof() read loop",
     "                while (feof($b4ad7225f6375fe5d757d3c7147fb034)) {\n",
     "                while (!feof($b4ad7225f6375fe5d757d3c7147fb034)) {\n"),
    ("tools/archive.php", "inverted for condition: old archive files were never deleted",
     "for ($Ced112d15c5a3c9e5ba92478d0228e93 = 0; $Ced112d15c5a3c9e5ba92478d0228e93 >= $d28ce8f5992f60104d778562650285fc; $Ced112d15c5a3c9e5ba92478d0228e93++) {",
     "for ($Ced112d15c5a3c9e5ba92478d0228e93 = 0; $Ced112d15c5a3c9e5ba92478d0228e93 < $d28ce8f5992f60104d778562650285fc; $Ced112d15c5a3c9e5ba92478d0228e93++) {"),

    # ---- crons ----
    ("crons/offline_cons.php", "inverted feof() read loop",
     "        while (feof($b4ad7225f6375fe5d757d3c7147fb034)) {\n",
     "        while (!feof($b4ad7225f6375fe5d757d3c7147fb034)) {\n"),
    ("crons/offline_cons.php", "fclose inside the read loop",
     "            }\n            fclose($b4ad7225f6375fe5d757d3c7147fb034);\n        }\n    }\n    return $e86143ae714b5db9373cfb584f8aaf70;\n",
     "            }\n        }\n        fclose($b4ad7225f6375fe5d757d3c7147fb034);\n    }\n    return $e86143ae714b5db9373cfb584f8aaf70;\n"),
    ("crons/tmp_del.php", "readdir loop condition inverted (=== instead of !==)",
     "while (false === $e51d2d22edaf82bf4df6dd3cd1f2e264 = readdir($A7cd68109a3d420b829e6d9425875c6d)) {",
     "while (false !== ($e51d2d22edaf82bf4df6dd3cd1f2e264 = readdir($A7cd68109a3d420b829e6d9425875c6d))) {"),
    ("crons/stream_errors.php", "readdir loop condition inverted (=== instead of !==)",
     "while (false === $e51d2d22edaf82bf4df6dd3cd1f2e264 = readdir($A7cd68109a3d420b829e6d9425875c6d)) {",
     "while (false !== ($e51d2d22edaf82bf4df6dd3cd1f2e264 = readdir($A7cd68109a3d420b829e6d9425875c6d))) {"),
    ("crons/users_checker.php", "bitrate factor 0.92 rendered as 0",
     "intval($Ead3b4aba4702e941b0b5878716a9112[\"bitrate\"] / 8 * 0);",
     "intval($Ead3b4aba4702e941b0b5878716a9112[\"bitrate\"] / 8 * 0.92);"),
    ("crons/vod_checker.php", "bitrate factor 0.008 rendered as 0",
     "[$Fa2325a1b301ca7c383cb69087c42d91[\"server_id\"]] * 0 / $f3db7858a998b217cdc28e738fd2182d);",
     "[$Fa2325a1b301ca7c383cb69087c42d91[\"server_id\"]] * 0.008 / $f3db7858a998b217cdc28e738fd2182d);"),
    # ---- php/etc/streamer.conf: parity with BASE and REDSS (LB copy too) ----
    ("php/etc/streamer.conf", "add process.dumpable = yes (BASE/REDSS have it; keeps /proc/<pid>/exe readable if fpm master is ever root)",
     "pool:$pool [%{HTTP_USER_AGENT}e]\"\n\n",
     "pool:$pool [%{HTTP_USER_AGENT}e]\"\n\nprocess.dumpable = yes\n"),
]


PATCHED_FILES = set(p[0] for p in DECODER_DAMAGE_PATCHES)


def apply_patches(rel_path, data, applied):
    """Apply every patch for rel_path to data (bytes). Each must match exactly once."""
    key = rel_path.replace(os.sep, "/")
    for idx, (pfile, why, old, new) in enumerate(DECODER_DAMAGE_PATCHES):
        if pfile != key:
            continue
        o = old.encode("utf-8")
        n = data.count(o)
        if n != 1:
            raise SystemExit("PATCH FAILED: %s [%s] matched %d times (need exactly 1)" % (pfile, why, n))
        data = data.replace(o, new.encode("utf-8"))
        applied.add(idx)
    return data


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

    applied = set()
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
                if rel_file.replace(os.sep, "/") in PATCHED_FILES:
                    with open(full_path, "rb") as fh:
                        data = apply_patches(rel_file, fh.read(), applied)
                    zi = zipfile.ZipInfo.from_file(full_path, arcname)
                    zi.compress_type = zipfile.ZIP_DEFLATED
                    zf.writestr(zi, data)
                else:
                    zf.write(full_path, arcname)

        # our own config.py (flag-based), replacing znuff's Rust binary
        zi = zipfile.ZipInfo.from_file(our_config_py, os.path.join("iptv_xtream_codes", "pytools", "config.py"))
        zi.external_attr = (0o100755 << 16)
        zi.compress_type = zipfile.ZIP_DEFLATED
        with open(our_config_py, "rb") as fh:
            zf.writestr(zi, fh.read())
        # our own GeoLite2.mmdb, replacing the 0-byte placeholder
        zf.write(our_geolite, os.path.join("iptv_xtream_codes", "GeoLite2.mmdb"))

    if len(applied) != len(DECODER_DAMAGE_PATCHES):
        missing = [DECODER_DAMAGE_PATCHES[i][0] + " [" + DECODER_DAMAGE_PATCHES[i][1] + "]"
                   for i in range(len(DECODER_DAMAGE_PATCHES)) if i not in applied]
        raise SystemExit("PATCH FAILED: not applied: %s" % "; ".join(missing))
    print("applied %d decoder-damage patches to %d files" % (len(applied), len(PATCHED_FILES)))
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
