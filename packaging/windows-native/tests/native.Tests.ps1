# Tests Pester (5.x) des fonctions de construction de l'installateur natif.
# Le reseau n'est pas utilise : le telechargement verifie est teste sur un
# fichier local (l'installateur reel est teste par smoke-installed.ps1 en CI).
BeforeAll {
    . (Join-Path (Split-Path -Parent $PSScriptRoot) 'native.ps1')
}

Describe 'Sources epinglees' {
    It 'chaque source a une empreinte SHA-256 complete et une URL https' {
        foreach ($k in @('Python', 'Pip', 'Inno')) {
            $Pinned[$k + 'Url'] | Should -Match '^https://'
            $Pinned[$k + 'Sha256'] | Should -Match '^[0-9a-f]{64}$'
        }
        $Pinned.PythonUrl | Should -Match ([regex]::Escape($Pinned.PythonVersion))
    }
    It 'requirements.txt est verrouille par empreintes' {
        Test-HashedRequirements (Join-Path (Split-Path -Parent $PSScriptRoot) 'requirements.txt') | Should -BeTrue
    }
}

Describe 'Test-HashedRequirements' {
    It 'refuse une exigence sans empreinte' {
        $f = Join-Path $TestDrive 'r.txt'
        Set-Content -LiteralPath $f -Value @('a==1 \', ('    --hash=sha256:' + ('a' * 64)), 'b==2')
        Test-HashedRequirements $f | Should -BeFalse
    }
    It 'accepte des exigences toutes hachees, commentaires compris' {
        $f = Join-Path $TestDrive 'ok.txt'
        Set-Content -LiteralPath $f -Value @('# genere', 'a==1 \', ('    --hash=sha256:' + ('b' * 64)), '    # via x')
        Test-HashedRequirements $f | Should -BeTrue
    }
}

Describe 'Test-Sha256' {
    It 'compare sans tenir compte de la casse et refuse un fichier absent' {
        $f = Join-Path $TestDrive 'x.bin'
        [System.IO.File]::WriteAllBytes($f, [byte[]](1, 2, 3))
        $h = (Get-FileHash -LiteralPath $f -Algorithm SHA256).Hash.ToLowerInvariant()
        Test-Sha256 $f $h | Should -BeTrue
        Test-Sha256 $f ('0' * 64) | Should -BeFalse
        Test-Sha256 (Join-Path $TestDrive 'absent') $h | Should -BeFalse
    }
    It 'un fichier deja present et conforme n est pas retelecharge' {
        $f = Join-Path $TestDrive 'y.bin'
        [System.IO.File]::WriteAllBytes($f, [byte[]](4, 5))
        $h = (Get-FileHash -LiteralPath $f -Algorithm SHA256).Hash
        Get-VerifiedDownload 'https://invalid.example/never' $h $f | Should -Be $f
    }
}

Describe 'Python embarque' {
    It 'fichier ._pth : archive standard, dossier, puis backend et site-packages' {
        Get-PthFileName '3.13.17' | Should -Be 'python313._pth'
        $lines = Get-PthLines '3.13.17'
        ($lines -join '|') | Should -Be 'python313.zip|.|..\backend|..\site-packages'
        (Get-PthLines '3.13.17' @('C:\w\pip.whl'))[2] | Should -Be 'C:\w\pip.whl'
    }
}

Describe 'ConvertTo-FileVersion' {
    It 'convertit un tag et une version de CI en version Windows a quatre nombres' {
        ConvertTo-FileVersion 'v0.2.0' | Should -Be '0.2.0.0'
        ConvertTo-FileVersion '0.0.0-ci.42' | Should -Be '0.0.0.42'
        ConvertTo-FileVersion '1.2.3' | Should -Be '1.2.3.0'
    }
    It 'refuse une version sans forme a.b.c' {
        { ConvertTo-FileVersion 'dev' } | Should -Throw
    }
}

Describe 'Wait-Condition' {
    It 'rend la premiere valeur vraie' {
        $script:n = 0
        Wait-Condition { $script:n++; if ($script:n -ge 2) { 'pret' } } 5 'test' | Should -Be 'pret'
    }
    It 'echoue avec un message apres le delai' {
        { Wait-Condition { $false } 1 'rien' } | Should -Throw '*rien*'
    }
}
