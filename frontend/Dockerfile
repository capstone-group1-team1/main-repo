# Multi-stage Next.js image (Module 10 §10). Builder compiles; runner ships
# only the standalone output — small final image, no devDependencies.

# --- Stage 1: builder ---
FROM node:20-alpine AS builder
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Next.js doesn't require a public/ folder to build, and git doesn't track
# empty directories — so a fresh checkout can legitimately be missing it,
# which would otherwise hard-fail the runner stage's COPY below. Guarantee
# it exists before build.
RUN mkdir -p public

# NEXT_PUBLIC_* is baked in at build time; the compose build arg supplies it.
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL

RUN npm run build

# --- Stage 2: runner ---
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production

# 'standalone' output bundles a minimal server + only the needed node_modules.
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3000

CMD ["node", "server.js"]