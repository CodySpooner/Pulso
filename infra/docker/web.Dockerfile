# syntax=docker/dockerfile:1
FROM node:24-trixie-slim AS build
WORKDIR /app
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN npm install --global pnpm@11.9.0
COPY apps/web ./apps/web
# No cache mount: Railway rejects ids without its per-service key (DEC-102).
RUN pnpm install --frozen-lockfile --store-dir=/pnpm/store
ARG NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
ARG API_URL=http://localhost:8000
ENV NEXT_TELEMETRY_DISABLED=1
RUN pnpm --dir apps/web build && mkdir -p apps/web/public

FROM node:24-trixie-slim AS runtime
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=:: PORT=3000
WORKDIR /app
COPY --from=build --chown=node:node /app/apps/web/.next/standalone ./
COPY --from=build --chown=node:node /app/apps/web/.next/static ./apps/web/.next/static
COPY --from=build --chown=node:node /app/apps/web/public ./apps/web/public
USER node
EXPOSE 3000
CMD ["node", "apps/web/server.js"]
