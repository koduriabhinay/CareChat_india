#!/usr/bin/env bash
# Builds deploy/catalyst/ into a folder the Catalyst CLI can deploy:
#   build/catalyst/appsail  -> the API (AppSail, Python 3.11)
#   build/catalyst/client   -> the web app (Catalyst web client hosting)
#
# Usage:
#   CARECHAT_API_URL=https://<your-appsail-url> ./deploy/build_catalyst.sh
#   cd build/catalyst && catalyst deploy
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT=$(pwd)
OUT=$ROOT/build/catalyst
: "${CARECHAT_API_URL:?Set CARECHAT_API_URL to your AppSail URL (see README)}"
# Catalyst web client hosting serves the app under /app. Set to "" for Slate or a custom domain.
BASE_PATH=${CARECHAT_BASE_PATH-/app}

rm -rf "$OUT"
mkdir -p "$OUT/appsail/lib" "$OUT/client"
cp deploy/catalyst/catalyst.json "$OUT/"
[ -f deploy/catalyst/.catalystrc ] && cp deploy/catalyst/.catalystrc "$OUT/"

echo "== API"
cp -r backend/carechat "$OUT/appsail/carechat"
find "$OUT/appsail/carechat" -name __pycache__ -prune -exec rm -rf {} +
cp deploy/catalyst/app.py deploy/catalyst/app-config.json "$OUT/appsail/"
if [ -f backend/knowledge.db ]; then cp backend/knowledge.db "$OUT/appsail/"; else echo "!! backend/knowledge.db not found: answers will have no sources. Run backend/scripts/ingest_medlineplus.py first."; fi
# Linux wheels for AppSail, whatever computer this runs on.
PIP_TARGET_OPTS=(--target "$OUT/appsail/lib" --platform manylinux2014_x86_64 --python-version 3.11 --only-binary=:all: --upgrade)
python3 -m pip install -q "${PIP_TARGET_OPTS[@]}" -r backend/requirements.txt uvicorn requests
# zcatalyst-sdk pins an old typing-extensions that clashes with pydantic; it works with the newer one.
python3 -m pip install -q "${PIP_TARGET_OPTS[@]}" --no-deps zcatalyst-sdk==1.4.0

echo "== Web app"
(cd frontend && npm ci --silent && NEXT_PUBLIC_API_URL="$CARECHAT_API_URL" NEXT_PUBLIC_BASE_PATH="$BASE_PATH" npm run build)
cp -r frontend/out/. "$OUT/client/"
cp deploy/catalyst/client/client-package.json "$OUT/client/"

echo "Built $OUT. Next: cd build/catalyst && catalyst deploy"
