FROM node:26.3.0-alpine3.22

WORKDIR /workspace/apps/web

RUN npm install --global npm@10.9.3
COPY --chown=node:node apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY --chown=node:node apps/web ./
RUN chown -R node:node /workspace/apps/web

USER node
EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
