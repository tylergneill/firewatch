#!/bin/bash

read -p "This script syncs data UP to the remote server. Type 'Sure' to continue: " CONFIRMATION

if [ "$CONFIRMATION" != "Sure" ]; then
    echo "Aborting."
    exit 1
fi

LOCAL_DATA_PATH="../firewatch-data"
for suffix in "" "-stg"; do
    for appname in skrutable splitter-server vatayana panditya hansel firewatch kalpataru-grove; do
        rsync -avz -e "ssh -i ~/.ssh/id_rsa_do" --size-only --delete ${LOCAL_DATA_PATH}/${appname}${suffix}-archive/ root@146.190.74.47:/var/log/nginx/${appname}${suffix}-archive/
    done
done
