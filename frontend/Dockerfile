FROM node:20-alpine
WORKDIR /usr/src/app
COPY package.json vite.config.js .
RUN npm install
COPY index.html ./
COPY src ./src
COPY public ./public
EXPOSE 5173
CMD ["npm","run","dev","--","--host"]
