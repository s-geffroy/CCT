#requires -Version 5.1
# Arrete l'application sans toucher aux donnees (volume conserve).
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')
try {
    $appRoot = Get-AppRoot
    if (-not (Test-Path -LiteralPath (Join-Path $appRoot '.env'))) { throw 'Application non installee : rien a arreter.' }
    Assert-DockerReady
    Invoke-Compose $appRoot @('stop') | Out-Null
    Write-Host 'Application arretee ; vos donnees sont conservees.'
    exit 0
} catch {
    Write-Host ('ERREUR : ' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
