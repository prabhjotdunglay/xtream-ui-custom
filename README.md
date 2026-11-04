rm -rf install.py && wget -qO install.py https://raw.githubusercontent.com/prabhjotdunglay/xtream-ui-custom/main/install.py && sudo python3 install.py


wget -qO smoke.py https://raw.githubusercontent.com/prabhjotdunglay/xtream-ui-custom/main/smoke_test.py
python3 smoke.py --line admin:admin
