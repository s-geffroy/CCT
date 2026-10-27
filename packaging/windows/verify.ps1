#requires -Version 5.1
# Pre-requis de l'installation. -Light : seulement "Docker joignable en mode
# Linux" (demarrer/arreter n'a pas besoin de recontroler la RAM ou le disque).
param([switch] $Light)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')

$MinBuild = 22631          # Windows 11 23H2 : seuil unique (decisions B1)
$MinRamBytes = 7.5 * 1GB   # un PC "8 Go" affiche ~7,7 Gio utilisables (B2)

if (-not $Light) {
    if ($env:OS -ne 'Windows_NT') { throw 'Windows est requis.' }
    $os = Get-CimInstance -ClassName Win32_OperatingSystem
    if ([int]$os.BuildNumber -lt $MinBuild) {
        throw ('Windows 11 x64 version 23H2 ou plus recente requise. Build actuel : ' + $os.BuildNumber)
    }
    $arch = (Get-CimInstance -ClassName Win32_Processor | Select-Object -First 1).Architecture
    if ($arch -ne 9) { throw 'Processeur ARM non pris en charge en V1 : un PC x64 (Intel ou AMD) est requis.' }
    $ram = [int64](Get-CimInstance -ClassName Win32_ComputerSystem).TotalPhysicalMemory
    if ($ram -lt $MinRamBytes) { throw ('Au moins 8 Go de memoire sont requis (detecte : ' + [math]::Round($ram / 1GB, 1) + ' Go).') }
    if ($ram -lt 8GB) { Write-Warning 'Memoire juste suffisante : fermez les applications lourdes pendant les analyses.' }
    if (-not (Get-Command 'wsl.exe' -ErrorAction SilentlyContinue)) {
        throw ('WSL n est pas installe. Suivez la page officielle de Docker Desktop : ' + $script:DockerInstallUrl)
    }
    & wsl.exe --version 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'WSL est trop ancien ou inactif : executez "wsl --update" dans un terminal, puis relancez.' }
}

Assert-DockerReady
& docker compose version 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Docker Compose v2 est indisponible : mettez Docker Desktop a jour.' }

if (-not $Light) {
    $drive = ([System.IO.Path]::GetPathRoot($env:LOCALAPPDATA)).TrimEnd('\')
    $disk = Get-CimInstance Win32_LogicalDisk -Filter ("DeviceID='" + $drive + "'")
    if ($null -ne $disk -and [int64]$disk.FreeSpace -lt 5GB) { throw 'Moins de 5 Go libres sur le disque systeme.' }
    Write-Host 'Pre-requis verifies : Windows 11 x64, WSL 2, Docker Desktop (conteneurs Linux), Compose, memoire, disque.'
}
