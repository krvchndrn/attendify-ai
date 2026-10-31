FROM node:20-alpine AS builder

WORKDIR /app

COPY package*.json ./

RUN npm ci

COPY . .

# NEXT_PUBLIC_* values are inlined into the browser bundle at build time.
# Pass the real backend URL here via Docker build-arg (Railway: set as build variable).
# Falls back to placeholder; runtime injection via /public/env-config.js overrides it.
ARG NEXT_PUBLIC_API_URL=__NEXT_PUBLIC_API_URL_PLACEHOLDER__
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

RUN npm run build

FROM node:20-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production

COPY --from=builder /app/public ./public

COPY --from=builder /app/.next/standalone ./

COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000

# Inject runtime env vars into a JS file served to the browser.
# This overrides the build-time baked value so Railway env vars work at runtime.
CMD ["/bin/sh", "-c", "echo \"window.__ENV__ = { NEXT_PUBLIC_API_URL: '${NEXT_PUBLIC_API_URL}' };\" > /app/public/env-config.js && node server.js"]
