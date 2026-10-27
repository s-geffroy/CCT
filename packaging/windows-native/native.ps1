#requires -Version 5.1
# Fonctions de la construction de l'installateur natif et de son smoke test.
# Rien ici ne s'execute au chargement : build.ps1 et les tests Pester le
# chargent par dot-sourcing.

# Sources epinglees : versions ET empreintes. Une archive differente est refusee.
$script:Pinned = @{
    PythonVersion = '3.13.17'
    PythonUrl     = 'https://www.python.org/ftp/python/3.13.17/python-3.13.17-embed-amd64.zip'
    PythonSha256  = '9e35319bffedab8b36ad44d8f377cb4f1733bcec257a0b6d04d94f01486ddb38'
    PipUrl        = 'https://files.pythonhosted.org/packages/f3/6e/1736e5b4ae2b778ef2f81c47d797de9f891d4d8acb047a24ca37a60294dd/pip-26.2.1-py3-none-any.whl'
    PipSha256     = '71138adf1f4ca900cdb7d289c21b7494329f2332b6d85f0e1c42108c0384ed3e'
    InnoUrl       = 'https://github.com/jrsoftware/issrc/releases/download/is-7_1_0/innosetup-7.1.0-x64.exe'
    InnoSha256    = '0362a383ed217d4c4239b5933866dd96d3eb2102737da92f80f6057a4b40df2f'
}

function Test-Sha256([string] $Path, [string] $Expected) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $false }
    $actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
    return $actual -eq $Expected.ToUpperInvariant()
}

function Get-VerifiedDownload([string] $Url, [string] $Sha256, [string] $Destination) {
    if (Test-Sha256 $Destination $Sha256) { return $Destination }
    $old = $ProgressPreference
    $ProgressPreference = 'SilentlyContinue'  # sinon Invoke-WebRequest est tres lent sous 5.1
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $Url -OutFile $Destination -UseBasicParsing
    } finally {
        $ProgressPreference = $old
    }
    if (-not (Test-Sha256 $Destination $Sha256)) {
        Remove-Item -LiteralPath $Destination -Force -ErrorAction SilentlyContinue
        throw ('Empreinte SHA-256 inattendue pour ' + $Url + ' : fichier refuse.')
    }
    return $Destination
}

# Fichier ._pth du Python embarque : chemins de recherche figes, relatifs au
# dossier python\ (PYTHONPATH et site-packages utilisateur ignores).
function Get-PthLines([string] $PythonVersion, [string[]] $Extra = @()) {
    $parts = $PythonVersion.Split('.')
    $zip = 'python' + $parts[0] + $parts[1] + '.zip'
    return @($zip, '.') + $Extra + @('..\backend', '..\site-packages')
}

function Get-PthFileName([string] $PythonVersion) {
    $parts = $PythonVersion.Split('.')
    return 'python' + $parts[0] + $parts[1] + '._pth'
}

# Version d'affichage (tag v1.2.3, 0.0.0-ci.42) -> version numerique Windows a.b.c.d.
function ConvertTo-FileVersion([string] $Version) {
    $m = [regex]::Match($Version, '^v?(\d+)\.(\d+)\.(\d+)(?:[-.+]\D*(\d+))?')
    if (-not $m.Success) { throw ('Version invalide : ' + $Version) }
    $build = if ($m.Groups[4].Success) { $m.Groups[4].Value } else { '0' }
    return ('{0}.{1}.{2}.{3}' -f $m.Groups[1].Value, $m.Groups[2].Value, $m.Groups[3].Value, ([int]$build % 65536))
}

# Chaque exigence de requirements.txt doit porter au moins une empreinte.
function Test-HashedRequirements([string] $Path) {
    $text = [System.IO.File]::ReadAllText($Path) -replace "\\\r?\n", ' '
    $reqs = @($text -split "\r?\n" | Where-Object { $_ -match '^[A-Za-z0-9]' })
    if ($reqs.Count -eq 0) { return $false }
    foreach ($r in $reqs) { if ($r -notmatch '--hash=sha256:[0-9a-f]{64}') { return $false } }
    return $true
}

function Wait-Condition([scriptblock] $Condition, [int] $TimeoutSeconds, [string] $What) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $value = & $Condition
        if ($value) { return $value }
        Start-Sleep -Milliseconds 500
    }
    throw ('Delai depasse (' + $TimeoutSeconds + ' s) : ' + $What)
}
