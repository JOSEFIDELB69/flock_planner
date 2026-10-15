FROM node:22-alpine AS build
WORKDIR /app
# El destino del proxy /api/v1 se fija en el build (rewrites de Next.js)
ARG API_BASE_URL=http://backend:8000
ARG NEXT_PUBLIC_APP_ENV=prod
ENV API_BASE_URL=$API_BASE_URL NEXT_PUBLIC_APP_ENV=$NEXT_PUBLIC_APP_ENV NEXT_TELEMETRY_DISABLED=1
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
USER node
EXPOSE 3000
CMD ["node", "server.js"]
