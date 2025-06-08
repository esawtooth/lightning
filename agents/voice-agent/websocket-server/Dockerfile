FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --omit=dev
COPY src ./src
COPY tsconfig.json ./tsconfig.json
RUN npx tsc
EXPOSE 8081
CMD ["node","dist/server.js"]
