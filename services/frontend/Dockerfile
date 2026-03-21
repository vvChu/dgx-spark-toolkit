# Stage 1: Build
FROM node:20-slim AS builder
WORKDIR /app
COPY package.json .
RUN npm install
COPY . .
ARG VITE_API_URL
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# Stage 2: Serve
FROM nginx:alpine
# Copy built assets to Nginx html directory
COPY --from=builder /app/dist /usr/share/nginx/html
# Expose default Nginx port
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
