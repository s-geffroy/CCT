#requires -Version 5.1
# Mise a jour depuis le bundle extrait de la NOUVELLE version :
# sauvegarde verifiee -> nouvelle image (par digest) -> migrations -> sante.
# Echec : retour automatique a l'ancienne image ET a la sauvegarde (une base
# migree n'est pas lisible par l'ancienne version).
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')
try {
    $bundle = Get-BundleRoot $PSScriptRoot
    & (Join-Path $PSScriptRoot 'verify.ps1')
    $manifest = Read-ReleaseManifest (Join-Path $bundle 'release-manifest.json')
    $appRoot = Get-AppRoot
    $envFile = Join-Path $appRoot '.env'
    $values = Read-EnvFile $envFile
    if (-not $values.ContainsKey('IMAGE_REF')) { throw 'Aucune installation existante : double-cliquez INSTALLER.cmd.' }
    $oldRef = $values['IMAGE_REF']
    $newRef = [string]$manifest.image_ref
    if ($oldRef -ceq $newRef) { Write-Host ('Deja a jour (' + $manifest.app_version + ').'); exit 0 }
    $url = 'http://127.0.0.1:' + (Get-HostPort $values)

    Write-Step 'Sauvegarde de vos donnees avant la mise a jour'
    $saved = Invoke-AppBackup $appRoot
    if ($saved.Path) { Write-Host ('  ' + (Protect-Text $saved.Path) + ' (' + $saved.Sessions + ' seance(s))') }
    else { Write-Host '  Aucune donnee pour l instant : rien a sauvegarder.' }

    Write-Step ('Passage a ' + $manifest.app_version)
    $previousManifest = Join-Path $appRoot 'release-manifest.json'
    if (Test-Path -LiteralPath $previousManifest) { Copy-Item -LiteralPath $previousManifest -Destination (Join-Path $appRoot 'previous-release-manifest.json') -Force }
    Copy-BundleFiles $bundle $appRoot
    $values['IMAGE_REF'] = $newRef
    Write-EnvFile $envFile $values
    $pull = Invoke-Compose $appRoot @('pull') -AllowFailure
    $pulled = ($LASTEXITCODE -eq 0)
    if ($pulled) { Invoke-Compose $appRoot @('up', '-d') | Out-Null }
    if ($pulled -and (Wait-App $url 240) -ne 'down') {
        # Raccourci absent (premiere installation interrompue, par exemple) : on le cree.
        $link = Get-ShortcutPath
        if ($link -and -not (Test-Path -LiteralPath $link)) {
            try { New-DesktopShortcut $appRoot } catch { Write-Warning ('Raccourci bureau non cree : ' + $_.Exception.Message) }
        }
        Write-Host ('Mise a jour terminee : ' + $manifest.app_version + '. Sauvegarde precedente conservee.')
        Start-Process $url
        exit 0
    }

    Write-Warning 'La nouvelle version ne demarre pas : retour a la version precedente.'
    if (-not $pulled) { Write-Host (Protect-Text (($pull | Out-String).Trim())) } else { Show-AppLogs $appRoot }
    $values['IMAGE_REF'] = $oldRef
    Write-EnvFile $envFile $values
    if ($saved.Path) { Invoke-AppRestore $appRoot $saved.Path } else { Invoke-Compose $appRoot @('up', '-d') | Out-Null }
    if ((Wait-App $url 180) -eq 'down') {
        throw ('Retour arriere incomplet. Vos donnees sont dans ' + (Protect-Text $saved.Path) +
               ' : envoyez le rapport de COLLECTER_DIAGNOSTIC.cmd avant toute autre action.')
    }
    throw 'Mise a jour annulee : version precedente et donnees d avant la mise a jour remises en place.'
} catch {
    Write-Host ('ERREUR : ' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
