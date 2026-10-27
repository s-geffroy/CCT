# Cibles de la CI GitHub (runner Ubuntu, docker disponible). Sur le VPS, on passe
# par appctl (tests/test_smoke.sh) : jamais de docker direct ici.
IMAGE ?= cct:ci
APP_VERSION ?= 0.0.0-ci
VCS_REF ?= $(shell git rev-parse --short HEAD 2>/dev/null || echo unknown)

.PHONY: ci test windows-requirements bundle-check image smoke e2e

ci: test windows-requirements bundle-check image smoke e2e

# pytest dans l'image de test (vrai Stockfish) ; le build rejoue aussi
# typecheck + vitest du frontend (stage `frontend`).
test:
	docker build -f backend/Dockerfile --target test -t cct-test:ci .
	docker run --rm cct-test:ci

# Dependances de l'installateur natif : exactement uv.lock (versions et empreintes).
windows-requirements:
	# Image distroless : pas de /tmp, ou uv ecrit un fichier temporaire. Options
	# par variables : la ligne de commande est recopiee dans l en-tete compare.
	docker run --rm --tmpfs /tmp -e UV_NO_CACHE=1 -v "$(CURDIR)/backend:/b:ro" -w /b \
	  ghcr.io/astral-sh/uv:0.13.5@sha256:32a7bb39b496babbd997b0a39a4d66c126bdaf5661b302bf6f06abda8deca6ff \
	  export --frozen --no-dev --no-emit-project --format requirements-txt \
	  | diff -u packaging/windows-native/requirements.txt -

# Le ZIP Windows se fabrique et se controle (digest factice) : un defaut de
# packaging se voit avant le tag, pas au moment de la release.
bundle-check:
	python3 scripts/ci/make_windows_bundle.py v0.0.0-ci ghcr.io/s-geffroy/cct sha256:$$(printf '0%.0s' $$(seq 64)) /tmp/cct-bundle-check

image:
	docker build -f backend/Dockerfile --target runtime \
	  --build-arg APP_VERSION=$(APP_VERSION) --build-arg VCS_REF=$(VCS_REF) -t $(IMAGE) .

# L'image FINALE demarre comme sous Windows (lecture seule, volume) et repond.
smoke:
	scripts/ci/smoke-image.sh $(IMAGE)

# Playwright/Chromium contre l'image finale.
e2e:
	scripts/ci/e2e.sh $(IMAGE)
