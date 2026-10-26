# syntax=docker/dockerfile:1
#
# Image unique linux/amd64 : API FastAPI + UI statique + Stockfish 19.
# Contexte de build : la racine du depot.
#
# Etapes :
#   devtools  outils de dev (Node, Python, uv) pour generer les lockfiles ;
#             jamais livree.
#   stockfish compilation du tag officiel sf_19, binaire "universal" (choix
#             du jeu d'instructions a l'execution : aucun AVX2 impose).
#   frontend  typecheck + tests + build Vite ; un echec casse le build.
#   pydeps    dependances Python figees par uv.lock.
#   runtime   l'image livree, non root.
#   test      runtime + dependances de test (pytest), pour `appctl run tests`.

ARG PYTHON_IMAGE=python:3.13-slim-trixie
ARG NODE_IMAGE=node:24-trixie-slim
ARG DEBIAN_IMAGE=debian:trixie-slim
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.13.5

FROM ${UV_IMAGE} AS uv

# ---------------------------------------------------------------- devtools
FROM ${NODE_IMAGE} AS devtools
COPY --from=uv /uv /usr/local/bin/uv
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 ca-certificates git \
 && rm -rf /var/lib/apt/lists/*
ENV HOME=/tmp/home \
    npm_config_cache=/tmp/npm-cache \
    UV_CACHE_DIR=/tmp/uv-cache \
    UV_PYTHON_INSTALL_DIR=/tmp/uv-python
WORKDIR /work

# ---------------------------------------------------------------- stockfish
FROM ${DEBIAN_IMAGE} AS stockfish
ARG SF_TAG=sf_19
ARG SF_SHA256=519b653d0d1ffb96531d982ccbe5c6a19425e8388e0e3c2f70f34b424ab32d76
ARG SF_NET=nn-1a298aa575a0.nnue
ARG SF_NET_SHA256=1a298aa575a085434d29027978dc36867fe9c5bcea9376654b7a8eba1e52dfc2
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential ca-certificates curl bsdextrautils \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /build
RUN curl -fsSL -o sf.tar.gz "https://github.com/official-stockfish/Stockfish/archive/refs/tags/${SF_TAG}.tar.gz" \
 && echo "${SF_SHA256}  sf.tar.gz" | sha256sum -c - \
 && tar xzf sf.tar.gz && mv "Stockfish-${SF_TAG}" src-root
WORKDIR /build/src-root/src
# Le reseau est telecharge et verifie ici (empreinte complete) : le Makefile
# le trouve deja present et ne telecharge rien lui-meme.
RUN curl -fsSL -o "${SF_NET}" "https://tests.stockfishchess.org/api/nn/${SF_NET}" \
 && echo "${SF_NET_SHA256}  ${SF_NET}" | sha256sum -c -
# Piege du build "universal" : sans #embed (GCC 14), le reseau est incorpore via
# un hexdump ; si `hexdump` manque (bsdextrautils), le binaire embarque un
# reseau VIDE sans aucune erreur. D'ou le controle de taille du dump, et des
# tests lances depuis un repertoire vide : sans reseau embarque, Stockfish
# s'arrete au premier `go`.
RUN make -j"$(nproc)" build ARCH=x86-64-universal COMP=gcc \
 && dump_size=$(stat -c %s universal/network_dump.inc 2>/dev/null || echo 0) \
 && echo "network_dump.inc : ${dump_size} octets" \
 && { [ ! -e universal/network_dump.inc ] || [ "$dump_size" -gt 100000000 ]; } \
 && strip stockfish \
 && install -D -m 0755 stockfish /out/stockfish \
 && mkdir /empty && cd /empty \
 && /out/stockfish bench 16 1 10 > /build/bench.txt 2>&1 \
 && tail -n 5 /build/bench.txt \
 && grep -q '^Nodes searched' /build/bench.txt \
 && printf 'uci\nisready\nposition startpos\ngo depth 8\n' | timeout 60 /out/stockfish | grep -q '^bestmove' \
 && cp /build/src-root/Copying.txt /out/COPYING-stockfish.txt \
 && printf 'tag=%s\nsource_sha256=%s\nnet=%s\nnet_sha256=%s\narch=x86-64-universal\nnet_embedded=yes\n' \
      "${SF_TAG}" "${SF_SHA256}" "${SF_NET}" "${SF_NET_SHA256}" > /out/stockfish-build.txt

# ---------------------------------------------------------------- frontend
FROM ${NODE_IMAGE} AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run typecheck && npm test && npm run build

# ---------------------------------------------------------------- pydeps
FROM ${PYTHON_IMAGE} AS pydeps
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/venv \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# ---------------------------------------------------------------- runtime
FROM ${PYTHON_IMAGE} AS runtime
ENV PATH=/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_DATA_DIR=/data \
    APP_STATIC_DIR=/app/static \
    STOCKFISH_PATH=/usr/local/bin/stockfish
COPY --from=pydeps /venv /venv
COPY --from=stockfish /out/stockfish /usr/local/bin/stockfish
COPY --from=stockfish /out/COPYING-stockfish.txt /out/stockfish-build.txt /usr/share/doc/stockfish/
COPY --from=frontend /frontend/dist /app/static
COPY backend/app /app/app
# Le depot est en 0660 sur l'hote et COPY conserve les modes : sans ce chmod,
# l'utilisateur 'app' ne peut pas lire le code.
# /data est cree ICI et possede par 'app' : un volume nomme vide herite du
# proprietaire du repertoire de l'image.
RUN chmod -R a+rX /app \
 && useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin app \
 && mkdir -p /data && chown app:app /data
USER app
WORKDIR /app
EXPOSE 8000
# Un seul worker Uvicorn : le planificateur Stockfish vit dans ce processus.
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-server-header", "--no-access-log"]

# ---------------------------------------------------------------- test
FROM runtime AS test
USER root
COPY --from=uv /uv /usr/local/bin/uv
COPY backend/pyproject.toml backend/uv.lock /backend/
RUN cd /backend && UV_PROJECT_ENVIRONMENT=/venv UV_PYTHON_DOWNLOADS=never \
    uv sync --frozen --only-group dev --inexact --no-install-project
COPY backend/tests /app/tests
RUN chmod -R a+rX /app/tests /backend
USER app
# Plafond dur : un test bloque ne laisse pas un conteneur `appctl run` orphelin
# (appctl down ne touche pas aux conteneurs ponctuels).
CMD ["timeout", "--signal=KILL", "1200", "python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "-c", "/backend/pyproject.toml", "--rootdir", "/app", "/app/tests"]
