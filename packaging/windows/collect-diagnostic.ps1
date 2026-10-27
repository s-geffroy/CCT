#requires -Version 5.1
# Rapport de diagnostic (W12) : versions, etat, sante, journal. Ecrit sur le
# Bureau un fichier texte a transmettre au projet. Aucun secret ; nom du compte,
# du poste et chemin du profil masques. Ne s'arrete jamais sur une section en echec.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Continue'
. (Join-Path $PSScriptRoot 'common.ps1')

$appRoot = Get-AppRoot
$lines = New-Object System.Collections.Generic.List[string]
function Add-Section([string] $Title, [scriptblock] $Body) {
    $lines.Add('')
    $lines.Add('## ' + $Title)
    try { foreach ($item in @(& $Body)) { $lines.Add((Protect-Text ([string]$item))) } }
    catch { $lines.Add('(indisponible : ' + (Protect-Text $_.Exception.Message) + ')') }
}

$lines.Add('# Rapport Chess Calculation Trainer - ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz'))
Add-Section 'Windows' {
    $os = Get-CimInstance Win32_OperatingSystem
    $cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
    $ram = (Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory
    $os.Caption + ' ' + $os.Version + ' (build ' + $os.BuildNumber + '), ' + $os.OSArchitecture
    'Processeur : ' + $cpu.Name + ' (' + $cpu.NumberOfLogicalProcessors + ' coeurs logiques)'
    'Memoire : ' + [math]::Round($ram / 1GB, 1) + ' Go ; langue : ' + (Get-Culture).Name
    'PowerShell : ' + $PSVersionTable.PSVersion.ToString()
}
Add-Section 'WSL' { (& wsl.exe --version 2>&1 | Out-String).Replace([string][char]0, '').Trim() }
Add-Section 'Docker' {
    if (-not (Resolve-Docker)) { 'Docker absent' } else {
        'Etat : ' + (Get-DockerState)
        (& docker version --format 'Client {{.Client.Version}} / Serveur {{.Server.Version}} ({{.Server.Os}}/{{.Server.Arch}})' 2>&1 | Out-String).Trim()
        (& docker compose version 2>&1 | Out-String).Trim()
        (& docker info --format 'CPUs {{.NCPU}} ; memoire {{.MemTotal}} ; noyau {{.KernelVersion}}' 2>&1 | Out-String).Trim()
    }
}
Add-Section 'Installation' {
    'Dossier : ' + $appRoot + ' (existe : ' + (Test-Path -LiteralPath $appRoot) + ')'
    $manifest = Join-Path $appRoot 'release-manifest.json'
    if (Test-Path -LiteralPath $manifest) { Get-Content -LiteralPath $manifest -Raw }
    $envValues = Read-EnvFile (Join-Path $appRoot '.env')
    foreach ($k in ($envValues.Keys | Sort-Object)) { $k + '=' + $envValues[$k] }
    'Sauvegardes : ' + @(Get-ChildItem -LiteralPath (Join-Path $appRoot 'backups') -File -ErrorAction SilentlyContinue).Count
    'Raccourci bureau : ' + [bool]((Get-ShortcutPath) -and (Test-Path -LiteralPath (Get-ShortcutPath)))
}
Add-Section 'Conteneur' {
    (Invoke-Compose $appRoot @('ps', '--all') -AllowFailure | Out-String).Trim()
    (& docker inspect --format 'Image {{.Image}} ; demarre {{.State.StartedAt}} ; sante {{if .State.Health}}{{.State.Health.Status}}{{end}}' 'chess-calculation-trainer-app-1' 2>&1 | Out-String).Trim()
    (& docker volume inspect $script:VolumeName --format 'Volume {{.Name}} cree {{.CreatedAt}}' 2>&1 | Out-String).Trim()
}
Add-Section 'Sante et version' {
    $port = Get-HostPort (Read-EnvFile (Join-Path $appRoot '.env'))
    foreach ($path in @('/api/v1/health/live', '/api/v1/health/ready', '/api/v1/meta')) {
        try {
            $r = Invoke-WebRequest -Uri ('http://127.0.0.1:' + $port + $path) -UseBasicParsing -TimeoutSec 5
            $path + ' -> ' + $r.StatusCode + ' ' + $r.Content
        } catch { $path + ' -> ' + $_.Exception.Message }
    }
}
Add-Section 'Journal (300 dernieres lignes)' { Invoke-Compose $appRoot @('logs', '--no-color', '--tail=300', 'app') -AllowFailure }

$name = 'cct-rapport-' + (Get-Date -Format 'yyyyMMdd-HHmm') + '.txt'
$desktop = [Environment]::GetFolderPath('Desktop')
if (-not $desktop) { $desktop = $appRoot }
$target = Join-Path $desktop $name
[System.IO.File]::WriteAllText($target, (($lines -join "`r`n") + "`r`n"), (New-Object System.Text.UTF8Encoding($false)))
Write-Host ('Rapport ecrit sur le Bureau : ' + $name)
Write-Host 'Deposez-le dans le dossier validation/ de la branche validation-windows sur GitHub (voir VALIDATION_WINDOWS.md).'
exit 0
