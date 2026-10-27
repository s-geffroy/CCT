# Tests Pester (5.x) des fonctions communes. Docker et le reseau sont simules :
# ces tests ne pretendent pas valider Docker Desktop (gates W01-W10, poste reel).
BeforeAll {
    . (Join-Path (Split-Path -Parent $PSScriptRoot) 'common.ps1')
    # Pas de docker sur la machine de test : une commande vide, que les tests simulent.
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { function global:docker { } }
    $digest = 'sha256:' + ('a' * 64)
    $validRef = 'ghcr.io/s-geffroy/cct@' + $digest
}

Describe 'Test-ImageRef' {
    It 'accepte une image GHCR par digest' { Test-ImageRef $validRef | Should -BeTrue }
    It 'refuse un tag mutable, une majuscule, un digest court ou un autre registre' {
        Test-ImageRef 'ghcr.io/s-geffroy/cct:latest' | Should -BeFalse
        Test-ImageRef 'ghcr.io/s-geffroy/CCT@sha256:abc' | Should -BeFalse
        Test-ImageRef ('ghcr.io/s-geffroy/cct@sha256:' + ('a' * 63)) | Should -BeFalse
        Test-ImageRef ('docker.io/x/cct@' + $digest) | Should -BeFalse
        Test-ImageRef '' | Should -BeFalse
    }
}

Describe 'Fichier .env' {
    It 'lit les cles, ignore commentaires et lignes vides, garde le reste de la valeur' {
        $f = Join-Path $TestDrive 'a.env'
        Set-Content -LiteralPath $f -Value @('# commentaire', '', 'IMAGE_REF=x=y', ' HOST_PORT = 8765 ')
        $v = Read-EnvFile $f
        $v['IMAGE_REF'] | Should -Be 'x=y'
        $v['HOST_PORT'] | Should -Be '8765'
    }
    It 'refuse une cle en double ou une ligne sans =' {
        $f = Join-Path $TestDrive 'b.env'
        Set-Content -LiteralPath $f -Value @('A=1', 'A=2')
        { Read-EnvFile $f } | Should -Throw '*double*'
        Set-Content -LiteralPath $f -Value @('nimportequoi')
        { Read-EnvFile $f } | Should -Throw '*invalide*'
    }
    It 'fichier absent : configuration vide' { (Read-EnvFile (Join-Path $TestDrive 'absent.env')).Count | Should -Be 0 }
    It 'ecrit puis relit sans perte, sans BOM, cles connues en tete' {
        $f = Join-Path $TestDrive 'c.env'
        Write-EnvFile $f @{ ZZZ = '1'; HOST_PORT = '8766'; IMAGE_REF = $validRef }
        $lines = @(Get-Content -LiteralPath $f)
        $lines[0] | Should -Be ('IMAGE_REF=' + $validRef)
        $lines[1] | Should -Be 'HOST_PORT=8766'
        [System.IO.File]::ReadAllBytes($f)[0] | Should -Be ([byte][char]'I')
        (Read-EnvFile $f)['ZZZ'] | Should -Be '1'
    }
}

Describe 'Get-HostPort' {
    It '8765 par defaut, valeur lue sinon' {
        Get-HostPort @{} | Should -Be 8765
        Get-HostPort @{ HOST_PORT = '9000' } | Should -Be 9000
    }
    It 'refuse un port invalide ou privilegie' {
        { Get-HostPort @{ HOST_PORT = 'abc' } } | Should -Throw
        { Get-HostPort @{ HOST_PORT = '80' } } | Should -Throw
        { Get-HostPort @{ HOST_PORT = '70000' } } | Should -Throw
    }
}

Describe 'Read-ReleaseManifest' {
    BeforeEach { $f = Join-Path $TestDrive 'release-manifest.json' }
    It 'accepte un manifeste conforme' {
        @{ schema_version = 1; target_platform = 'linux/amd64'; image_ref = $validRef; app_version = 'v0.1.0'; host_port_default = 8765 } |
            ConvertTo-Json | Set-Content -LiteralPath $f
        (Read-ReleaseManifest $f).app_version | Should -Be 'v0.1.0'
    }
    It 'refuse une autre plateforme, un tag mutable ou un fichier absent' {
        @{ schema_version = 1; target_platform = 'linux/arm64'; image_ref = $validRef } | ConvertTo-Json | Set-Content -LiteralPath $f
        { Read-ReleaseManifest $f } | Should -Throw '*linux/amd64*'
        @{ schema_version = 1; target_platform = 'linux/amd64'; image_ref = 'ghcr.io/s-geffroy/cct:v0.1.0' } | ConvertTo-Json | Set-Content -LiteralPath $f
        { Read-ReleaseManifest $f } | Should -Throw '*digest*'
        { Read-ReleaseManifest (Join-Path $TestDrive 'nope.json') } | Should -Throw '*absent*'
    }
}

Describe 'Protect-Text' {
    It 'masque le compte, le poste et le profil (chemins accentues compris)' {
        $saved = @($env:USERPROFILE, $env:USERNAME, $env:COMPUTERNAME)
        try {
            $env:USERPROFILE = 'C:\Users\Elodie Muller'; $env:USERNAME = 'Elodie Muller'; $env:COMPUTERNAME = 'PC-SALON'
            Protect-Text 'C:\Users\Elodie Muller\AppData\Local et Elodie Muller sur PC-SALON' |
                Should -Be '<profil>\AppData\Local et <utilisateur> sur <poste>'
        } finally { $env:USERPROFILE, $env:USERNAME, $env:COMPUTERNAME = $saved }
    }
}

Describe 'Test-PortFree' {
    It 'detecte un port deja occupe' {
        $listener = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, 0)
        $listener.Start()
        try {
            $port = $listener.LocalEndpoint.Port
            Test-PortFree $port | Should -BeFalse
        } finally { $listener.Stop() }
        Test-PortFree $port | Should -BeTrue
    }
}

Describe 'Get-Health' {
    It 'ready quand /live et /ready repondent' {
        Mock Invoke-WebRequest { [pscustomobject]@{ StatusCode = 200 } }
        Get-Health 'http://127.0.0.1:8765' | Should -Be 'ready'
    }
    It 'live quand le moteur est indisponible (/ready en 503) : pas un echec' {
        Mock Invoke-WebRequest { if ($Uri -like '*ready') { throw '503' } else { [pscustomobject]@{ StatusCode = 200 } } }
        Get-Health 'http://127.0.0.1:8765' | Should -Be 'live'
    }
    It 'down quand le processus ne repond pas' {
        Mock Invoke-WebRequest { throw 'refused' }
        Get-Health 'http://127.0.0.1:8765' | Should -Be 'down'
    }
}

Describe 'Invoke-Compose' {
    It 'cible uniquement le projet de l application, jamais les autres stacks' {
        Mock docker { $global:LASTEXITCODE = 0; 'ok' }
        $app = Join-Path $TestDrive 'App'
        Invoke-Compose $app @('up', '-d') | Should -Be 'ok'
        $expected = 'compose --project-name chess-calculation-trainer --project-directory ' + $app + ' --env-file ' +
            (Join-Path $app '.env') + ' -f ' + (Join-Path $app 'compose.yaml') + ' up -d'
        Should -Invoke docker -Times 1 -ParameterFilter { ($args -join ' ') -eq $expected }
    }
    It 'echec signale avec le message de docker, sauf si tolere explicitement' {
        Mock docker { $global:LASTEXITCODE = 1; 'boom' }
        { Invoke-Compose $TestDrive @('pull') } | Should -Throw '*pull*boom*'
        { Invoke-Compose $TestDrive @('pull') -AllowFailure } | Should -Not -Throw
    }
    It 'desinstallation : down sans -v (les donnees restent)' {
        $uninstall = Get-Content -LiteralPath (Join-Path (Split-Path -Parent $PSScriptRoot) 'uninstall.ps1') -Raw
        $uninstall | Should -Match "Invoke-Compose \`$appRoot @\('down'\)"
        $uninstall | Should -Not -Match "'down', '-v'"
    }
}

Describe 'Get-DockerState' {
    BeforeEach { Mock Resolve-Docker { $true } }
    It 'linux, windows, arrete ou absent' {
        Mock docker { $global:LASTEXITCODE = 0; 'linux' }
        Get-DockerState | Should -Be 'linux'
        Mock docker { $global:LASTEXITCODE = 0; 'windows' }
        Get-DockerState | Should -Be 'windows'
        Mock docker { $global:LASTEXITCODE = 1 }
        Get-DockerState | Should -Be 'stopped'
        Mock Resolve-Docker { $false }
        Get-DockerState | Should -Be 'absent'
    }
    It 'hors installation : rien n est installe, message et lien officiel' {
        Mock Get-DockerState { 'absent' }
        Mock Install-DockerDesktop { $true }
        { Assert-DockerReady } | Should -Throw '*Docker Desktop absent*'
        Should -Invoke Install-DockerDesktop -Times 0
        Mock Get-DockerState { 'windows' }
        { Assert-DockerReady } | Should -Throw '*Linux containers*'
    }
}

Describe 'Installation assistee des prerequis' {
    BeforeEach {
        Mock Write-Host { }
        Mock Start-Process { }
        Mock Start-Sleep { }
    }
    It 'Docker absent, accord donne : installation officielle par winget, sans accepter de licence a la place de l utilisateur' {
        Mock Get-Command { [pscustomobject]@{ Name = 'winget' } } -ParameterFilter { $Name -eq 'winget' }
        Mock Confirm-Action { $true }
        Mock Invoke-Winget { 0 }
        Mock Get-DockerDesktopExe { 'C:\Docker Desktop.exe' }
        Install-DockerDesktop | Should -BeTrue
        Should -Invoke Invoke-Winget -Times 1 -ParameterFilter {
            ($Arguments -join ' ') -eq 'install --exact --id Docker.DockerDesktop --source winget' -and
            -not ($Arguments -match 'accept')
        }
    }
    It 'Docker absent, accord refuse : rien d installe, gestes affiches et page officielle ouverte' {
        Mock Get-Command { [pscustomobject]@{ Name = 'winget' } } -ParameterFilter { $Name -eq 'winget' }
        Mock Confirm-Action { $false }
        Mock Invoke-Winget { 0 }
        Mock Show-DockerSteps { }
        Install-DockerDesktop | Should -BeFalse
        Should -Invoke Invoke-Winget -Times 0
        Should -Invoke Show-DockerSteps -Times 1
        Should -Invoke Start-Process -Times 1 -ParameterFilter { $FilePath -like 'https://docs.docker.com/*' }
    }
    It 'Docker installe puis demarre automatiquement : l installation continue dans la meme execution' {
        $script:states = [System.Collections.Generic.Queue[string]]::new([string[]]@('absent', 'stopped', 'linux'))
        Mock Get-DockerState { $script:states.Dequeue() }
        Mock Install-DockerDesktop { $true }
        Mock Get-DockerDesktopExe { 'C:\Docker Desktop.exe' }
        Mock Wait-DockerLinux { $true }
        { Resolve-DockerPrerequisite -Interactive } | Should -Not -Throw
        Should -Invoke Start-Process -Times 1 -ParameterFilter { $FilePath -eq 'C:\Docker Desktop.exe' }
    }
    It 'Docker arrete qui ne demarre pas : message clair' {
        Mock Get-DockerState { 'stopped' }
        Mock Get-DockerDesktopExe { 'C:\Docker Desktop.exe' }
        Mock Wait-DockerLinux { $false }
        { Resolve-DockerPrerequisite } | Should -Throw '*ne repond toujours pas*'
    }
    It 'conteneurs Windows : bascule vers Linux seulement avec accord' {
        Mock Get-DockerState { 'windows' }
        Mock Test-Path { $true } -ParameterFilter { $LiteralPath -like '*DockerCli.exe' }
        Mock Confirm-Action { $false }
        { Resolve-DockerPrerequisite -Interactive } | Should -Throw '*Switch to Linux containers*'
    }
    It 'WSL absent, accord donne : wsl --install avec elevation UAC, puis redemarrage demande' {
        Mock Get-Command { $null } -ParameterFilter { $Name -eq 'wsl.exe' }
        Mock Confirm-Action { $true }
        Mock Invoke-Elevated { 0 }
        Resolve-WslPrerequisite | Should -Be 'reboot'
        Should -Invoke Invoke-Elevated -Times 1 -ParameterFilter { $FilePath -eq 'wsl.exe' -and ($Arguments -join ' ') -eq '--install --no-distribution' }
    }
    It 'WSL absent, accord refuse : gestes precis, rien d execute' {
        Mock Get-Command { $null } -ParameterFilter { $Name -eq 'wsl.exe' }
        Mock Confirm-Action { $false }
        Mock Invoke-Elevated { 0 }
        { Resolve-WslPrerequisite } | Should -Throw '*wsl --install --no-distribution*'
        Should -Invoke Invoke-Elevated -Times 0
    }
    It 'WSL present et a jour : rien a faire' {
        Mock Get-Command { [pscustomobject]@{ Name = 'wsl.exe' } } -ParameterFilter { $Name -eq 'wsl.exe' }
        Mock Invoke-Wsl { 0 }
        Mock Confirm-Action { throw 'aucune question attendue' }
        Resolve-WslPrerequisite | Should -Be 'ok'
    }
    It 'accord : seules les reponses oui sont prises pour un accord' {
        Mock Read-Host { 'o' }
        Confirm-Action '?' | Should -BeTrue
        Mock Read-Host { '' }
        Confirm-Action '?' | Should -BeFalse
        Mock Read-Host { 'non' }
        Confirm-Action '?' | Should -BeFalse
    }
}

Describe 'Copy-BundleFiles' {
    It 'copie lanceurs, notices, manifeste et scripts ; rien depuis le dossier installe lui-meme' {
        $src = Join-Path $TestDrive 'bundle'; $dst = Join-Path $TestDrive 'Donnees eleve'
        New-Item -ItemType Directory -Path (Join-Path $src 'scripts/windows') -Force | Out-Null
        foreach ($n in @('INSTALLER.cmd', 'README_WINDOWS.md', 'release-manifest.json', 'compose.yaml', 'LICENSE', 'autre.exe')) {
            Set-Content -LiteralPath (Join-Path $src $n) -Value 'x'
        }
        Set-Content -LiteralPath (Join-Path $src 'scripts/windows/install.ps1') -Value 'x'
        Copy-BundleFiles $src $dst
        (Get-ChildItem -LiteralPath $dst -File).Name | Sort-Object |
            Should -Be @('compose.yaml', 'INSTALLER.cmd', 'LICENSE', 'README_WINDOWS.md', 'release-manifest.json')
        Test-Path -LiteralPath (Join-Path $dst 'scripts/windows/install.ps1') | Should -BeTrue
        { Copy-BundleFiles $dst $dst } | Should -Not -Throw
    }
}

Describe 'Invoke-AppBackup' {
    It 'sauvegarde dans le conteneur, refuse un resultat non verifie, copie sur le PC' {
        $app = Join-Path $TestDrive 'app'
        New-Item -ItemType Directory -Path $app -Force | Out-Null
        Mock Test-AppRunning { $true }
        Mock Invoke-Compose {
            if ($Arguments[0] -eq 'exec') { 'log ignore'; '{"ok": true, "path": "/data/backups/cct-1.sqlite", "sessions": 3, "schema_version": 4}' }
        }
        $r = Invoke-AppBackup $app
        $r.Sessions | Should -Be 3
        $r.Path | Should -Be (Join-Path (Join-Path $app 'backups') 'cct-1.sqlite')
        Should -Invoke Invoke-Compose -ParameterFilter { $Arguments[0] -eq 'cp' -and $Arguments[1] -eq 'app:/data/backups/cct-1.sqlite' }
        Mock Invoke-Compose { if ($Arguments[0] -eq 'exec') { '{"ok": false, "reason": "integrite"}' } }
        { Invoke-AppBackup $app } | Should -Throw '*integrite*'
    }
}

Describe 'Scripts' {
    It 'chaque script se lit sans erreur de syntaxe' {
        foreach ($s in Get-ChildItem -LiteralPath (Split-Path -Parent $PSScriptRoot) -Filter '*.ps1' -File) {
            $errors = $null
            [System.Management.Automation.Language.Parser]::ParseFile($s.FullName, [ref]$null, [ref]$errors) | Out-Null
            $errors | Should -BeNullOrEmpty -Because $s.Name
        }
    }
    It 'chaque lanceur .cmd appelle un script qui existe' {
        $dir = Split-Path -Parent $PSScriptRoot
        foreach ($c in Get-ChildItem -LiteralPath $dir -Filter '*.cmd' -File) {
            $m = [regex]::Match((Get-Content -LiteralPath $c.FullName -Raw), 'scripts\\windows\\([a-z-]+\.ps1)')
            $m.Success | Should -BeTrue -Because $c.Name
            Test-Path -LiteralPath (Join-Path $dir $m.Groups[1].Value) | Should -BeTrue -Because $c.Name
        }
    }
}
