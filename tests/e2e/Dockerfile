# syntax=docker/dockerfile:1
# Tests de bout en bout dans un vrai Chromium (image officielle Playwright,
# navigateurs inclus, version alignee sur @playwright/test).
FROM mcr.microsoft.com/playwright:v1.64.0-noble
WORKDIR /e2e
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund --loglevel=error
COPY playwright.config.ts ./
COPY specs ./specs
# Le depot est en 0660 sur l'hote : rendre les fichiers lisibles par l'utilisateur
# non privilegie qui lance les tests.
RUN chmod -R a+rX /e2e
ENV HOME=/tmp/home
# Plafond dur au-dela du globalTimeout de Playwright (appctl down ne touche pas
# aux conteneurs ponctuels).
CMD ["timeout", "--signal=KILL", "1500", "npx", "playwright", "test"]
