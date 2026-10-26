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

FROM nginx:1.27-alpine
COPY --from=react /src/dist /usr/share/nginx/html/admin
# Flutter PWA is prebuilt (deploy/build-pwa.sh): the host is ARM with a slow link.
COPY deploy/pwa /usr/share/nginx/html/pwa
COPY deploy/proxy.inc /etc/nginx/conf.d/proxy.inc
# nginx's entrypoint renders templates with envsubst (PLATFORM_HOST) into conf.d/default.conf
COPY deploy/nginx.conf.template /etc/nginx/templates/default.conf.template
RUN rm -f /etc/nginx/conf.d/default.conf
