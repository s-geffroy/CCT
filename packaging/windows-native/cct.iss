; Installateur Windows natif (Lot 7) : par utilisateur, sans droits
; administrateur, sans Docker. Compile par build.ps1 :
;   ISCC /DAppVersion=v0.2.0 /DFileVersion=0.2.0.0 /DPayload=<payload> cct.iss
;
; Programme : %LOCALAPPDATA%\Programs\ChessCalculationTrainer (remplace a chaque mise a jour)
; Donnees   : %LOCALAPPDATA%\ChessCalculationTrainer\data (jamais supprimees par
;             l'installateur ni par la desinstallation)

#ifndef AppVersion
  #error AppVersion manquant
#endif
#ifndef FileVersion
  #error FileVersion manquant
#endif
#ifndef Payload
  #error Payload manquant
#endif

#define AppName "Chess Calculation Trainer"

[Setup]
; Identifiant fixe : ne jamais le changer (mises a jour et desinstallation en dependent).
AppId={{E877534B-0CBD-4AD0-9E90-B99D56245D2C}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Chess Calculation Trainer
AppPublisherURL=https://github.com/s-geffroy/CCT
VersionInfoVersion={#FileVersion}
DefaultDirName={localappdata}\Programs\ChessCalculationTrainer
DisableDirPage=yes
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputBaseFilename=ChessCalculationTrainer-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
LicenseFile={#Payload}\LICENSE
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\python\pythonw.exe
; Le lanceur est arrete proprement par [Code] avant la copie.
CloseApplications=no
SetupLogging=yes

[Languages]
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "Creer un raccourci sur le Bureau"; GroupDescription: "Raccourcis :"

[InstallDelete]
; Mise a jour : aucune trace de l'ancienne version (modules retires, bytecode perime).
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\site-packages"
Type: filesandordirs; Name: "{app}\backend"

[Files]
Source: "{#Payload}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}\{#AppName}"; Filename: "{app}\python\pythonw.exe"; Parameters: "-m app.desktop"; WorkingDir: "{app}"; Comment: "Ouvrir l'application dans le navigateur"
Name: "{autoprograms}\{#AppName}\Arreter {#AppName}"; Filename: "{app}\python\pythonw.exe"; Parameters: "-m app.desktop --stop"; WorkingDir: "{app}"
Name: "{autoprograms}\{#AppName}\Dossier des donnees"; Filename: "{localappdata}\ChessCalculationTrainer\data"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\python\pythonw.exe"; Parameters: "-m app.desktop"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\python\pythonw.exe"; Parameters: "-m app.desktop"; WorkingDir: "{app}"; Description: "Ouvrir {#AppName}"; Flags: postinstall nowait skipifsilent

[UninstallRun]
Filename: "{app}\python\python.exe"; Parameters: "-m app.desktop --stop"; WorkingDir: "{app}"; Flags: runhidden waituntilterminated; RunOnceId: "StopApp"

[UninstallDelete]
; Bytecode ecrit apres l'installation ; les DONNEES (autre dossier) restent.
Type: filesandordirs; Name: "{app}"

[Code]
// Avant une mise a jour : arret propre de l'instance en cours (le lifespan
// quitte Stockfish et ferme la base), sinon les fichiers seraient verrouilles.
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Python: String;
  Code: Integer;
begin
  Result := '';
  Python := ExpandConstant('{app}\python\python.exe');
  if FileExists(Python) then
  begin
    if not Exec(Python, '-m app.desktop --stop', ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, Code) then
      Log('Arret de l''instance precedente : lancement impossible')
    else if Code <> 0 then
      Result := 'L''application en cours ne s''est pas arretee. Fermez-la (menu Demarrer, "Arreter") puis relancez l''installation.';
  end;
end;
