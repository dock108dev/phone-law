FROM mcr.microsoft.com/playwright:v1.62.1-noble

ARG COLACCI_CANDIDATE_COMMIT=unbound
ARG COLACCI_CANDIDATE_TREE=unbound
ARG COLACCI_RUNTIME_CONTRACT=unbound

LABEL io.colacci-law.candidate.commit="$COLACCI_CANDIDATE_COMMIT" \
    io.colacci-law.candidate.tree="$COLACCI_CANDIDATE_TREE" \
    io.colacci-law.runtime.contract="$COLACCI_RUNTIME_CONTRACT"

WORKDIR /workspace/apps/web
RUN npm install --global npm@12.0.2
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web ./
RUN chown -R pwuser:pwuser /workspace/apps/web

USER pwuser
