rm -rf install.py && wget -qO install.py https://raw.githubusercontent.com/prabhjotdunglay/xtream-ui-custom/main/install.py && sudo python3 install.py


wget -qO smoke.py https://raw.githubusercontent.com/prabhjotdunglay/xtream-ui-custom/main/smoke_test.py
python3 smoke.py --line testline:testline


Key for maxmind in /home/xtreamcodes/iptv_xtream_codes
example: 1411212:xjidi8ewopioekfjfalfklasl


run (cd /home/xtreamcodes/iptv_xtream_codes
curl -fsSL -o vod_heal.py https://raw.githubusercontent.com/prabhjotdunglay/xtream-ui-custom/0993bddb39d232138bbc31885d9d835de7b74412/vod_heal.py
md5sum vod_heal.py   # must be 219e75279afc8f7c5f98f28cb1063cb8
chown xtreamcodes: vod_heal.py)

sudo -u xtreamcodes python3 /home/xtreamcodes/iptv_xtream_codes/vod_heal.py  --apply --cleanup

