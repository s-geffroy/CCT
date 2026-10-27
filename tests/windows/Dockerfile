# syntax=docker/dockerfile:1
# Analyse statique et tests Pester des scripts Windows, sous Linux (PowerShell 7).
# La compatibilite Windows PowerShell 5.1 est controlee par la regle
# PSUseCompatibleSyntax ici, et par un vrai runner Windows en CI (W11).
# Image figee par digest : le tag 7.5-ubuntu-24.04 bouge, et une nouvelle
# version a deja casse l'installation des modules sans faire echouer le build.
FROM mcr.microsoft.com/powershell:7.5-ubuntu-24.04@sha256:042240d57ec9e47e511033b92625a8d95875ee5860af3015992c248b58a8be81
# PSResourceGet (inclus dans PowerShell 7.4+) ; $ErrorActionPreference = Stop et
# Import-Module : un module absent fait echouer le build au lieu de passer en silence.
RUN pwsh -NoLogo -NoProfile -Command "\$ErrorActionPreference = 'Stop'; \
    Install-PSResource -Name Pester -Version 5.7.1 -Scope AllUsers -TrustRepository -Repository PSGallery; \
    Install-PSResource -Name PSScriptAnalyzer -Version 1.25.0 -Scope AllUsers -TrustRepository -Repository PSGallery; \
    Import-Module Pester -RequiredVersion 5.7.1; Import-Module PSScriptAnalyzer -RequiredVersion 1.25.0"
ENV HOME=/tmp/home
WORKDIR /work
CMD ["timeout", "--signal=KILL", "600", "pwsh", "-NoLogo", "-NoProfile", "-File", "/work/packaging/windows/tests/run.ps1"]
