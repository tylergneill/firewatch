LOCAL_DATA_PATH = $(shell realpath $(dir $(lastword $(MAKEFILE_LIST)))../firewatch-data)
LOCAL_CACHE_PATH = $(shell realpath $(dir $(lastword $(MAKEFILE_LIST)))../firewatch-data-cache)

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
	  tylergneill/firewatch-app:$(VERSION)
