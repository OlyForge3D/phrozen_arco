#!/bin/sh
systemctl stop klipper

# KAOS disabled: killall phrozen_slave_ota
#sleep 1
# KAOS disabled: /home/mks/klipper/klippy/extras/phrozen_dev/frp-oms/phrozen_slave_ota >/dev/null 2>&1 &

sleep 1

exit
