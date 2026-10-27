# syntax=docker/dockerfile:1
# Analyse statique et tests Pester des scripts Windows, sous Linux (PowerShell 7).
# La compatibilite Windows PowerShell 5.1 est controlee par la regle
# PSUseCompatibleSyntax ici, et par un vrai runner Windows en CI (W11).
# Image figee par digest : le tag 7.5-ubuntu-24.04 bouge.
FROM mcr.microsoft.com/powershell:7.5-ubuntu-24.04@sha256:042240d57ec9e47e511033b92625a8d95875ee5860af3015992c248b58a8be81
# Modules hors PowerShell Gallery (versions et empreintes figees, meme script
# que la CI Windows) ; le build echoue si l'un manque.
COPY packaging/windows/tests/install-test-modules.ps1 /tmp/install-test-modules.ps1
RUN pwsh -NoLogo -NoProfile -File /tmp/install-test-modules.ps1 -Destination /usr/local/share/powershell/Modules \
 && pwsh -NoLogo -NoProfile -Command "\$ErrorActionPreference = 'Stop'; Import-Module Pester -RequiredVersion 5.7.1; Import-Module PSScriptAnalyzer -RequiredVersion 1.25.0" \
 && rm /tmp/install-test-modules.ps1
ENV HOME=/tmp/home
WORKDIR /work
CMD ["timeout", "--signal=KILL", "600", "pwsh", "-NoLogo", "-NoProfile", "-File", "/work/packaging/windows/tests/run.ps1"]
