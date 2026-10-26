#!/usr/bin/env bash
# Builds the Flutter PWA into deploy/pwa (committed). The Coolify host is ARM and has a slow link,
# so Flutter is not built there. Re-run after every change in mobile/ and commit the result.
set -euo pipefail
cd "$(dirname "$0")/../mobile"
v=$(python3 ../scripts/version.py)
flutter build web --release --base-href / --dart-define=API_URL= --dart-define=QASSA_VERSION="$v" --dart-define=QASSA_CHANNEL=debug
rm -rf ../deploy/pwa && cp -r build/web ../deploy/pwa
rm -rf ../deploy/pwa/canvaskit
# per-company manifest is served by the backend at /manifest.json (D-005)
sed -i 's#<link rel="manifest" href="manifest.json">#<link rel="manifest" href="/manifest.json">#' ../deploy/pwa/index.html   # loaded from Google CDN (Flutter default)
echo "PWA $v → deploy/pwa"
