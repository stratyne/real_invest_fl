FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# Stage 2 — export built files for Nginx to consume via named volume
FROM alpine:3.19 AS exporter

WORKDIR /dist

COPY --from=builder /app/dist ./
