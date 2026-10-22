#!/usr/bin/env bash
# End-to-end check of a running compose stack: static app, /api/health and one /api/quote through nginx.
set -euo pipefail
BASE="${BASE_URL:-http://localhost:${WEB_PORT:-8080}}"

for i in $(seq 1 30); do
  curl -fsS "$BASE/api/health" >/dev/null 2>&1 && break
  [ "$i" = 30 ] && { echo "stack not healthy at $BASE" >&2; exit 1; }
  sleep 2
done

curl -fsS "$BASE/" | grep -q '<div id="root">' || { echo "frontend not served" >&2; exit 1; }
curl -fsS "$BASE/api/health"; echo
curl -fsS "$BASE/api/quote" -H 'content-type: application/json' -d '{
  "driver_age": 22, "vehicle_age": 3, "vehicle_power": 7, "bonus_malus": 90,
  "population_density": 2500, "fuel_type": "Diesel", "vehicle_brand": "B12",
  "region_name": "Ile-de-France"}' \
| python3 "$(dirname "$0")/check_quote.py"
status=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/api/quote" -H 'content-type: application/json' -d '{"driver_age": 5}')
[ "$status" = 422 ] || { echo "invalid quote returned $status, expected 422" >&2; exit 1; }
echo "validation ok (422)"
