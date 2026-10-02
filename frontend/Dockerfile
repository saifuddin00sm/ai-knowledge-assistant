# syntax=docker/dockerfile:1

# The app is a static export (`output: "export"` in next.config.ts), so the
# runtime image is just a web server. NEXT_PUBLIC_* values are inlined at build
# time, which is why the API URL is a build arg rather than a runtime env var.
# Debian rather than Alpine: Tailwind v4's `@tailwindcss/oxide` has a native
# glibc binary, where musl falls back to a wasm build whose optional deps npm
# will not resolve into a lock file generated on another platform.
FROM node:22-slim AS build

WORKDIR /app

ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
ARG NEXT_PUBLIC_API_KEY=
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL \
    NEXT_PUBLIC_API_KEY=$NEXT_PUBLIC_API_KEY \
    NEXT_TELEMETRY_DISABLED=1

COPY package.json package-lock.json ./
# `npm install`, not `npm ci`: the lock file is generated on the developer's
# platform, and npm does not record the Linux-only optional dependencies that
# Tailwind v4's native binary pulls in, so `npm ci` refuses the lock as
# out of sync. The lock is still honoured for everything it does describe.
RUN npm install --no-audit --no-fund

COPY . .
RUN npm run build

FROM nginx:1.27-alpine AS runtime

COPY --from=build /app/out /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

# 127.0.0.1, not `localhost`: inside the container `localhost` resolves to ::1
# first, and the check would fail against an IPv4-only listener.
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q --spider http://127.0.0.1/ || exit 1
