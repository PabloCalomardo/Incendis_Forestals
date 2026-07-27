#!/bin/sh
set -eu

DATA_DIR=/data/cnig
DOWNLOAD_ID="${CNIG_ROADS_DOWNLOAD_ID:-11655655}"
OUTER_ZIP="$DATA_DIR/igr_rt_spain.zip"
EXTRACT_DIR="$DATA_DIR/igr_rt_spain"
GPKG=$(find "$EXTRACT_DIR" -name rt_viaria.gpkg -print -quit 2>/dev/null || true)

if [ -z "$GPKG" ]; then
  mkdir -p "$EXTRACT_DIR"
  if [ ! -f "$OUTER_ZIP" ]; then
    curl --fail --location --retry 3 \
      --data "secDescDirLA=$DOWNLOAD_ID" \
      --output "$OUTER_ZIP" \
      https://centrodedescargas.cnig.es/CentroDescargas/descargaDir
  fi
  unzip -o "$OUTER_ZIP" -d "$EXTRACT_DIR"
  ROAD_ZIP=$(find "$EXTRACT_DIR" -name '*RT_VIARIA_CARRETERAS.zip' -print -quit)
  test -n "$ROAD_ZIP"
  unzip -o "$ROAD_ZIP" -d "$EXTRACT_DIR/RT_VIARIA_CARRETERAS"
  GPKG=$(find "$EXTRACT_DIR" -name rt_viaria.gpkg -print -quit)
fi

test -n "$GPKG"
PG="PG:host=postgres port=5432 dbname=$POSTGRES_DB user=$POSTGRES_USER password=$POSTGRES_PASSWORD"

ogr2ogr -f PostgreSQL "$PG" "$GPKG" rt_tramo_vial \
  -nln cnig_road_segments -overwrite -t_srs EPSG:4326 \
  -lco GEOMETRY_NAME=geometry -lco FID=fid -nlt LINESTRING

ogr2ogr -f PostgreSQL "$PG" "$GPKG" rt_ppkk_p \
  -nln cnig_road_kilometers -overwrite -t_srs EPSG:4326 \
  -lco GEOMETRY_NAME=geometry -lco FID=id -nlt POINT

psql "host=postgres port=5432 dbname=$POSTGRES_DB user=$POSTGRES_USER password=$POSTGRES_PASSWORD" <<'SQL'
CREATE INDEX IF NOT EXISTS ix_cnig_road_segments_geometry ON cnig_road_segments USING gist (geometry);
CREATE INDEX IF NOT EXISTS ix_cnig_road_segments_name ON cnig_road_segments (upper(nombre));
CREATE INDEX IF NOT EXISTS ix_cnig_road_segments_code ON cnig_road_segments (upper(codigo));
CREATE INDEX IF NOT EXISTS ix_cnig_road_kilometers_geometry ON cnig_road_kilometers USING gist (geometry);
CREATE INDEX IF NOT EXISTS ix_cnig_road_kilometers_name ON cnig_road_kilometers (upper(nombre));
ANALYZE cnig_road_segments;
ANALYZE cnig_road_kilometers;
SQL

echo "CNIG road network imported from $GPKG"
