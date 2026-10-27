#requires -Version 5.1
# Controles des scripts Windows : encodage, analyse statique, tests Pester.
# Code de sortie non nul au moindre probleme (utilise par la CI et par appctl).
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
# Installateur natif (Lot 7) : memes regles, sous-dossiers compris.
$native = Join-Path (Split-Path -Parent $root) 'windows-native'
$failures = 0

# 1. ASCII et CRLF : Windows PowerShell 5.1 lit un .ps1 sans BOM en ANSI, et
#    cmd.exe lit mal un .cmd en LF.
$scripts = @(Get-ChildItem -LiteralPath $root -File) + @(Get-ChildItem -LiteralPath $native -File -Recurse)
foreach ($file in $scripts | Where-Object { $_.Extension -in @('.ps1', '.cmd', '.iss') }) {
    $bytes = [System.IO.File]::ReadAllBytes($file.FullName)
    if (@($bytes | Where-Object { $_ -gt 127 }).Count -gt 0) { Write-Host ('NON ASCII : ' + $file.Name); $failures++ }
    $text = [System.Text.Encoding]::ASCII.GetString($bytes)
    if ($text -match "[^`r]`n") { Write-Host ('FIN DE LIGNE LF (CRLF attendu) : ' + $file.Name); $failures++ }
}

# 2. Analyse statique, syntaxe compatible 5.1 et 7.
$settings = @{
    Severity = @('Error', 'Warning')
    ExcludeRules = @(
        'PSAvoidUsingWriteHost',                       # scripts de console, messages pour l'utilisateur
        'PSUseShouldProcessForStateChangingFunctions', # fonctions internes, confirmations faites explicitement
        'PSUseSingularNouns', 'PSUseApprovedVerbs', 'PSUseBOMForUnicodeEncodedFile'
    )
    Rules = @{ PSUseCompatibleSyntax = @{ Enable = $true; TargetVersions = @('5.1', '7.0') } }
}
$findings = @(Invoke-ScriptAnalyzer -Path $root -Settings $settings) + @(Invoke-ScriptAnalyzer -Path $native -Recurse -Settings $settings)
foreach ($f in $findings) { Write-Host ('{0}:{1} [{2}] {3}' -f $f.ScriptName, $f.Line, $f.RuleName, $f.Message) }
$failures += $findings.Count

# 3. Tests Pester.
$config = New-PesterConfiguration
$config.Run.Path = @($PSScriptRoot, (Join-Path $native 'tests'))
$config.Run.PassThru = $true
$config.Output.Verbosity = 'Detailed'
$result = Invoke-Pester -Configuration $config
$failures += $result.FailedCount
if ($result.TotalCount -eq 0) { Write-Host 'Aucun test Pester execute.'; $failures++ }

Write-Host ('Analyse : ' + $findings.Count + ' probleme(s) ; Pester : ' + $result.PassedCount + ' reussi(s), ' + $result.FailedCount + ' echec(s).')
exit ([int]($failures -gt 0))
