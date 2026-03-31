FROM node:20-slim AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci --legacy-peer-deps
COPY . .
RUN rm -f .env.local .env.production
RUN mkdir -p public
RUN npm run build

FROM node:20-slim
WORKDIR /app
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
EXPOSE 3000
ENV HOSTNAME=0.0.0.0
CMD ["node", "server.js"]
