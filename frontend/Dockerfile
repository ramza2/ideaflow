FROM node:22-alpine AS build

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./

ARG VITE_API_BASE_URL=/api/v1
ARG VITE_AUTH_CSRF_COOKIE_NAME=ideaflow_csrf
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV VITE_AUTH_CSRF_COOKIE_NAME=${VITE_AUTH_CSRF_COOKIE_NAME}

RUN npm run build

FROM nginx:stable-alpine

COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
