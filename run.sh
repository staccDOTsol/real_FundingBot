#!/bin/bash
#sudo killall node
#nohup node api-connectors/official-ws/delta-server/index.js &
#sudo killall mongod
#sudo nohup mongod --dbpath=/var/lib/mongodb &
sudo killall python3
sudo killall python3.7
while :
do
OUTPUT=$(ps -aux | grep -cE "python3.7 market_maker")

if (( OUTPUT > 1 )); then
    echo "python3 is running"
	sleep 30s
else
    echo "python3 is not running"
	
    nohup python3.7 mex_pos.py &
    nohup python3.7 bit_pos.py &
    nohup python3.7 der_pos.py &
    nohup python3.7 mex_ords.py &
    nohup python3.7 bit_ords.py &
    nohup python3.7 der_ords.py &
#    nohup python3.7 market_maker.py &
fi

OUTPUT=$(ps -aux | grep -cE "python3 market_maker")

if (( OUTPUT > 1 )); then
    echo "python3 is running"
        sleep 30s
else
    echo "python3 is not running"

    nohup python3.7 mex_pos.py &
    nohup python3.7 bit_pos.py &
    nohup python3.7 der_pos.py &
    nohup python3.7 mex_ords.py &
    nohup python3.7 bit_ords.py &
    nohup python3.7 der_ords.py &
 #   nohup python3.7 market_maker.py &
fi


done

