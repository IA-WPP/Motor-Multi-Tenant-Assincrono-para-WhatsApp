FROM node:22-alpine AS build
WORKDIR /console
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
ARG VITE_DATA_SOURCE=api
ARG VITE_API_BASE_URL=
ENV VITE_DATA_SOURCE=$VITE_DATA_SOURCE
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

FROM caddy:2-alpine
COPY integration/Caddyfile.static /etc/caddy/Caddyfile
COPY --from=build /console/dist /srv
EXPOSE 80
