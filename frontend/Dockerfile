FROM node:22-slim AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci --legacy-peer-deps
COPY . .
RUN rm -f .env.local .env.production
RUN mkdir -p public
# next.config.mjs reads BACKEND_URL for its /api and /health rewrites, and
# `next build` bakes rewrite destinations into the standalone output: setting
# BACKEND_URL on the running container changes nothing. Pass it as a build arg.
ARG BACKEND_URL=http://backend:8000
ENV BACKEND_URL=${BACKEND_URL}
RUN npm run build

FROM node:22-slim
WORKDIR /app
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static
USER node
EXPOSE 3000
ENV HOSTNAME=0.0.0.0
CMD ["node", "server.js"]
