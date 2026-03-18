; =============================================================================
; Inno Setup Script for Libiry
; =============================================================================
; Dit script maakt een professionele Windows installer (.exe) die:
; - Libiry installeert in Program Files
; - Een desktop shortcut aanmaakt
; - Een Start Menu entry aanmaakt
; - Een uninstaller toevoegt aan Windows "Apps & Features"
;
; Vereist: Inno Setup 6.x (gratis download: https://jrsoftware.org/isinfo.php)
; Gebruik: Open dit bestand in Inno Setup Compiler en klik "Compile"
;
; Waarom Inno Setup:
; - Gratis en open source
; - Industriestandaard voor Windows installers
; - Maakt professionele installers zonder code signing vereiste
; - Alternatief NSIS is complexer en minder user-friendly
; =============================================================================

#define MyAppName "Libiry"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Libiry"
#define MyAppURL "https://github.com/libiry/libiry"
#define MyAppExeName "Libiry.exe"

[Setup]
; Unieke ID voor deze applicatie (NIET WIJZIGEN na eerste release!)
; Gegenereerd met: https://www.guidgenerator.com/
AppId={{A7B3C8D9-E1F2-4A5B-6C7D-8E9F0A1B2C3D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; Installatie locatie
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}

; Waar de installer wordt opgeslagen
OutputDir=dist\installer
OutputBaseFilename=LibirySetup

; Compressie (lzma2 is beste balans tussen grootte en snelheid)
Compression=lzma2
SolidCompression=yes

; Windows versie vereisten
MinVersion=10.0

; Rechten (admin voor Program Files, user voor AppData)
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog

; Wizard styling
WizardStyle=modern
WizardSizePercent=100

; Icon voor de installer zelf
SetupIconFile=resources\icons\Libiry.ico

; Uninstaller
UninstallDisplayIcon={app}\Libiry.exe
UninstallDisplayName={#MyAppName}

; Licentie en info pagina's (optioneel, uncomment indien gewenst)
; LicenseFile=LICENSE.txt
; InfoBeforeFile=README.txt

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "dutch"; MessagesFile: "compiler:Languages\Dutch.isl"

[Files]
; Kopieer alle bestanden uit de PyInstaller dist/Libiry folder
; Source pad is relatief aan dit .iss bestand
Source: "dist\Libiry\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; De customize folder moet BUITEN de app folder komen zodat users het kunnen aanpassen
; Bij eerste installatie: kopieer defaults naar user's AppData
Source: "customize\*"; DestDir: "{userappdata}\Libiry\customize"; Flags: ignoreversion recursesubdirs createallsubdirs onlyifdoesntexist

[Dirs]
; Zorg dat de customize folder schrijfbaar is voor de user
Name: "{userappdata}\Libiry"; Permissions: users-modify
Name: "{userappdata}\Libiry\customize"; Permissions: users-modify

[Icons]
; Start Menu
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"

; Desktop shortcut (altijd aangemaakt)
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"

[Run]
; Optie om Libiry direct te starten na installatie
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Registry]
; Registreer de applicatie in Windows App Paths (maakt 'libiry' uitvoerbaar vanaf command line)
Root: HKLM; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{#MyAppExeName}"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName}"; Flags: uninsdeletekey

[Code]
// =============================================================================
// Pascal Script voor custom installer logica
// =============================================================================

// Controleer of een eerdere versie al geinstalleerd is
function InitializeSetup(): Boolean;
var
  UninstallKey: String;
  UninstallString: String;
begin
  Result := True;

  // Check voor bestaande installatie
  UninstallKey := 'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{#SetupSetting("AppId")}_is1';
  if RegQueryStringValue(HKLM, UninstallKey, 'UninstallString', UninstallString) then
  begin
    // Vraag of gebruiker wil doorgaan (oude versie wordt overschreven)
    if MsgBox('An older version of Libiry is already installed. ' +
              'Do you want to continue and update to the new version?',
              mbConfirmation, MB_YESNO) = IDNO then
    begin
      Result := False;
    end;
  end;
end;
