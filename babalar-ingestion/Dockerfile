FROM node:20-slim

ARG BUILD_VERSION=dev
ENV APP_VERSION=$BUILD_VERSION

RUN apt-get update && apt-get install -y \
    chromium \
    fonts-noto \
    --no-install-recommends && rm -rf /var/lib/apt/lists/*

ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true
ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium

WORKDIR /app
COPY package*.json ./
RUN npm install --omit=dev

COPY src/ ./src/

CMD ["node", "src/index.js"]
