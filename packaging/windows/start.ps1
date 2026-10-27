#requires -Version 5.1
# Demarre l'application installee et ouvre le navigateur. Toujours depuis le
# dossier d'installation, quel que soit l'endroit d'ou on lance OUVRIR.cmd.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')
try {
    $appRoot = Get-AppRoot
    if (-not (Test-Path -LiteralPath (Join-Path $appRoot '.env'))) {
        throw 'Application pas encore installee : double-cliquez INSTALLER.cmd dans le dossier extrait de la release.'
    }
    Assert-DockerReady
    $url = 'http://127.0.0.1:' + (Get-HostPort (Read-EnvFile (Join-Path $appRoot '.env')))
    Invoke-Compose $appRoot @('up', '-d') | Out-Null
    $state = Wait-App $url 120
    if ($state -eq 'down') { Show-AppLogs $appRoot; throw 'L application ne repond pas.' }
    if ($state -eq 'live') { Write-Warning 'Moteur Stockfish indisponible : les analyses attendront.' }
    Start-Process $url
    exit 0
} catch {
    Write-Host ('ERREUR : ' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
