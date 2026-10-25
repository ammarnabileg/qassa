# Web container: React back-office at / and the Flutter customer PWA at /app/, API proxied to backend.
FROM node:22-alpine AS react
WORKDIR /src
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
COPY VERSION scripts/ /tmp/v/
ARG SOURCE_COMMIT=""
RUN apk add --no-cache python3 && mkdir -p /scripts && cp /tmp/v/version.py /scripts/ && cp /tmp/v/VERSION / \
 && QASSA_VERSION=$(SOURCE_COMMIT=$SOURCE_COMMIT python3 /scripts/version.py) QASSA_CHANNEL=debug npm run build

FROM debian:bookworm-slim AS flutter
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates xz-utils git unzip python3 && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL https://storage.googleapis.com/flutter_infra_release/releases/stable/linux/flutter_linux_3.47.8-stable.tar.xz | tar xJ -C /opt \
 && git config --global --add safe.directory /opt/flutter
ENV PATH=/opt/flutter/bin:$PATH
WORKDIR /src
COPY mobile/pubspec.* ./
RUN flutter pub get
COPY mobile/ ./
COPY VERSION /VERSION
COPY scripts/ /scripts/
ARG SOURCE_COMMIT=""
RUN V=$(SOURCE_COMMIT=$SOURCE_COMMIT python3 /scripts/version.py) \
 && flutter build web --release --base-href /app/ --dart-define=API_URL= --dart-define=QASSA_VERSION=$V --dart-define=QASSA_CHANNEL=debug

FROM nginx:1.27-alpine
COPY --from=react /src/dist /usr/share/nginx/html
COPY --from=flutter /src/build/web /usr/share/nginx/html/app
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
