#requires -Version 5.1
# Desinstallation. Par defaut, les DONNEES SONT CONSERVEES (volume Docker et
# sauvegardes) : une reinstallation les retrouve. -PurgeData les detruit, apres
# double confirmation.
param([switch] $PurgeData)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')
try {
    $appRoot = Get-AppRoot
    if (-not (Test-Path -LiteralPath (Join-Path $appRoot '.env'))) { throw 'Application non installee.' }
    $answer = Read-Host 'Desinstaller Chess Calculation Trainer ? Vos donnees seront conservees. (O/N)'
    if ($answer -notmatch '^[oOyY]') { Write-Host 'Annule.'; exit 0 }
    Assert-DockerReady
    # down SANS -v : le volume de donnees n'est jamais supprime ici.
    Invoke-Compose $appRoot @('down') | Out-Null
    $link = Get-ShortcutPath
    if ($link -and (Test-Path -LiteralPath $link)) { Remove-Item -LiteralPath $link -Force }
    $images = @(& docker images --filter 'reference=ghcr.io/*/cct' --format '{{.ID}}' 2>$null)
    foreach ($id in $images) { & docker image rm $id 2>$null | Out-Null }

    if ($PurgeData) {
        Write-Host 'ATTENTION : suppression DEFINITIVE de toutes vos seances et positions.'
        $first = Read-Host 'Taper SUPPRIMER pour continuer'
        $second = Read-Host 'Confirmer une seconde fois : taper SUPPRIMER'
        if ($first -ceq 'SUPPRIMER' -and $second -ceq 'SUPPRIMER') {
            & docker volume rm $script:VolumeName 2>$null | Out-Null
            Remove-Item -LiteralPath (Join-Path $appRoot 'backups') -Recurse -Force -ErrorAction SilentlyContinue
            Write-Host 'Donnees supprimees.'
        } else {
            Write-Host 'Confirmation differente : donnees CONSERVEES.'
        }
    }
    # Le dossier garde les sauvegardes ; le reste est retire.
    Get-ChildItem -LiteralPath $appRoot -Force | Where-Object { $_.Name -ne 'backups' } |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host 'Application desinstallee.'
    if (-not $PurgeData) {
        Write-Host ('Donnees conservees : volume Docker ' + $script:VolumeName + ', sauvegardes dans ' + (Protect-Text (Join-Path $appRoot 'backups')) + '.')
        Write-Host 'Une nouvelle installation les retrouvera.'
    }
    exit 0
} catch {
    Write-Host ('ERREUR : ' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
