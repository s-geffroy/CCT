# Notices des composants tiers

Chess Calculation Trainer est distribue sous **GPL-3.0-or-later** (fichier
`LICENSE`). L'image `ghcr.io/s-geffroy/cct` et le paquet Windows contiennent les
composants ci-dessous, chacun sous sa propre licence.

Liste generee depuis l'image finale et les lockfiles (`scripts/notices_python.py`,
`scripts/notices_npm.mjs`, voir « Regenerer » plus bas).

## Moteur d'echecs

| Composant | Version | Licence | Source correspondante |
|---|---|---|---|
| Stockfish | 19 (tag `sf_19`, archive sha256 `519b653d0d1ffb96531d982ccbe5c6a19425e8388e0e3c2f70f34b424ab32d76`) | GPL-3.0 | https://github.com/official-stockfish/Stockfish/tree/sf_19 |
| Reseau NNUE `nn-1a298aa575a0.nnue` | sha256 `1a298aa575a085434d29027978dc36867fe9c5bcea9376654b7a8eba1e52dfc2` | distribue avec Stockfish (GPL-3.0) | https://tests.stockfishchess.org/api/nn/nn-1a298aa575a0.nnue |

Stockfish est compile sans modification (`ARCH=x86-64-universal`) par
`backend/Dockerfile` ; son texte de licence est copie dans l'image
(`/usr/share/doc/stockfish/COPYING-stockfish.txt`). La source correspondante de
chaque version publiee est le tag Git du present depot (`backend/Dockerfile`
indique les sources exactes et leurs empreintes).

## Serveur (Python, image finale)

| Paquet | Version | Licence |
|---|---|---|
| annotated-doc | 0.0.5 | MIT |
| annotated-types | 0.8.0 | MIT |
| anyio | 4.15.1 | MIT |
| chess | 1.11.2 | GNU General Public License v3 or later (GPLv3+) |
| click | 8.5.0 | BSD-3-Clause |
| fastapi | 0.162.0 | MIT |
| h11 | 0.16.0 | MIT License |
| idna | 3.20 | BSD-3-Clause |
| opentelemetry-api | 1.45.1 | Apache-2.0 |
| pydantic | 2.14.1 | MIT |
| pydantic_core | 2.50.1 | MIT |
| starlette | 1.10.0 | BSD-3-Clause |
| typing-inspection | 0.4.4 | MIT |
| typing_extensions | 4.16.0 | PSF-2.0 |
| uvicorn | 0.54.0 | BSD-3-Clause |

Interpreteur et systeme : image de base `python:3.13-slim-trixie` (Python, licence
PSF-2.0 ; paquets Debian, licences dans `/usr/share/doc/*/copyright` de l'image).

## Interface (npm, dependances de production et transitives)

| Paquet | Version | Licence |
|---|---|---|
| @babel/runtime | 7.29.10 | MIT |
| @babel/runtime | 7.29.10 | MIT |
| @dnd-kit/accessibility | 3.1.1 | MIT |
| @dnd-kit/core | 6.3.1 | MIT |
| @dnd-kit/modifiers | 9.0.0 | MIT |
| @dnd-kit/utilities | 3.2.2 | MIT |
| @radix-ui/number | 1.1.3 | MIT |
| @radix-ui/primitive | 1.2.0 | MIT |
| @radix-ui/react-accessible-icon | 1.2.0 | MIT |
| @radix-ui/react-accordion | 1.3.1 | MIT |
| @radix-ui/react-alert-dialog | 1.2.1 | MIT |
| @radix-ui/react-arrow | 1.1.17 | MIT |
| @radix-ui/react-aspect-ratio | 1.2.0 | MIT |
| @radix-ui/react-avatar | 1.3.1 | MIT |
| @radix-ui/react-checkbox | 1.4.1 | MIT |
| @radix-ui/react-collapsible | 1.2.1 | MIT |
| @radix-ui/react-collection | 1.2.0 | MIT |
| @radix-ui/react-compose-refs | 1.1.5 | MIT |
| @radix-ui/react-context | 1.3.0 | MIT |
| @radix-ui/react-context-menu | 2.4.1 | MIT |
| @radix-ui/react-dialog | 1.3.1 | MIT |
| @radix-ui/react-direction | 1.2.0 | MIT |
| @radix-ui/react-dismissable-layer | 1.2.1 | MIT |
| @radix-ui/react-dropdown-menu | 2.2.1 | MIT |
| @radix-ui/react-focus-guards | 1.2.0 | MIT |
| @radix-ui/react-focus-scope | 1.3.1 | MIT |
| @radix-ui/react-form | 0.3.0 | MIT |
| @radix-ui/react-hover-card | 1.2.1 | MIT |
| @radix-ui/react-id | 1.1.4 | MIT |
| @radix-ui/react-label | 2.1.17 | MIT |
| @radix-ui/react-menu | 2.2.1 | MIT |
| @radix-ui/react-menubar | 1.2.1 | MIT |
| @radix-ui/react-navigation-menu | 1.4.1 | MIT |
| @radix-ui/react-one-time-password-field | 0.2.1 | MIT |
| @radix-ui/react-password-toggle-field | 0.2.1 | MIT |
| @radix-ui/react-popover | 1.3.1 | MIT |
| @radix-ui/react-popper | 1.4.0 | MIT |
| @radix-ui/react-portal | 1.2.0 | MIT |
| @radix-ui/react-presence | 1.1.11 | MIT |
| @radix-ui/react-primitive | 2.2.0 | MIT |
| @radix-ui/react-progress | 1.2.1 | MIT |
| @radix-ui/react-radio-group | 1.5.1 | MIT |
| @radix-ui/react-roving-focus | 1.2.1 | MIT |
| @radix-ui/react-scroll-area | 1.4.0 | MIT |
| @radix-ui/react-select | 2.4.1 | MIT |
| @radix-ui/react-separator | 1.2.0 | MIT |
| @radix-ui/react-slider | 1.6.1 | MIT |
| @radix-ui/react-slot | 1.5.0 | MIT |
| @radix-ui/react-switch | 1.4.1 | MIT |
| @radix-ui/react-tabs | 1.2.1 | MIT |
| @radix-ui/react-toast | 1.3.1 | MIT |
| @radix-ui/react-toggle | 1.2.1 | MIT |
| @radix-ui/react-toggle-group | 1.2.1 | MIT |
| @radix-ui/react-toolbar | 1.2.1 | MIT |
| @radix-ui/react-tooltip | 1.4.1 | MIT |
| @radix-ui/react-use-callback-ref | 1.1.5 | MIT |
| @radix-ui/react-use-controllable-state | 1.3.0 | MIT |
| @radix-ui/react-use-effect-event | 0.0.5 | MIT |
| @radix-ui/react-use-escape-keydown | 1.1.6 | MIT |
| @radix-ui/react-use-is-hydrated | 0.1.3 | MIT |
| @radix-ui/react-use-layout-effect | 1.1.4 | MIT |
| @radix-ui/react-use-previous | 1.1.4 | MIT |
| @radix-ui/react-use-size | 1.1.5 | MIT |
| @radix-ui/react-visually-hidden | 1.2.13 | MIT |
| @types/react | 19.3.0 | MIT |
| @types/react-dom | 19.3.0 | MIT |
| @types/react-window | 1.8.8 | MIT |
| aria-hidden | 1.2.6 | MIT |
| chess.js | 1.4.0 | BSD-2-Clause |
| class-variance-authority | 0.7.1 | Apache-2.0 |
| clsx | 2.1.1 | MIT |
| csstype | 3.2.3 | MIT |
| lucide-react | 1.55.0 | ISC |
| memoize-one | 5.2.1 | MIT |
| radix-ui | 1.8.1 | MIT |
| react | 19.3.1 | MIT |
| react-arborist | 4.0.1 | MIT |
| react-chessboard | 5.12.1 | MIT |
| react-dnd | 16.0.1 | MIT |
| react-dnd-html5-backend | 16.0.1 | MIT |
| react-dom | 19.3.1 | MIT |
| react-remove-scroll | 2.7.2 | MIT |
| react-window | 1.8.11 | MIT |
| redux | 5.0.1 | MIT |
| sonner | 2.0.8 | MIT |
| tailwind-merge | 3.7.0 | MIT |
| tslib | 2.8.1 | 0BSD |

Les composants `frontend/src/components/ui/` sont generes depuis shadcn/ui
(MIT, https://ui.shadcn.com) puis adaptes.

## Outils de developpement

Les outils de test et de construction (pytest, vitest, Playwright, axe-core,
TypeScript, Vite, PSScriptAnalyzer, Pester...) ne sont pas distribues dans
l'image ni dans le paquet Windows.

## Regenerer cette liste

```bash
sudo appctl run app python -c "$(cat scripts/notices_python.py)"   # serveur
sudo appctl run devtools sh -c 'node /work/scripts/notices_npm.mjs' # interface
```
