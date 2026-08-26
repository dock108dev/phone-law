FROM node:26.3.0-alpine3.22

ARG COLACCI_CANDIDATE_COMMIT=unbound
ARG COLACCI_CANDIDATE_TREE=unbound
ARG COLACCI_RUNTIME_CONTRACT=unbound

LABEL io.colacci-law.candidate.commit="$COLACCI_CANDIDATE_COMMIT" \
    io.colacci-law.candidate.tree="$COLACCI_CANDIDATE_TREE" \
    io.colacci-law.runtime.contract="$COLACCI_RUNTIME_CONTRACT"

WORKDIR /workspace/apps/web

RUN npm install --global npm@12.0.2
COPY --chown=node:node apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY --chown=node:node apps/web ./
RUN chown -R node:node /workspace/apps/web

USER node
EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
