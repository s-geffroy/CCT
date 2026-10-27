#requires -Version 5.1
# Installation (ou reinstallation de la MEME version) depuis le bundle extrait.
# Une autre version deja installee : refus, renvoi vers METTRE_A_JOUR.cmd.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')

try {
    $bundle = Get-BundleRoot $PSScriptRoot
    & (Join-Path $PSScriptRoot 'verify.ps1')
    $manifest = Read-ReleaseManifest (Join-Path $bundle 'release-manifest.json')
    $imageRef = [string]$manifest.image_ref
    $appRoot = Get-AppRoot
    $envFile = Join-Path $appRoot '.env'

    $existing = Read-EnvFile $envFile
    if ($existing.ContainsKey('IMAGE_REF') -and $existing['IMAGE_REF'] -cne $imageRef) {
        throw ('Une autre version est deja installee. Pour changer de version, double-cliquez METTRE_A_JOUR.cmd ' +
               'dans le dossier de la NOUVELLE version : vos donnees seront sauvegardees avant.')
    }

    Write-Step ('Installation de ' + $manifest.app_version + ' dans ' + (Protect-Text $appRoot))
    Copy-BundleFiles $bundle $appRoot
    if (-not $existing.ContainsKey('IMAGE_REF')) {
        $computer = Get-CimInstance -ClassName Win32_ComputerSystem
        $resources = Get-ResourceProfile ([int64]$computer.TotalPhysicalMemory) ([int]$computer.NumberOfLogicalProcessors)
        Write-EnvFile $envFile @{ IMAGE_REF = $imageRef; HOST_PORT = [string]$manifest.host_port_default;
                                APP_CPUS = $resources.APP_CPUS; APP_MEMORY = $resources.APP_MEMORY;
                                ENGINE_THREADS = $resources.ENGINE_THREADS; ENGINE_HASH_MB = $resources.ENGINE_HASH_MB }
    }
    $port = Get-HostPort (Read-EnvFile $envFile)
    $url = 'http://127.0.0.1:' + $port

    # Port deja pris par un autre programme (pas par nous) : message, aucune fermeture forcee.
    if (-not (Test-AppRunning $appRoot) -and -not (Test-PortFree $port)) {
        throw ('Le port ' + $port + ' est deja utilise par un autre programme. Changez HOST_PORT dans ' +
               (Protect-Text $envFile) + ' (par exemple 8766), puis relancez INSTALLER.cmd.')
    }

    Invoke-Compose $appRoot @('config', '--quiet') | Out-Null
    Write-Step 'Telechargement de l image (la premiere fois : quelques minutes)'
    $pull = Invoke-Compose $appRoot @('pull') -AllowFailure
    if ($LASTEXITCODE -ne 0) {
        Write-Host (Protect-Text (($pull | Out-String).Trim()))
        throw ('Telechargement de l image impossible. Verifiez la connexion Internet. Si le message parle de ' +
               '"denied" ou "unauthorized", l image n est pas encore publique : signalez-le au projet.')
    }
    Write-Step 'Demarrage'
    Invoke-Compose $appRoot @('up', '-d') | Out-Null

    $state = Wait-App $url 180
    if ($state -eq 'down') {
        Show-AppLogs $appRoot
        throw 'L application ne repond pas. Aucune reussite annoncee : envoyez le rapport de COLLECTER_DIAGNOSTIC.cmd.'
    }
    try { New-DesktopShortcut $appRoot } catch { Write-Warning ('Raccourci bureau non cree : ' + $_.Exception.Message) }
    if ($state -eq 'live') {
        Write-Warning ('Application installee, mais le moteur Stockfish est indisponible : les seances de calcul ' +
                       'fonctionnent, les analyses attendront. Envoyez le rapport de COLLECTER_DIAGNOSTIC.cmd.')
    }
    Start-Process $url
    Write-Host ('Application prete : ' + $url)
    Write-Host 'Raccourci "Chess Calculation Trainer" sur le Bureau ; donnees dans le volume Docker chess-calculation-trainer-data.'
    exit 0
} catch {
    Write-Host ''
    Write-Host ('ERREUR : ' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
