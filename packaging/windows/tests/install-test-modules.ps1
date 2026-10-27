#requires -Version 5.1
# Installe Pester et PSScriptAnalyzer (versions et empreintes figees) sans
# passer par la PowerShell Gallery, indisponible le 27/10/2026 depuis le VPS
# comme depuis les runners GitHub. Sources officielles : nuget.org (Pester) et
# la release GitHub de Microsoft (PSScriptAnalyzer). Toute empreinte differente
# arrete l'installation.
param([Parameter(Mandatory = $true)] [string] $Destination)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$modules = @(
    @{ Name = 'Pester'; Version = '5.7.1'; Root = 'tools'
       Url = 'https://api.nuget.org/v3-flatcontainer/pester/5.7.1/pester.5.7.1.nupkg'
       Sha256 = '3c6dad5fb143faf19709dfb28c31c873989944705a087e160e23b7ce462e37a1' },
    @{ Name = 'PSScriptAnalyzer'; Version = '1.25.0'; Root = ''
       Url = 'https://github.com/PowerShell/PSScriptAnalyzer/releases/download/1.25.0/PSScriptAnalyzer.1.25.0.nupkg'
       Sha256 = '14e634c828eb98efb9f40b2918ba90f139ed5eccdf663a2a747736d996995d60' }
)
$work = Join-Path ([System.IO.Path]::GetTempPath()) ('cct-modules-' + [guid]::NewGuid())
New-Item -ItemType Directory -Path $work -Force | Out-Null
try {
    foreach ($m in $modules) {
        $archive = Join-Path $work ($m.Name + '.zip')
        Invoke-WebRequest -Uri $m.Url -OutFile $archive -UseBasicParsing
        $hash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($hash -ne $m.Sha256) { throw ($m.Name + ' : empreinte inattendue ' + $hash) }
        $extracted = Join-Path $work $m.Name
        Expand-Archive -LiteralPath $archive -DestinationPath $extracted -Force
        $source = if ($m.Root) { Join-Path $extracted $m.Root } else { $extracted }
        $target = Join-Path (Join-Path $Destination $m.Name) $m.Version
        New-Item -ItemType Directory -Path $target -Force | Out-Null
        Copy-Item -Path (Join-Path $source '*') -Destination $target -Recurse -Force
        if (-not (Test-Path -LiteralPath (Join-Path $target ($m.Name + '.psd1')))) { throw ($m.Name + ' : manifeste absent apres extraction') }
        Write-Host ($m.Name + ' ' + $m.Version + ' installe (sha256 verifie)')
    }
} finally {
    Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
}
