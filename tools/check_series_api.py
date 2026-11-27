#!/usr/bin/env python3
# Read-only: compares what player_api.php returns for one line with what a player app may drop.
# Usage: python3 check_series_api.py <base_url> <username> <password>
#   base_url example: https://panel.example.com:443   (no trailing slash)
# Optional: empty-series ids are read from the local database with the mysql client (read-only).
import collections, json, subprocess, sys, urllib.parse, urllib.request

def fetch(base, user, pw, action):
    q = urllib.parse.urlencode({"username": user, "password": pw, "action": action})
    req = urllib.request.Request(base.rstrip("/") + "/player_api.php?" + q, headers={"User-Agent": "series-check"})
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = r.read()
    try:
        return json.loads(raw)
    except ValueError:
        sys.exit("The server did not return JSON for %s. First 200 bytes: %r" % (action, raw[:200]))

def main():
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    base, user, pw = sys.argv[1:4]
    s = fetch(base, user, pw, "get_series")
    c = fetch(base, user, pw, "get_series_categories")
    if not isinstance(s, list) or not isinstance(c, list):
        sys.exit("Unexpected answer (wrong username/password?).")
    cats = {str(x.get("category_id")): x.get("category_name") for x in c}
    noep = set()
    try:
        out = subprocess.run(["mysql", "-N", "xtream_iptvpro", "-e",
            "SELECT r.id FROM series r WHERE NOT EXISTS (SELECT 1 FROM series_episodes e WHERE e.series_id = r.id);"],
            capture_output=True, text=True, timeout=120)
        if out.returncode == 0:
            noep = {l.strip() for l in out.stdout.splitlines() if l.strip()}
        else:
            print("(could not read empty series from mysql: %s)" % out.stderr.strip()[:120])
    except Exception as e:
        print("(mysql not available: %s)" % e)
    ids = [str(x.get("series_id")) for x in s]
    print("entries in get_series        :", len(s))
    print("distinct series_id           :", len(set(ids)))
    print("categories returned          :", len(cats))
    print("name null/empty              :", sum(1 for x in s if not (x.get("name") or "").strip()))
    print("category_id null/empty       :", sum(1 for x in s if x.get("category_id") in (None, "", 0, "0")))
    print("category not in category list:", sum(1 for x in s if str(x.get("category_id")) not in cats))
    print("cover empty                  :", sum(1 for x in s if not (x.get("cover") or "").strip()))
    print("series with no episodes      :", len(noep), " of which in the API list:", sum(1 for i in ids if i in noep))
    names = collections.Counter((x.get("name") or "").strip().lower() for x in s)
    dup = {n: k for n, k in names.items() if k > 1 and n}
    print("names used by >1 series      :", len(dup), " (extra entries:", sum(k - 1 for k in dup.values()), ")")
    percat = collections.Counter(str(x.get("category_id")) for x in s)
    print("sum of per-category counts   :", sum(percat.values()))
    print("categories with 0 series     :", sum(1 for k in cats if k not in percat))
    # per-category table: compare these numbers with what the player app shows for each category
    empty_by_cat = collections.Counter(str(x.get("category_id")) for x in s if str(x.get("series_id")) in noep)
    seen = set(); dupnames = collections.Counter()
    for x in s:
        n = (x.get("name") or "").strip().lower()
        if n in seen: dupnames[str(x.get("category_id"))] += 1
        seen.add(n)
    print()
    print("%-9s %-34s %7s %7s %9s" % ("cat_id", "category", "series", "empty", "dup_name"))
    for k, v in sorted(percat.items(), key=lambda kv: -kv[1]):
        print("%-9s %-34s %7d %7d %9d" % (k, (cats.get(k) or "?")[:34], v, empty_by_cat.get(k, 0), dupnames.get(k, 0)))

main()
