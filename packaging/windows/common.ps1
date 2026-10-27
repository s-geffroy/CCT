#requires -Version 5.1
# Fonctions communes aux scripts Windows. Fichier ASCII uniquement : Windows
# PowerShell 5.1 lit sans BOM en ANSI, un accent y deviendrait illisible.
Set-StrictMode -Version Latest

$script:ProjectName = 'chess-calculation-trainer'
$script:VolumeName = 'chess-calculation-trainer-data'
$script:ImageRefPattern = '^ghcr\.io/[a-z0-9_.-]+/[a-z0-9_.-]+@sha256:[0-9a-f]{64}$'
$script:DockerInstallUrl = 'https://docs.docker.com/desktop/setup/install/windows-install/'

function Get-AppRoot {
    return (Join-Path $env:LOCALAPPDATA 'ChessCalculationTrainer')
}

function Write-Step([string] $Message) {
    Write-Host ('-> ' + $Message)
}

function Test-ImageRef([string] $Ref) {
    return ($null -ne $Ref) -and ($Ref -cmatch $script:ImageRefPattern)
}

function Read-EnvFile([string] $Path) {
    # Fichier KEY=VALUE ; une cle en double est une erreur (configuration ambigue).
    $values = @{}
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $values }
    foreach ($line in (Get-Content -LiteralPath $Path)) {
        $trimmed = $line.Trim()
        if ($trimmed -eq '' -or $trimmed.StartsWith('#')) { continue }
        $index = $trimmed.IndexOf('=')
        if ($index -lt 1) { throw ('Ligne invalide dans ' + $Path + ' : ' + $trimmed) }
        $key = $trimmed.Substring(0, $index).Trim()
        if ($values.ContainsKey($key)) { throw ('Cle en double dans ' + $Path + ' : ' + $key) }
        $values[$key] = $trimmed.Substring($index + 1).Trim()
    }
    return $values
}

function Write-EnvFile([string] $Path, [hashtable] $Values) {
    $order = @('IMAGE_REF', 'HOST_PORT', 'APP_CPUS', 'APP_MEMORY')
    $keys = @($order | Where-Object { $Values.ContainsKey($_) }) + @($Values.Keys | Where-Object { $order -notcontains $_ } | Sort-Object)
    $text = (($keys | ForEach-Object { $_ + '=' + $Values[$_] }) -join "`n") + "`n"
    [System.IO.File]::WriteAllText($Path, $text, (New-Object System.Text.UTF8Encoding($false)))
}

function Get-HostPort([hashtable] $EnvValues) {
    $port = 0
    $raw = if ($EnvValues.ContainsKey('HOST_PORT')) { $EnvValues['HOST_PORT'] } else { '8765' }
    if (-not [int]::TryParse($raw, [ref]$port) -or $port -lt 1024 -or $port -gt 65535) {
        throw 'HOST_PORT doit etre un nombre entre 1024 et 65535 (fichier .env).'
    }
    return $port
}

function Read-ReleaseManifest([string] $Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw ('Manifeste de release absent : ' + $Path) }
    $manifest = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($manifest.schema_version -ne 1) { throw 'Manifeste de release : version de format inconnue.' }
    if ($manifest.target_platform -ne 'linux/amd64') { throw 'Image non compatible : plateforme attendue linux/amd64.' }
    if (-not (Test-ImageRef ([string]$manifest.image_ref))) {
        throw 'Reference d image invalide : un digest immuable (ghcr.io/...@sha256:...) est obligatoire.'
    }
    return $manifest
}

function Protect-Text([string] $Text) {
    # Le nom du compte Windows et le chemin du profil ne quittent pas le PC.
    if ([string]::IsNullOrEmpty($Text)) { return $Text }
    $out = $Text
    if ($env:USERPROFILE) { $out = $out.Replace($env:USERPROFILE, '<profil>') }
    if ($env:USERNAME -and $env:USERNAME.Length -ge 3) { $out = $out.Replace($env:USERNAME, '<utilisateur>') }
    if ($env:COMPUTERNAME -and $env:COMPUTERNAME.Length -ge 3) { $out = $out.Replace($env:COMPUTERNAME, '<poste>') }
    return $out
}

function Resolve-Docker {
    if (Get-Command 'docker' -ErrorAction SilentlyContinue) { return $true }
    # Installation par utilisateur : PATH pas encore a jour dans cette console.
    $candidates = @()
    if ($env:LOCALAPPDATA) { $candidates += (Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe') }
    if ($env:ProgramFiles) { $candidates += (Join-Path $env:ProgramFiles 'Docker\Docker\resources\bin\docker.exe') }
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            $env:PATH = ([System.IO.Path]::GetDirectoryName($candidate) + ';' + $env:PATH)
            return $true
        }
    }
    return $false
}

function Get-DockerState {
    # 'absent' | 'stopped' | 'windows' | 'linux'
    if (-not (Resolve-Docker)) { return 'absent' }
    $ostype = (& docker info --format '{{.OSType}}' 2>$null | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $ostype) { return 'stopped' }
    if ($ostype -ne 'linux') { return 'windows' }
    return 'linux'
}

function Confirm-Action([string] $Question) {
    # Toute installation ou modification du systeme passe par cet accord explicite.
    $answer = Read-Host ($Question + ' (O/N)')
    return ($answer -match '^\s*[oOyY]')
}

# Appels externes isoles (simules dans les tests).
function Invoke-Winget([string[]] $Arguments) { & winget @Arguments; return $LASTEXITCODE }
function Invoke-Wsl([string[]] $Arguments) { & wsl.exe @Arguments 2>$null | Out-Null; return $LASTEXITCODE }
function Invoke-Elevated([string] $FilePath, [string[]] $Arguments) {
    # Fenetre UAC de Windows : l'utilisateur voit et accepte l'elevation.
    $p = Start-Process -FilePath $FilePath -ArgumentList $Arguments -Verb RunAs -Wait -PassThru
    return $p.ExitCode
}

function Get-DockerDesktopExe {
    $candidates = @()
    if ($env:ProgramFiles) { $candidates += (Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe') }
    if ($env:LOCALAPPDATA) { $candidates += (Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\Docker Desktop.exe') }
    foreach ($c in $candidates) { if (Test-Path -LiteralPath $c -PathType Leaf) { return $c } }
    return $null
}

function Wait-DockerLinux([int] $TimeoutSeconds = 240) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if ((Get-DockerState) -eq 'linux') { return $true }
        Start-Sleep -Seconds 3
    }
    return $false
}

function Show-DockerSteps {
    Write-Host ''
    Write-Host 'Installer Docker Desktop vous-meme :'
    Write-Host ('  1. Ouvrir ' + $script:DockerInstallUrl + ' et telecharger "Docker Desktop for Windows - x86_64".')
    Write-Host '  2. Lancer l installateur ; garder l option "Use WSL 2 instead of Hyper-V" cochee.'
    Write-Host '  3. Redemarrer Windows si l installateur le demande.'
    Write-Host '  4. Lancer Docker Desktop, lire et accepter ses conditions d utilisation, attendre "Engine running".'
    Write-Host '  5. Relancer INSTALLER.cmd.'
}

function Install-DockerDesktop {
    # $true si Docker Desktop vient d'etre installe ; $false sinon (gestes affiches).
    Write-Host 'Docker Desktop n est pas installe. C est le seul logiciel necessaire (gratuit pour un usage personnel ;'
    Write-Host 'ses conditions de licence sont a lire et accepter par vous au premier lancement).'
    if (Get-Command 'winget' -ErrorAction SilentlyContinue) {
        if (Confirm-Action 'Installer Docker Desktop maintenant (installateur officiel de Docker via winget, environ 600 Mo) ?') {
            Write-Step 'Installation de Docker Desktop (Windows peut demander une autorisation)'
            # Aucun --accept-*-agreements : les conditions restent acceptees par l'utilisateur.
            $code = Invoke-Winget @('install', '--exact', '--id', 'Docker.DockerDesktop', '--source', 'winget')
            if ($code -eq 0 -and (Get-DockerDesktopExe)) {
                Write-Host 'Docker Desktop est installe. Si Windows demande un redemarrage, redemarrez puis relancez INSTALLER.cmd.'
                return $true
            }
            Write-Warning ('L installation par winget n a pas abouti (code ' + $code + ').')
        }
    }
    Show-DockerSteps
    Start-Process $script:DockerInstallUrl
    return $false
}

function Resolve-DockerPrerequisite([switch] $Interactive) {
    # Amene Docker a l etat "pret, conteneurs Linux", ou explique quoi faire.
    # Sans -Interactive (ouvrir, arreter, sauvegarder) : on demarre Docker
    # Desktop s'il est arrete, mais on n'installe ni ne reconfigure rien.
    for ($round = 0; $round -lt 3; $round++) {
        switch (Get-DockerState) {
            'linux' { return }
            'absent' {
                if ($Interactive -and (Install-DockerDesktop)) { continue }
                if (-not $Interactive) { Write-Host ('Page officielle : ' + $script:DockerInstallUrl) }
                throw 'Docker Desktop absent : rien n a ete installe. Installez-le (gestes ci-dessus), demarrez-le, puis relancez.'
            }
            'stopped' {
                $exe = Get-DockerDesktopExe
                if (-not $exe) { throw 'Docker ne repond pas : demarrez Docker Desktop (menu Demarrer), attendez "Engine running", puis relancez.' }
                Write-Step 'Demarrage de Docker Desktop (jusqu a 4 minutes la premiere fois)'
                Write-Host '   Si une fenetre de conditions d utilisation s ouvre, lisez-la et acceptez-la pour continuer.'
                Start-Process -FilePath $exe
                if (Wait-DockerLinux 240) { continue }
                throw 'Docker Desktop ne repond toujours pas : ouvrez-le, attendez "Engine running" (ou redemarrez Windows), puis relancez.'
            }
            'windows' {
                $cli = if ($env:ProgramFiles) { Join-Path $env:ProgramFiles 'Docker\Docker\DockerCli.exe' } else { $null }
                if ($Interactive -and $cli -and (Test-Path -LiteralPath $cli) -and
                    (Confirm-Action 'Docker Desktop execute des conteneurs Windows. Passer aux conteneurs Linux (necessaire) ?')) {
                    & $cli -SwitchLinuxEngine
                    if (Wait-DockerLinux 180) { continue }
                }
                throw 'Docker Desktop execute des conteneurs Windows : dans son menu, choisissez "Switch to Linux containers", puis relancez.'
            }
        }
    }
    throw 'Docker n est pas pret apres plusieurs tentatives : envoyez le rapport de COLLECTER_DIAGNOSTIC.cmd.'
}

function Resolve-WslPrerequisite {
    # 'ok' | 'reboot' (installe, redemarrage requis) ; leve une erreur avec les gestes sinon.
    if (-not (Get-Command 'wsl.exe' -ErrorAction SilentlyContinue)) {
        Write-Host 'WSL 2 (sous-systeme Linux de Windows, utilise par Docker Desktop) n est pas installe.'
        if (Confirm-Action 'L installer maintenant (commande Microsoft "wsl --install", autorisation administrateur, puis redemarrage) ?') {
            $code = Invoke-Elevated 'wsl.exe' @('--install', '--no-distribution')
            if ($code -eq 0) { return 'reboot' }
            Write-Warning ('wsl --install a echoue (code ' + $code + ').')
        }
        throw ('Installez WSL : menu Demarrer, "Terminal" en tant qu administrateur, tapez "wsl --install --no-distribution", ' +
               'redemarrez, puis relancez INSTALLER.cmd. Aide : https://learn.microsoft.com/windows/wsl/install')
    }
    if ((Invoke-Wsl @('--version')) -eq 0) { return 'ok' }
    Write-Host 'WSL est trop ancien (version integree a Windows) ou inactif.'
    if (Confirm-Action 'Le mettre a jour maintenant (commande Microsoft "wsl --update") ?') {
        if ((Invoke-Wsl @('--update')) -eq 0 -or (Invoke-Elevated 'wsl.exe' @('--update')) -eq 0) {
            if ((Invoke-Wsl @('--version')) -eq 0) { return 'ok' }
            return 'reboot'
        }
    }
    throw 'Mettez WSL a jour : Terminal, tapez "wsl --update", puis relancez INSTALLER.cmd.'
}

function Assert-DockerReady {
    Resolve-DockerPrerequisite
}

function Invoke-Compose([string] $AppRoot, [string[]] $Arguments, [switch] $AllowFailure) {
    $envFile = Join-Path $AppRoot '.env'
    $composeFile = Join-Path $AppRoot 'compose.yaml'
    $all = @('compose', '--project-name', $script:ProjectName, '--project-directory', $AppRoot,
             '--env-file', $envFile, '-f', $composeFile) + $Arguments
    $output = & docker @all 2>&1
    $code = $LASTEXITCODE
    if ($code -ne 0 -and -not $AllowFailure) {
        throw ('docker compose ' + ($Arguments -join ' ') + ' a echoue : ' + (($output | Out-String).Trim()))
    }
    return $output
}

function Test-PortFree([int] $Port) {
    # Vrai si rien n'ecoute deja sur 127.0.0.1:Port.
    $listener = $null
    try {
        $listener = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, $Port)
        $listener.Start()
        return $true
    } catch {
        return $false
    } finally {
        if ($null -ne $listener) { $listener.Stop() }
    }
}

function Get-Health([string] $BaseUrl) {
    # 'ready' (moteur pret) | 'live' (application OK, moteur indisponible) | 'down'
    try {
        $live = Invoke-WebRequest -Uri ($BaseUrl + '/api/v1/health/live') -UseBasicParsing -TimeoutSec 3
        if ($live.StatusCode -ne 200) { return 'down' }
    } catch { return 'down' }
    try {
        $ready = Invoke-WebRequest -Uri ($BaseUrl + '/api/v1/health/ready') -UseBasicParsing -TimeoutSec 5
        if ($ready.StatusCode -eq 200) { return 'ready' }
    } catch { return 'live' }  # /ready en 503 : moteur indisponible, application vivante
    return 'live'
}

function Wait-App([string] $BaseUrl, [int] $TimeoutSeconds = 120) {
    # Attend 'ready' ; se contente de 'live' passe la moitie du delai (moteur lent ou absent).
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $state = 'down'
    while ((Get-Date) -lt $deadline) {
        $state = Get-Health $BaseUrl
        if ($state -eq 'ready') { return $state }
        Start-Sleep -Seconds 2
    }
    return $state
}

function Show-AppLogs([string] $AppRoot) {
    Write-Host 'Dernieres lignes du journal de l application :'
    Invoke-Compose $AppRoot @('logs', '--no-color', '--tail=40', 'app') -AllowFailure | ForEach-Object { Write-Host (Protect-Text ([string]$_)) }
}

function Test-AppRunning([string] $AppRoot) {
    $ids = Invoke-Compose $AppRoot @('ps', '--status', 'running', '-q', 'app') -AllowFailure
    return [bool](($ids | Out-String).Trim())
}

function Invoke-AppBackup([string] $AppRoot) {
    # Sauvegarde coherente faite DANS le conteneur (API SQLite), verifiee, puis copiee sur le PC.
    if (-not (Test-AppRunning $AppRoot)) { Invoke-Compose $AppRoot @('up', '-d') | Out-Null }
    $raw = (Invoke-Compose $AppRoot @('exec', '-T', 'app', 'python', '-m', 'app.backup', 'create') | Out-String).Trim()
    $line = @($raw -split "`r?`n" | Where-Object { $_.StartsWith('{') }) | Select-Object -Last 1
    if (-not $line) { throw ('Sauvegarde : reponse inattendue : ' + $raw) }
    $result = $line | ConvertFrom-Json
    if (-not $result.ok) { throw ('Sauvegarde refusee : ' + $result.reason) }
    $backups = Join-Path $AppRoot 'backups'
    if (-not (Test-Path -LiteralPath $backups)) { New-Item -ItemType Directory -Path $backups -Force | Out-Null }
    $name = [System.IO.Path]::GetFileName([string]$result.path)
    Invoke-Compose $AppRoot @('cp', ('app:' + $result.path), (Join-Path $backups $name)) | Out-Null
    return [pscustomobject]@{ Path = (Join-Path $backups $name); Sessions = $result.sessions; Schema = $result.schema_version }
}

function Invoke-AppRestore([string] $AppRoot, [string] $File) {
    # Depot du fichier, application arretee ; l'application le verifie et le prend au demarrage.
    Invoke-Compose $AppRoot @('stop') | Out-Null
    Invoke-Compose $AppRoot @('cp', $File, 'app:/data/restore/incoming.sqlite') | Out-Null
    Invoke-Compose $AppRoot @('up', '-d') | Out-Null
}

function New-DesktopShortcut([string] $AppRoot) {
    $desktop = [Environment]::GetFolderPath('Desktop')
    if (-not $desktop) { return }
    $linkPath = Join-Path $desktop 'Chess Calculation Trainer.lnk'
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($linkPath)
    $shortcut.TargetPath = (Join-Path $AppRoot 'OUVRIR.cmd')
    $shortcut.WorkingDirectory = $AppRoot
    $shortcut.Description = 'Ouvrir Chess Calculation Trainer'
    $shortcut.Save()
}

function Get-ShortcutPath {
    $desktop = [Environment]::GetFolderPath('Desktop')
    if (-not $desktop) { return $null }
    return (Join-Path $desktop 'Chess Calculation Trainer.lnk')
}

function Copy-BundleFiles([string] $SourceRoot, [string] $AppRoot) {
    # Recopie le bundle extrait dans le dossier stable (jamais execute depuis Telechargements).
    # Relance depuis le dossier installe : rien a copier (et pas de copie sur soi-meme).
    if ([System.IO.Path]::GetFullPath($SourceRoot).TrimEnd('\') -ieq [System.IO.Path]::GetFullPath($AppRoot).TrimEnd('\')) { return }
    $scriptsDest = Join-Path $AppRoot 'scripts\windows'
    foreach ($dir in @($AppRoot, $scriptsDest)) {
        if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    }
    Get-ChildItem -LiteralPath $SourceRoot -File | Where-Object { $_.Extension -in @('.cmd', '.md', '.json', '.yaml', '.txt') -or $_.Name -eq 'LICENSE' } |
        Copy-Item -Destination $AppRoot -Force
    Get-ChildItem -LiteralPath (Join-Path $SourceRoot 'scripts\windows') -Filter '*.ps1' -File |
        Copy-Item -Destination $scriptsDest -Force
}

function Get-BundleRoot([string] $ScriptRoot) {
    return (Resolve-Path (Join-Path $ScriptRoot '..\..')).Path
}
