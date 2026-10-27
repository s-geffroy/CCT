#requires -Version 5.1
# Pre-requis de l'installation. Ce qui manque est PROPOSE (accord explicite,
# fenetre UAC de Windows pour les droits administrateur) ou explique pas a pas.
# -Light (ouvrir, arreter, sauvegarder) : seulement Docker, demarre s'il le faut.
param([switch] $Light)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')

$MinBuild = 22631          # Windows 11 23H2 : seuil unique (decisions B1)

if ($Light) { Assert-DockerReady; return }

if ($env:OS -ne 'Windows_NT') { throw 'Windows est requis.' }
$os = Get-CimInstance -ClassName Win32_OperatingSystem
if ([int]$os.BuildNumber -lt $MinBuild) {
    throw ('Windows 11 version 23H2 ou plus recente est requise (build actuel : ' + $os.BuildNumber + '). ' +
           'Parametres > Windows Update > Rechercher des mises a jour, installer, redemarrer, puis relancer INSTALLER.cmd. ' +
           'Un PC sous Windows 10 doit d abord passer a Windows 11 (s il est compatible).')
}
$arch = (Get-CimInstance -ClassName Win32_Processor | Select-Object -First 1).Architecture
if ($arch -ne 9) { throw 'Ce PC a un processeur ARM : non pris en charge en V1 (un PC Intel ou AMD 64 bits est requis).' }
$ram = [int64](Get-CimInstance -ClassName Win32_ComputerSystem).TotalPhysicalMemory
$cores = [int](Get-CimInstance -ClassName Win32_ComputerSystem).NumberOfLogicalProcessors
$resources = Get-ResourceProfile $ram $cores   # refuse sous 4 Go (minimum de Docker Desktop)
if ($resources.Light) {
    Write-Warning ('Memoire limitee (' + [math]::Round($ram / 1GB, 1) + ' Go) : configuration allegee, analyses plus lentes. ' +
                   'Le moteur calcule pendant votre reflexion ; fermez les applications lourdes.')
}
$drive = ([System.IO.Path]::GetPathRoot($env:LOCALAPPDATA)).TrimEnd('\')
$disk = Get-CimInstance Win32_LogicalDisk -Filter ("DeviceID='" + $drive + "'")
if ($null -ne $disk -and [int64]$disk.FreeSpace -lt 5GB) {
    throw ('Moins de 5 Go libres sur ' + $drive + ' : liberez de la place (Parametres > Systeme > Stockage), puis relancez.')
}

if ((Resolve-WslPrerequisite) -eq 'reboot') {
    throw 'WSL vient d etre installe ou mis a jour : redemarrez Windows, puis relancez INSTALLER.cmd (l installation reprendra ici).'
}
Resolve-DockerPrerequisite -Interactive
if ((Invoke-Native 'docker' @('compose', 'version')).ExitCode -ne 0) { throw 'Docker Compose v2 indisponible : mettez Docker Desktop a jour (son menu > Check for updates).' }
Write-Host 'Pre-requis verifies : Windows 11 x64, memoire, disque, WSL 2, Docker Desktop (conteneurs Linux), Compose.'
