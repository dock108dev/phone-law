FROM mcr.microsoft.com/playwright:v1.62.1-noble

WORKDIR /workspace/apps/web
RUN npm install --global npm@10.9.3
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web ./
RUN chown -R pwuser:pwuser /workspace/apps/web

USER pwuser
