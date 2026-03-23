FROM oven/bun:1.2.0-alpine AS build

WORKDIR /app

COPY package.json bun.lock ./
COPY apps/webapp/package.json ./apps/webapp/package.json
COPY apps/worker/package.json ./apps/worker/package.json
COPY apps/backend/fastapi/package.json ./apps/backend/fastapi/package.json
COPY apps/simulator/package.json ./apps/simulator/package.json
COPY ml/package.json ./ml/package.json
COPY shacklib/package.json ./shacklib/package.json

RUN bun install --frozen-lockfile

COPY apps/webapp/ ./apps/webapp/

ARG VITE_BACKEND_URL
ENV VITE_BACKEND_URL=${VITE_BACKEND_URL}

WORKDIR /app/apps/webapp
RUN bun run build

FROM nginx:1.27-alpine

COPY docker/webapp.nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/apps/webapp/dist /usr/share/nginx/html

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1/health || exit 1

EXPOSE 80
