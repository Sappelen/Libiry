; =============================================================================
; Inno Setup Script for Libiry
; =============================================================================
; This script makes a professional Windows installer (.exe) that:
; - Install Libiry in Program Files
; - Makes a desktop shortcut
; - Makes a Start Menu entry 
; - Adds an uninstaller to Windows "Apps & Features"
;
; Required: Inno Setup 6.x (free download: https://jrsoftware.org/isinfo.php)
; Use: Open this file in Inno Setup Compiler and click "Compile"
;
; Why Inno Setup:
; - Free and open source
; - Industry default for Windows installers
; - Makes professional installers without required code signing
; - Alternative NSIS is more complex and less user friendly
; =============================================================================

#define MyAppName "Libiry"
#define MyAppVersion "0.2.0"
#define MyAppPublisher "Libiry"
#define MyAppURL "https://github.com/libiry/libiry"
#define MyAppExeName "Libiry.exe"

[Setup]
; Unique ID for this application (DO NOT CHANGE after first release!)
; Generated with: https://www.guidgenerator.com/
AppId={{A7B3C8D9-E1F2-4A5B-6C7D-8E9F0A1B2C3D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; Installation location
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}

; Where the installer is saved
OutputDir=dist\installer
OutputBaseFilename=LibirySetup

; Compression (lzma2 is best balance between size and speed)
Compression=lzma2
SolidCompression=yes

; Windows version requirements
MinVersion=10.0

; Rights (admin for Program Files, user for AppData)
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog

; Wizard styling
WizardStyle=modern
WizardSizePercent=100

; Icon for the installer itself
SetupIconFile=resources\icons\Libiry.ico

; Uninstaller
UninstallDisplayIcon={app}\Libiry.exe
UninstallDisplayName={#MyAppName}

; Licence and info pages (optional)
; LicenseFile=LICENSE.txt
; InfoBeforeFile=README.txt

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "dutch"; MessagesFile: "compiler:Languages\Dutch.isl"

[Files]
; Copy all files from the PyInstaller dist/Libiry folder
; Source path is relative to this .iss file
Source: "dist\Libiry\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; The customize folder must be placed OUTSIDE the app folder
; First installation: copy defaults to user's AppData
Source: "resources\*"; DestDir: "{userappdata}\Libiry\customize"; Flags: ignoreversion recursesubdirs createallsubdirs onlyifdoesntexist

[Dirs]
; Make sure the customize folder has the correct authorisation
Name: "{userappdata}\Libiry"; Permissions: users-modify
Name: "{userappdata}\Libiry\customize"; Permissions: users-modify

[Icons]
; Start Menu
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"

; Desktop shortcut (always created)
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"

[Run]
; Option to start Libiry immediately after installation
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Registry]
; Register the app in Windows App Paths (makes 'libiry' executeable from command line)
Root: HKLM; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{#MyAppExeName}"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName}"; Flags: uninsdeletekey

[Code]
// =============================================================================
// Pascal Script for custom installer logic
// =============================================================================

// Check if a previous version is installed already
function InitializeSetup(): Boolean;
var
  UninstallKey: String;
  UninstallString: String;
begin
  Result := True;

  // Check for existing installation
  UninstallKey := 'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{#SetupSetting("AppId")}_is1';
  if RegQueryStringValue(HKLM, UninstallKey, 'UninstallString', UninstallString) then
  begin
    if MsgBox('An older version of Libiry is already installed. ' +
              'Do you want to continue and update to the new version?',
              mbConfirmation, MB_YESNO) = IDNO then
    begin
      Result := False;
    end;
  end;
end;