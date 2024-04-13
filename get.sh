#!/bin/bash

if [ -z "$HOSTUSER" ]; then
    echo "HOSTUSER not set"
    exit 1
fi

cd ~/Source/pga-betting
. venv/bin/activate

scp results.css $HOSTUSER:/var/www/html > /dev/null 2>&1

# loop forever
while true; do

    python pga-scraper-score.py redis
    
    if [ "`redis-cli exists 'pga-scaper-score:html'`" == "1" ]; then
        redis-cli get 'pga-scaper-score:html' | ssh $HOSTUSER "cat > /var/www/html/results.html"
    else
        echo "The key 'pga-scaper-score:html' does not exist. Probably an error."
        exit 1
    fi

    duration=$((RANDOM % 180 + 180))
    echo "sleep $duration"
    sleep $duration

    # after 2 am sleep for 30 minutes till 2 pm
    if [ "$(date +%H)" -ge 2 ] && [ "$(date +%H)" -lt 14 ]; then
        duration=1800
        echo "long sleep $duration"
        sleep $duration
    fi
done


