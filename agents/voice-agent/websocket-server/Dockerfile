FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
# install all dependencies including devDependencies so TypeScript
# compilation succeeds during the image build
RUN npm ci
COPY src ./src
COPY tsconfig.json ./tsconfig.json
RUN npx tsc && cp src/twiml.xml dist/
EXPOSE 8081
CMD ["node","dist/server.js"]
