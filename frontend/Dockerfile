# CloudOps Sentinel console: build the React app with Node, serve it with Nginx.
# Built by compose.yaml (context: frontend/).

# --- build: npm ci from the lockfile, then vite build ----------------------------------
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

# --- runtime: static files + reverse proxy, non-root Nginx listening on 8080 -----------
FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
