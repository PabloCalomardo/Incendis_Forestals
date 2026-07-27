FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gdal-bin postgresql-client unzip \
    && rm -rf /var/lib/apt/lists/*

COPY infrastructure/scripts/import-cnig-roads.sh /usr/local/bin/import-cnig-roads
RUN chmod +x /usr/local/bin/import-cnig-roads

ENTRYPOINT ["import-cnig-roads"]
