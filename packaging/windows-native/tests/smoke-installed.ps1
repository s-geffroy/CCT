#requires -Version 5.1
# Smoke test de l'installateur natif sur un vrai Windows (runner CI) :
# installation silencieuse, demarrage, interface servie, Stockfish telecharge
# et verifie, analyse reelle, instance unique, arret propre, mise a jour par
# reinstallation, desinstallation qui garde les donnees.
#
#   .\smoke-installed.ps1 -Setup dist\ChessCalculationTrainer-Setup-v0.2.0.exe
param([Parameter(Mandatory = $true)] [string] $Setup)
$ErrorActionPreference = 'Stop'
. (Join-Path (Split-Path -Parent $PSScriptRoot) 'native.ps1')

$installDir = Join-Path $env:LOCALAPPDATA 'Programs\ChessCalculationTrainer'
$dataDir = Join-Path $env:LOCALAPPDATA 'ChessCalculationTrainer\data'
$python = Join-Path $installDir 'python\python.exe'
$pythonw = Join-Path $installDir 'python\pythonw.exe'

function Step([string] $Text) { Write-Host ('==> ' + $Text) }

function Install-App([string] $Installer) {
    $p = Start-Process -FilePath $Installer -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', ('/LOG=' + (Join-Path $env:TEMP 'cct-setup.log')) -Wait -PassThru
    if ($p.ExitCode -ne 0) { Get-Content (Join-Path $env:TEMP 'cct-setup.log') -Tail 40; throw ('Installation en echec : code ' + $p.ExitCode) }
    if (-not (Test-Path -LiteralPath $pythonw)) { throw 'pythonw.exe absent apres installation' }
}

function Start-App {
    # Comme le raccourci du menu Demarrer : pythonw, sans console.
    Start-Process -FilePath $pythonw -ArgumentList '-m', 'app.desktop', '--no-browser' -WorkingDirectory $installDir | Out-Null
    $info = Wait-Condition {
        $file = Join-Path $dataDir 'instance.json'
        if (-not (Test-Path -LiteralPath $file)) { return $null }
        $i = Get-Content -LiteralPath $file -Raw | ConvertFrom-Json
        try {
            Invoke-RestMethod -Uri ('http://127.0.0.1:' + $i.port + '/api/v1/health/live') -TimeoutSec 3 | Out-Null
            return $i
        } catch { return $null }
    } 120 'demarrage de l application'
    return $info
}

function Invoke-Api([string] $Method, [string] $Path, $Body = $null) {
    $uri = $script:base + $Path
    if ($null -eq $Body) { return Invoke-RestMethod -Method $Method -Uri $uri -TimeoutSec 30 }
    return Invoke-RestMethod -Method $Method -Uri $uri -TimeoutSec 30 -ContentType 'application/json' -Body ($Body | ConvertTo-Json -Compress)
}

function Stop-App {
    & $python -m app.desktop --stop
    if ($LASTEXITCODE -ne 0) { throw ('Arret en echec : code ' + $LASTEXITCODE) }
    if (Test-Path -LiteralPath (Join-Path $dataDir 'instance.json')) { throw 'instance.json toujours present apres l arret' }
}

try {
    Step 'Installation silencieuse'
    Install-App $Setup

    Step 'Demarrage (pythonw, comme le raccourci)'
    $info = Start-App
    $script:base = 'http://127.0.0.1:' + $info.port
    Write-Host ('   port ' + $info.port)
    $page = Invoke-WebRequest -Uri ($script:base + '/') -UseBasicParsing -TimeoutSec 10
    if ($page.Content -notmatch '<div id="root"') { throw 'Interface non servie' }
    $version = (Invoke-Api GET '/api/v1/health/live')
    Write-Host ('   ' + ($version | ConvertTo-Json -Compress))

    Step 'Moteur : existant ou telechargement de la release officielle'
    $engine = Invoke-Api GET '/api/v1/engine'
    if ($engine.status -ne 'ready') {
        if ($null -eq $engine.offer) { throw 'Aucun telechargement propose pour cette plateforme' }
        Invoke-Api POST '/api/v1/engine/download' @{} | Out-Null
        $engine = Wait-Condition {
            $e = Invoke-Api GET '/api/v1/engine'
            if ($e.download.status -eq 'failed') { throw ('Telechargement en echec : ' + $e.download.error) }
            if ($e.download.status -eq 'done') { return $e }
            return $null
        } 600 'telechargement de Stockfish'
    }
    if ($engine.status -ne 'ready') { throw ('Moteur indisponible : ' + $engine.error) }
    Write-Host ('   ' + $engine.current.name + ' (' + $engine.current.source + ') ' + $engine.current.path)
    if ($engine.current.name -notmatch '^Stockfish') { throw 'Moteur inattendu' }
    Wait-Condition { try { Invoke-Api GET '/api/v1/health/ready' } catch { $null } } 60 'health/ready' | Out-Null

    Step 'Analyse reelle (profondeur 12)'
    $position = Invoke-Api POST '/api/v1/positions' @{ source = 'fen'; fen = 'r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3' }
    $job = Invoke-Api POST '/api/v1/analysis-jobs' @{ position_id = $position.id; target_depth = 12; multipv_max = 3; budget_s = 60 }
    $final = Wait-Condition {
        $j = Invoke-Api GET ('/api/v1/analysis-jobs/' + $job.id)
        if ($j.state -in @('complete_depth', 'budget_exhausted', 'failed', 'interrupted', 'incomplete')) { return $j }
        return $null
    } 180 'analyse'
    if ($final.state -ne 'complete_depth') { throw ('Analyse : etat ' + $final.state) }
    Write-Host ('   ' + $final.state)

    Step 'Second lancement : rejoint l instance existante'
    $p = Start-Process -FilePath $python -ArgumentList '-m', 'app.desktop', '--no-browser' -Wait -PassThru -WindowStyle Hidden
    if ($p.ExitCode -ne 0) { throw ('Second lancement : code ' + $p.ExitCode) }
    $again = Get-Content -LiteralPath (Join-Path $dataDir 'instance.json') -Raw | ConvertFrom-Json
    if ($again.pid -ne $info.pid) { throw 'Un second serveur a demarre' }

    Step 'Mise a jour (reinstallation par-dessus, application ouverte)'
    Install-App $Setup
    if (Test-Path -LiteralPath (Join-Path $dataDir 'instance.json')) { throw 'L installateur n a pas arrete l application' }
    $info = Start-App
    $script:base = 'http://127.0.0.1:' + $info.port
    $engine = Invoke-Api GET '/api/v1/engine'
    if ($engine.status -ne 'ready' -or ($engine.current.source -notin @('telecharge', 'path', 'emplacement'))) {
        throw ('Moteur non retrouve apres mise a jour : ' + ($engine | ConvertTo-Json -Compress -Depth 4))
    }
    $kept = Invoke-Api GET ('/api/v1/analysis-jobs/' + $job.id)
    if ($kept.state -ne 'complete_depth') { throw 'Analyse perdue apres mise a jour' }

    Step 'Arret propre'
    Stop-App

    Step 'Desinstallation : programme supprime, donnees conservees'
    $uninstaller = Join-Path $installDir 'unins000.exe'
    $p = Start-Process -FilePath $uninstaller -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART' -Wait -PassThru
    if ($p.ExitCode -ne 0) { throw ('Desinstallation en echec : code ' + $p.ExitCode) }
    Wait-Condition { -not (Test-Path -LiteralPath (Join-Path $installDir 'python')) } 60 'suppression du programme' | Out-Null
    if (-not (Test-Path -LiteralPath (Join-Path $dataDir 'app.sqlite'))) { throw 'Donnees supprimees par la desinstallation' }
    Write-Host 'OK : installateur natif valide sur ce Windows'
} catch {
    Write-Host ('ECHEC : ' + $_)
    $log = Join-Path $dataDir 'logs\cct.log'
    if (Test-Path -LiteralPath $log) { Write-Host '--- cct.log ---'; Get-Content -LiteralPath $log -Tail 80 }
    exit 1
}
