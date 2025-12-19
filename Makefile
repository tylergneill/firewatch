LOCAL_DATA_PATH = $(shell realpath $(dir $(lastword $(MAKEFILE_LIST)))../firewatch-data)
LOCAL_CACHE_PATH = $(shell realpath $(dir $(lastword $(MAKEFILE_LIST)))../firewatch-data-cache)
LOCAL_GEOIP_DB_PATH = $(shell realpath $(dir $(lastword $(MAKEFILE_LIST)))../firewatch-data-geoip-db)

# (or export LOCAL_DATA_PATH env var if different from above)

# for temporary local builds with full data
run:
	docker build . -f Dockerfile.stg -t firewatch-dev:debug
	docker run \
	  --rm \
	  -it \
	  -p 5071:5071 \
	  -v $(LOCAL_DATA_PATH):/app/static/data \
	  -v $(LOCAL_CACHE_PATH):/app/static/cache \
	  -v $(LOCAL_GEOIP_DB_PATH):/data/geoip \
	  -e GEOIP_DATABASE_PATH=/data/geoip/GeoLite2-City.mmdb \
	  --name firewatch-dev \
	  firewatch-dev:debug

# for official stg and prod builds uploaded to Docker Hub
# to use: VERSION={version} make run-official
run-official:
	docker run \
	  --rm \
	  -it \
	  -p 5070:5070 \
	  -v $(LOCAL_DATA_PATH):/app/static/data \
	  -v $(LOCAL_CACHE_PATH):/app/static/cache \
	  -v $(LOCAL_GEOIP_DB_PATH):/data/geoip \
	  -e GEOIP_DATABASE_PATH=/data/geoip/GeoLite2-City.mmdb \
	  tylergneill/firewatch-app:$(VERSION)

data-refresh-full:
	bash utils/sync_data_down.sh
	python utils/reshard_logs.py --data-dir /Users/tyler/Git/firewatch-data
	python utils/generate_traffic_analytics.py --data-dir /Users/tyler/Git/firewatch-data --db-file /Users/tyler/Git/firewatch-data-cache/traffic_analytics.db
	python utils/move_old_junk.py --data-dir /Users/tyler/Git/firewatch-data --cache-file /Users/tyler/Git/firewatch-data-cache/firewatch_cache.db
	python utils/update_cache.py --rebuild-all --data-dir /Users/tyler/Git/firewatch-data --cache-file /Users/tyler/Git/firewatch-data-cache/firewatch_cache.db
	bash utils/sync_data_up.sh

data-refresh-local:
	bash utils/sync_data_down.sh
	python utils/reshard_logs.py --data-dir /Users/tyler/Git/firewatch-data
	python utils/generate_traffic_analytics.py --data-dir /Users/tyler/Git/firewatch-data --db-file /Users/tyler/Git/firewatch-data-cache/traffic_analytics.db
	python utils/move_old_junk.py --data-dir /Users/tyler/Git/firewatch-data --cache-file /Users/tyler/Git/firewatch-data-cache/firewatch_cache.db
	python utils/update_cache.py --rebuild-all --data-dir /Users/tyler/Git/firewatch-data --cache-file /Users/tyler/Git/firewatch-data-cache/firewatch_cache.db
