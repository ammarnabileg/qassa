#!/usr/bin/env bash
# Usage: tool/build.sh <apk|appbundle|ipa|web> <debug|release> [API_URL]
# Version comes from ../VERSION via scripts/version.py (release = tagged vX.Y.Z, debug = X.(Y+1).0-dev.N+sha).
set -euo pipefail
cd "$(dirname "$0")/.."
target=$1; mode=$2; api=${3-http://localhost:8000}   # "" = same origin (PWA behind the same domain as the API)
version=$(python3 ../scripts/version.py); channel=$(python3 ../scripts/version.py --channel)
name=${version%%+*}; name=${name%%-*}                       # stores accept X.Y.Z only
build=$(git rev-list --count HEAD)                         # monotonic build number
if [[ $mode == release && $channel != release ]]; then
  echo "refusing release build: HEAD is not tagged v$(cat ../VERSION) (current: $version)" >&2; exit 1
fi
flutter build "$target" --"$mode" --build-name="$name" --build-number="$build" \
  --dart-define=API_URL="$api" --dart-define=QASSA_VERSION="$version" --dart-define=QASSA_CHANNEL="$channel"
