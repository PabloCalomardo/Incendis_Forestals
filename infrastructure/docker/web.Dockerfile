FROM node:22-alpine

WORKDIR /app

COPY package.json package.json
COPY apps/web/package.json apps/web/package.json
COPY packages/shared-types/package.json packages/shared-types/package.json
COPY packages/config/package.json packages/config/package.json
COPY packages/ui/package.json packages/ui/package.json
RUN npm install

COPY apps/web apps/web
COPY packages packages

WORKDIR /app/apps/web

EXPOSE 3000
CMD ["npm", "run", "dev"]
