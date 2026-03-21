# Stage 1: Build
FROM node:20-slim AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG VITE_API_URL
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# Stage 2: Serve
FROM nginx:alpine
# SPA routing + static asset caching
COPY nginx.conf /etc/nginx/conf.d/default.conf
# Copy built assets to Nginx html directory
COPY --from=builder /app/dist /usr/share/nginx/html
# Expose default Nginx port
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
