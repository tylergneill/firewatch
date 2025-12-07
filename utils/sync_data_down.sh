LOCAL_DATA_PATH="../firewatch-data"
for suffix in "" "-stg"; do
    for appname in skrutable splitter-server vatayana panditya hansel firewatch kalpataru-grove; do
        rsync -avz -e "ssh -i ~/.ssh/id_rsa_do" --size-only --delete root@146.190.74.47:/var/log/nginx/${appname}${suffix}-archive/ ${LOCAL_DATA_PATH}/${appname}${suffix}-archive/
        rsync -avz -e "ssh -i ~/.ssh/id_rsa_do" root@146.190.74.47:/var/log/nginx/${appname}${suffix}-app.access.log ${LOCAL_DATA_PATH}/${appname}${suffix}-app.access.log
    done
done