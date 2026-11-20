#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# GTB mods LB config tool.
#
# Replaces znuff's downloaded Rust binary with a small, readable Python
# script. Same file format as BASE/install.py's encrypt()/decrypt():
# XOR with the key below, then base64, JSON fields
# host, db_user, db_pass, db_name, server_id, db_port, pconnect.
#
# Usage (matches the link command printed by install-lb / install.py LB mode):
#   config.py --id <server-id> --host <main-IP> --port <DB port> \
#             --password <password> encrypt
#   config.py decrypt
#   config.py interactive        (asks questions, same as before)
#
import argparse, base64, json, os, shutil, sys
from itertools import cycle

CONFIG_PATH = "/home/xtreamcodes/iptv_xtream_codes/config"
XOR_KEY = "5709650b0d7806074842c6de575025b1"


def _xor(data, key):
    return ''.join(chr(ord(c) ^ ord(k)) for c, k in zip(data, cycle(key)))


def encrypt(host, db_user, db_pass, db_name, server_id, db_port, path=CONFIG_PATH):
    payload = {
        "host": host,
        "db_user": db_user,
        "db_pass": db_pass,
        "db_name": db_name,
        "server_id": str(server_id),
        "db_port": str(db_port),
        "pconnect": "0",
    }
    raw = json.dumps(payload, separators=(",", ":"))
    enc = _xor(raw, XOR_KEY)
    try:
        os.remove(path)
    except OSError:
        pass
    with open(path, "wb") as f:
        f.write(base64.b64encode(enc.encode("latin1")))
    try:
        shutil.chown(path, "xtreamcodes", "xtreamcodes")
    except (LookupError, OSError):
        pass
    try:
        os.chmod(path, 0o400)
    except OSError:
        pass
    print("Updated configuration")
    print("Configuration saved successfully!")
    return payload


def decrypt(path=CONFIG_PATH):
    with open(path, "rb") as f:
        raw = base64.b64decode(f.read())
    dec = ''.join(chr(c ^ ord(k)) for c, k in zip(raw, cycle(XOR_KEY)))
    return json.loads(dec)


def interactive():
    rHost = input("Main server IP/host: ").strip()
    rUser = input("DB user [user_iptvpro]: ").strip() or "user_iptvpro"
    rPass = input("DB password: ").strip()
    rDb = input("DB name [xtream_iptvpro]: ").strip() or "xtream_iptvpro"
    rId = input("Server ID: ").strip()
    rPort = input("DB port [7999]: ").strip() or "7999"
    encrypt(rHost, rUser, rPass, rDb, rId, rPort)


def main():
    parser = argparse.ArgumentParser(description="GTB LB config tool")
    parser.add_argument("action", choices=["encrypt", "decrypt", "interactive"], nargs="?", default="interactive")
    parser.add_argument("--id", dest="server_id")
    parser.add_argument("--host")
    parser.add_argument("--port", dest="db_port", default="7999")
    parser.add_argument("--user", dest="db_user", default="user_iptvpro")
    parser.add_argument("--password", dest="db_pass")
    parser.add_argument("--db", dest="db_name", default="xtream_iptvpro")
    parser.add_argument("--create", choices=["yes", "no"], default=None)
    args = parser.parse_args()

    if args.action == "decrypt":
        if not os.path.exists(CONFIG_PATH) and args.create != "yes":
            print("No config file found.")
            sys.exit(1)
        print(json.dumps(decrypt(), indent=2))
        return

    if args.action == "interactive":
        interactive()
        return

    # encrypt
    if args.create == "yes" and not (args.host and args.db_pass and args.server_id):
        # blank placeholder config, filled in later by a real encrypt call
        encrypt("127.0.0.1", args.db_user, "", args.db_name, 0, args.db_port)
        return

    if not (args.host and args.db_pass and args.server_id):
        print("Usage: config.py --id <id> --host <host> --port <port> --password <password> encrypt")
        sys.exit(1)

    encrypt(args.host, args.db_user, args.db_pass, args.db_name, args.server_id, args.db_port)


if __name__ == "__main__":
    main()
