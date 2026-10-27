#requires -Version 5.1
# Sauvegarde coherente de la base (faite dans le conteneur, verifiee), copiee dans
# %LOCALAPPDATA%\ChessCalculationTrainer\backups.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')
try {
    $appRoot = Get-AppRoot
    if (-not (Test-Path -LiteralPath (Join-Path $appRoot '.env'))) { throw 'Application non installee : rien a sauvegarder.' }
    Assert-DockerReady
    $saved = Invoke-AppBackup $appRoot
    Write-Host ('Sauvegarde verifiee (' + $saved.Sessions + ' seance(s), schema v' + $saved.Schema + ') :')
    Write-Host ('  ' + (Protect-Text $saved.Path))
    exit 0
} catch {
    Write-Host ('ERREUR : ' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
