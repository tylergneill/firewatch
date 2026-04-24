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
	@T0=$$SECONDS; \
	echo "==> [START] data-refresh-full $$(date)"; \
	t=$$SECONDS; bash utils/sync_data_down.sh;                                                                                                                  echo "  [sync_data_down]          $$((SECONDS-t))s"; \
	t=$$SECONDS; python utils/reshard_logs.py --data-dir $(LOCAL_DATA_PATH);                                                                                     echo "  [reshard_logs]            $$((SECONDS-t))s"; \
	t=$$SECONDS; python utils/generate_traffic_analytics.py --data-dir $(LOCAL_DATA_PATH) --db-file $(LOCAL_CACHE_PATH)/traffic_analytics.db;                    echo "  [generate_traffic_analytics] $$((SECONDS-t))s"; \
	t=$$SECONDS; python utils/move_old_junk.py --data-dir $(LOCAL_DATA_PATH) --cache-file $(LOCAL_CACHE_PATH)/firewatch_cache.db;                                echo "  [move_old_junk]           $$((SECONDS-t))s"; \
	t=$$SECONDS; python utils/update_cache.py --rebuild-all --data-dir $(LOCAL_DATA_PATH) --cache-file $(LOCAL_CACHE_PATH)/firewatch_cache.db;                   echo "  [update_cache]            $$((SECONDS-t))s"; \
	t=$$SECONDS; bash utils/sync_data_up.sh;                                                                                                                    echo "  [sync_data_up]            $$((SECONDS-t))s"; \
	echo "==> [DONE] data-refresh-full $$(date) (total: $$((SECONDS-T0))s)"

data-refresh-local:
	@T0=$$SECONDS; \
	echo "==> [START] data-refresh-local $$(date)"; \
	t=$$SECONDS; bash utils/sync_data_down.sh;                                                                                                                  echo "  [sync_data_down]          $$((SECONDS-t))s"; \
	t=$$SECONDS; python utils/reshard_logs.py --data-dir $(LOCAL_DATA_PATH);                                                                                     echo "  [reshard_logs]            $$((SECONDS-t))s"; \
	t=$$SECONDS; python utils/generate_traffic_analytics.py --data-dir $(LOCAL_DATA_PATH) --db-file $(LOCAL_CACHE_PATH)/traffic_analytics.db;                    echo "  [generate_traffic_analytics] $$((SECONDS-t))s"; \
	t=$$SECONDS; python utils/move_old_junk.py --data-dir $(LOCAL_DATA_PATH) --cache-file $(LOCAL_CACHE_PATH)/firewatch_cache.db;                                echo "  [move_old_junk]           $$((SECONDS-t))s"; \
	t=$$SECONDS; python utils/update_cache.py --rebuild-all --data-dir $(LOCAL_DATA_PATH) --cache-file $(LOCAL_CACHE_PATH)/firewatch_cache.db;                   echo "  [update_cache]            $$((SECONDS-t))s"; \
	echo "==> [DONE] data-refresh-local $$(date) (total: $$((SECONDS-T0))s)"

data-refresh-recent:
	@T0=$$SECONDS; \
	echo "==> [START] data-refresh-recent $$(date)"; \
	t=$$SECONDS; bash utils/sync_data_down.sh;                                                                                                                  echo "  [sync_data_down]          $$((SECONDS-t))s"; \
	SINCE=$$(python utils/get_last_processed_date.py --data-dir $(LOCAL_DATA_PATH)); \
	t=$$SECONDS; python utils/reshard_logs.py --data-dir $(LOCAL_DATA_PATH) --since $$SINCE;                                                                     echo "  [reshard_logs]            $$((SECONDS-t))s"; \
	t=$$SECONDS; python utils/generate_traffic_analytics.py --data-dir $(LOCAL_DATA_PATH) --db-file $(LOCAL_CACHE_PATH)/traffic_analytics.db;                    echo "  [generate_traffic_analytics] $$((SECONDS-t))s"; \
	t=$$SECONDS; python utils/move_old_junk.py --start-date $$SINCE --data-dir $(LOCAL_DATA_PATH) --cache-file $(LOCAL_CACHE_PATH)/firewatch_cache.db;           echo "  [move_old_junk]           $$((SECONDS-t))s"; \
	t=$$SECONDS; python utils/update_cache.py --start-date $$SINCE --end-date $$(date +%Y-%m-%d) --data-dir $(LOCAL_DATA_PATH) --cache-file $(LOCAL_CACHE_PATH)/firewatch_cache.db; echo "  [update_cache]            $$((SECONDS-t))s"; \
	t=$$SECONDS; bash utils/sync_data_up.sh;                                                                                                                    echo "  [sync_data_up]            $$((SECONDS-t))s"; \
	echo "==> [DONE] data-refresh-recent $$(date) (total: $$((SECONDS-T0))s)"

data-refresh-recent-local:
	@T0=$$SECONDS; \
	echo "==> [START] data-refresh-recent-local $$(date)"; \
	t=$$SECONDS; bash utils/sync_data_down.sh;                                                                                                                  echo "  [sync_data_down]          $$((SECONDS-t))s"; \
	SINCE=$$(python utils/get_last_processed_date.py --data-dir $(LOCAL_DATA_PATH)); \
	t=$$SECONDS; python utils/reshard_logs.py --data-dir $(LOCAL_DATA_PATH) --since $$SINCE;                                                                     echo "  [reshard_logs]            $$((SECONDS-t))s"; \
	t=$$SECONDS; python utils/generate_traffic_analytics.py --data-dir $(LOCAL_DATA_PATH) --db-file $(LOCAL_CACHE_PATH)/traffic_analytics.db;                    echo "  [generate_traffic_analytics] $$((SECONDS-t))s"; \
	t=$$SECONDS; python utils/move_old_junk.py --start-date $$SINCE --data-dir $(LOCAL_DATA_PATH) --cache-file $(LOCAL_CACHE_PATH)/firewatch_cache.db;           echo "  [move_old_junk]           $$((SECONDS-t))s"; \
	t=$$SECONDS; python utils/update_cache.py --start-date $$SINCE --end-date $$(date +%Y-%m-%d) --data-dir $(LOCAL_DATA_PATH) --cache-file $(LOCAL_CACHE_PATH)/firewatch_cache.db; echo "  [update_cache]            $$((SECONDS-t))s"; \
	echo "==> [DONE] data-refresh-recent-local $$(date) (total: $$((SECONDS-T0))s)"

# Rebuild the local cache without re-running the full data pipeline.
# On the server, run: python utils/update_cache.py --rebuild-all  (no extra flags needed inside the container)
cache-rebuild:
	@T0=$$SECONDS; \
	echo "==> [START] cache-rebuild $$(date)"; \
	python utils/update_cache.py --rebuild-all --data-dir $(LOCAL_DATA_PATH) --cache-file $(LOCAL_CACHE_PATH)/firewatch_cache.db; \
	echo "==> [DONE] cache-rebuild $$(date) (total: $$((SECONDS-T0))s)"

cache-rebuild-recent:
	@T0=$$SECONDS; \
	echo "==> [START] cache-rebuild-recent $$(date)"; \
	python utils/update_cache.py --since-last-processed --data-dir $(LOCAL_DATA_PATH) --cache-file $(LOCAL_CACHE_PATH)/firewatch_cache.db; \
	echo "==> [DONE] cache-rebuild-recent $$(date) (total: $$((SECONDS-T0))s)"
