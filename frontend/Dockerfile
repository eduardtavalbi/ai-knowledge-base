FROM node:22-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=${VITE_API_URL}

RUN npm run build


FROM nginx:alpine

ARG VITE_API_URL=http://localhost:8000
COPY nginx.conf /etc/nginx/conf.d/default.conf
RUN case "$VITE_API_URL" in http://*|https://*) ;; *) echo "VITE_API_URL must be an HTTP(S) API origin" >&2; exit 1 ;; esac \
    && sed -i "s|__API_CONNECT_ORIGIN__|$VITE_API_URL|g" /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1
