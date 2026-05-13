#!/bin/bash
#johnson250902: phrozengo

# lancaigang260325: 单例保护 - 使用 flock 文件锁确保同时只有一个实例运行
# lancaigang260325: flock -n 尝试获取非阻塞排他锁，获取失败说明已有实例，直接退出
LOCK_FILE="/tmp/PhrozenGoStart.lock"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    echo "[$(date)] PhrozenGoStart.sh already running (lock held), exiting."
    exit 0
fi

# lancaigang260325: 单例保护 - 检测phrozen-go-release是否已在运行
if pgrep -f "phrozen-go-release" > /dev/null 2>&1; then
    echo "[$(date)] phrozen-go-release already running, exiting."
    exit 0
fi

(
    mkdir /home/mks/PhrozenGo
    tar xvf /home/mks/klipper/klippy/extras/phrozen_dev/PhrozenGo.tar -C /home/mks/ >> /home/mks/PhrozenGo/phrozengo.log 2>&1
    chmod -R 755 /home/mks/PhrozenGo
    while true; do
        # Trim log to latest 100 lines
        if [ -f /home/mks/PhrozenGo/phrozengo.log ]; then
            tail -n 100 /home/mks/PhrozenGo/phrozengo.log > /home/mks/PhrozenGo/phrozengo.log.tmp \
                && mv /home/mks/PhrozenGo/phrozengo.log.tmp /home/mks/PhrozenGo/phrozengo.log
        fi

        echo "[$(date)] Starting PhrozenGo..." >> /home/mks/PhrozenGo/phrozengo.log
        /home/mks/PhrozenGo/run.sh >> /home/mks/PhrozenGo/phrozengo.log 2>&1
        EXIT_CODE=$?
        echo "[$(date)] PhrozenGo exited with code $EXIT_CODE, restarting in 5s..." >> /home/mks/PhrozenGo/phrozengo.log
        sleep 5
    done
) &

while true
do
    sleep 1
done