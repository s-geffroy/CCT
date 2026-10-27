#requires -Version 5.1
# Construit l'installateur Windows natif (sans Docker) :
#   payload\python\         Python embarque officiel (empreinte verifiee)
#   payload\site-packages\  dependances verrouillees (uv.lock), wheels win_amd64 avec empreintes
#   payload\backend\        paquet app + interface compilee (static\) + VERSION
# puis compile cct.iss avec Inno Setup (epingle) et ecrit le SHA-256 du setup.
#
#   .\build.ps1 -Version v0.2.0 -FrontendDist ..\..\frontend\dist -OutDir ..\..\dist
param(
    [Parameter(Mandatory = $true)] [string] $Version,
    [Parameter(Mandatory = $true)] [string] $FrontendDist,
    [string] $OutDir = 'dist',
    [string] $Work = ''
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'native.ps1')

$repo = Resolve-Path (Join-Path $PSScriptRoot '..\..')
if (-not $Work) { $Work = Join-Path $(if ($env:RUNNER_TEMP) { $env:RUNNER_TEMP } else { $env:TEMP }) 'cct-build' }
$payload = Join-Path $Work 'payload'
$downloads = Join-Path $Work 'downloads'
if (Test-Path -LiteralPath $payload) { Remove-Item -LiteralPath $payload -Recurse -Force }
New-Item -ItemType Directory -Force -Path $payload, $downloads, $OutDir | Out-Null

function Invoke-Checked([string] $FilePath, [string[]] $Arguments) {
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) { throw ($FilePath + ' a echoue (code ' + $LASTEXITCODE + ')') }
}

Write-Host '==> Python embarque'
$zip = Get-VerifiedDownload $Pinned.PythonUrl $Pinned.PythonSha256 (Join-Path $downloads 'python-embed.zip')
$python = Join-Path $payload 'python'
Expand-Archive -LiteralPath $zip -DestinationPath $python
$pth = Join-Path $python (Get-PthFileName $Pinned.PythonVersion)
$exe = Join-Path $python 'python.exe'

Write-Host '==> Dependances (wheels win_amd64, empreintes exigees)'
$requirements = Join-Path $PSScriptRoot 'requirements.txt'
if (-not (Test-HashedRequirements $requirements)) { throw 'requirements.txt : une exigence sans empreinte' }
if ((Get-RequirementHash $requirements 'chess') -ne $Pinned.ChessSha256) { throw 'python-chess : empreinte epinglee differente de uv.lock' }
$wheels = Join-Path $Work 'requirements-wheels.txt'
Write-RequirementsWithout $requirements @('chess') $wheels
$pip = Get-VerifiedDownload $Pinned.PipUrl $Pinned.PipSha256 (Join-Path $downloads 'pip.whl')
# pip ne sert qu'a la construction : present dans le ._pth le temps de l'installation.
[System.IO.File]::WriteAllLines($pth, [string[]](Get-PthLines $Pinned.PythonVersion @($pip)))
Invoke-Checked $exe @('-m', 'pip', 'install', '--no-deps', '--require-hashes', '--only-binary=:all:',
    '--no-input', '--disable-pip-version-check', '--target', (Join-Path $payload 'site-packages'), '-r', $wheels)
[System.IO.File]::WriteAllLines($pth, [string[]](Get-PthLines $Pinned.PythonVersion))
# python-chess : pur Python, publie en sources seulement ; on extrait le paquet.
$sdist = Get-VerifiedDownload $Pinned.ChessUrl $Pinned.ChessSha256 (Join-Path $downloads 'chess.tar.gz')
$unpacked = Join-Path $Work 'chess-src'
if (Test-Path -LiteralPath $unpacked) { Remove-Item -LiteralPath $unpacked -Recurse -Force }
New-Item -ItemType Directory -Force -Path $unpacked | Out-Null
Invoke-Checked 'tar.exe' @('-xzf', $sdist, '-C', $unpacked)
$chessRoot = Join-Path $unpacked ('chess-' + $Pinned.ChessVersion)
Copy-Item -LiteralPath (Join-Path $chessRoot 'chess') -Destination (Join-Path $payload 'site-packages') -Recurse
Copy-Item -LiteralPath (Join-Path $chessRoot 'LICENSE.txt') -Destination (Join-Path $payload 'site-packages\chess\LICENSE.txt') -ErrorAction SilentlyContinue

Write-Host '==> Application et interface'
$backend = Join-Path $payload 'backend'
New-Item -ItemType Directory -Force -Path $backend | Out-Null
Copy-Item -LiteralPath (Join-Path $repo 'backend\app') -Destination $backend -Recurse
Get-ChildItem -LiteralPath $backend -Recurse -Directory -Filter '__pycache__' | Remove-Item -Recurse -Force
if (-not (Test-Path -LiteralPath (Join-Path $FrontendDist 'index.html'))) { throw ('Interface absente : ' + $FrontendDist) }
Copy-Item -LiteralPath $FrontendDist -Destination (Join-Path $backend 'static') -Recurse
[System.IO.File]::WriteAllText((Join-Path $backend 'VERSION'), $Version)
Copy-Item -LiteralPath (Join-Path $repo 'LICENSE'), (Join-Path $repo 'THIRD_PARTY_NOTICES.md') -Destination $payload
# Bytecode precompile : premier demarrage plus rapide, rien a ecrire dans le dossier du programme.
Invoke-Checked $exe @('-m', 'compileall', '-q', '-j', '0', $backend, (Join-Path $payload 'site-packages'))
# L'application se charge-t-elle avec ce Python et ces dependances ? (pas de
# guillemets doubles : Windows PowerShell 5.1 les retire des arguments natifs)
Invoke-Checked $exe @('-c', 'import app.desktop, app.main, chess.engine, pydantic_core; print(''import ok'')')

Write-Host '==> Inno Setup'
function Find-Iscc { Get-ChildItem -Path (Join-Path ${env:ProgramFiles} 'Inno Setup 7*\ISCC.exe') -ErrorAction SilentlyContinue | Select-Object -First 1 }
$iscc = Find-Iscc
if (-not $iscc) {
    $installer = Get-VerifiedDownload $Pinned.InnoUrl $Pinned.InnoSha256 (Join-Path $downloads 'innosetup.exe')
    $p = Start-Process -FilePath $installer -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', '/ALLUSERS' -Wait -PassThru
    if ($p.ExitCode -ne 0) { throw ('Installation d''Inno Setup en echec : ' + $p.ExitCode) }
    $iscc = Find-Iscc
}
if (-not $iscc) { throw 'ISCC (Inno Setup 7) introuvable' }
$iscc = $iscc.FullName
$out = (Resolve-Path $OutDir).Path
Invoke-Checked $iscc @('/Q', ('/DAppVersion=' + $Version), ('/DFileVersion=' + (ConvertTo-FileVersion $Version)),
    ('/DPayload=' + $payload), ('/O' + $out), (Join-Path $PSScriptRoot 'cct.iss'))

$setup = Get-ChildItem -LiteralPath $out -Filter 'ChessCalculationTrainer-Setup-*.exe' | Select-Object -First 1
$hash = (Get-FileHash -LiteralPath $setup.FullName -Algorithm SHA256).Hash
[System.IO.File]::WriteAllText($setup.FullName + '.sha256', ($hash + '  ' + $setup.Name + "`n"))
Write-Host ('==> ' + $setup.Name + ' (' + [math]::Round($setup.Length / 1MB, 1) + ' Mo) SHA256 ' + $hash)
