#requires -Version 5.1
# Restaure une sauvegarde choisie dans la liste. La base actuelle est elle-meme
# sauvegardee par l'application avant d'etre remplacee ; un fichier invalide est
# refuse et la base actuelle reste en place.
param([string] $File)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')
try {
    $appRoot = Get-AppRoot
    if (-not (Test-Path -LiteralPath (Join-Path $appRoot '.env'))) { throw 'Application non installee.' }
    Assert-DockerReady
    if (-not $File) {
        $backups = @(Get-ChildItem -LiteralPath (Join-Path $appRoot 'backups') -Filter '*.sqlite' -File -ErrorAction SilentlyContinue |
                     Sort-Object LastWriteTime -Descending)
        if ($backups.Count -eq 0) { throw 'Aucune sauvegarde : lancez d abord SAUVEGARDER.cmd.' }
        Write-Host 'Sauvegardes disponibles (la plus recente en premier) :'
        for ($i = 0; $i -lt $backups.Count; $i++) { Write-Host ('  ' + ($i + 1) + '. ' + $backups[$i].Name) }
        $choice = Read-Host 'Numero de la sauvegarde a restaurer (Entree pour annuler)'
        $n = 0
        if (-not [int]::TryParse($choice, [ref]$n) -or $n -lt 1 -or $n -gt $backups.Count) { Write-Host 'Annule.'; exit 0 }
        $File = $backups[$n - 1].FullName
    }
    if (-not (Test-Path -LiteralPath $File -PathType Leaf)) { throw ('Fichier introuvable : ' + (Protect-Text $File)) }
    $confirm = Read-Host 'Les seances posterieures a cette sauvegarde seront retirees (une copie est gardee). Taper OUI pour confirmer'
    if ($confirm -cne 'OUI') { Write-Host 'Annule, rien n a change.'; exit 0 }
    $url = 'http://127.0.0.1:' + (Get-HostPort (Read-EnvFile (Join-Path $appRoot '.env')))
    Invoke-AppRestore $appRoot $File
    if ((Wait-App $url 120) -eq 'down') { Show-AppLogs $appRoot; throw 'L application ne redemarre pas.' }
    $log = (Invoke-Compose $appRoot @('logs', '--no-color', '--since', '5m', 'app') -AllowFailure | Out-String)
    if ($log -match 'base restauree') { Write-Host 'Restauration faite et verifiee.' }
    elseif ($log -match 'restauration refusee') { throw 'Sauvegarde refusee par l application (fichier invalide) : la base actuelle est conservee.' }
    else { Write-Warning 'Restauration non confirmee par le journal : envoyez le rapport de COLLECTER_DIAGNOSTIC.cmd.' }
    exit 0
} catch {
    Write-Host ('ERREUR : ' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
