# syntax=docker/dockerfile:1
# Analyse statique et tests Pester des scripts Windows, sous Linux (PowerShell 7).
# La compatibilite Windows PowerShell 5.1 est controlee par la regle
# PSUseCompatibleSyntax ici, et par un vrai runner Windows en CI (W11).
FROM mcr.microsoft.com/powershell:7.5-ubuntu-24.04
RUN pwsh -NoLogo -NoProfile -Command "Set-PSRepository PSGallery -InstallationPolicy Trusted; \
    Install-Module Pester -RequiredVersion 5.7.1 -Scope AllUsers -Force -SkipPublisherCheck; \
    Install-Module PSScriptAnalyzer -RequiredVersion 1.25.0 -Scope AllUsers -Force"
ENV HOME=/tmp/home
WORKDIR /work
CMD ["timeout", "--signal=KILL", "600", "pwsh", "-NoLogo", "-NoProfile", "-File", "/work/packaging/windows/tests/run.ps1"]
