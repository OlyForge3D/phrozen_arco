#!/bin/bash
#GPIO2_C5,2*32+8*2=5=85
if [ -d /sys/class/gpio/gpio85 ]
then
        echo out > /sys/class/gpio/gpio85/direction
        echo 1 > /sys/class/gpio/gpio85/value
else
        echo 85 > /sys/class/gpio/export
        echo out > /sys/class/gpio/gpio85/direction
        echo 1 > /sys/class/gpio/gpio85/value
fi
#GPIO2_C0,2*32+8*2=80
if [ -d /sys/class/gpio/gpio80 ]
then
        echo in > /sys/class/gpio/gpio80/direction
else
        echo 80 > /sys/class/gpio/export
        echo in > /sys/class/gpio/gpio80/direction
fi



while :
do
    #lancaigang260330：读取电源键状态，防止fork进程太多；
    read level < /sys/class/gpio/gpio80/value   # shell 内置，不 fork 进程
    if [ "$level" = "1" ]
    then
        echo 1 > /sys/class/gpio/gpio85/value
        sync
        shutdown -h now
        echo "shutdown!!!"
    fi
    #lancaigang260330：添加电源键响应时间，防止电源键抖动；
    sleep 0.5   # 0.01 → 0.5，按电源键 0.5 秒响应完全够
done





