rm -rf install.py && wget -qO install.py https://raw.githubusercontent.com/prabhjotdunglay/xtream-ui-custom/main/install.py && sudo python3 install.py


wget -qO smoke.py https://raw.githubusercontent.com/prabhjotdunglay/xtream-ui-custom/main/smoke_test.py
python3 smoke.py --line testline:testline


Key for maxmind in /home/xtreamcodes/iptv_xtream_codes
example: 1411212:xjidi8ewopioekfjfalfklasl


Every few days:
On Main server
1.cd /tmp && wget -O series_dedupe.py "https://raw.githubusercontent.com/prabhjotdunglay/xtream-ui-custom/main/tools/series_dedupe.py?nocache=$(date +%s)"
python3 series_dedupe.py

2. python3 series_dedupe.py --apply

ON LB

3. cd /tmp && wget -O vod_heal.py "https://raw.githubusercontent.com/prabhjotdunglay/xtream-ui-custom/vod-heal/vod_heal.py?nocache=$(date +%s)"
python3 vod_heal.py --version | head -1
sudo -u xtreamcodes python3 /tmp/vod_heal.py

5. sudo -u xtreamcodes python3 /tmp/vod_heal.py --apply
6. sudo -u xtreamcodes python3 /tmp/vod_heal.py --remove-orphans
7. sudo -u xtreamcodes python3 /tmp/vod_heal.py --remove-orphans --apply




