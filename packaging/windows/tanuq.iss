; TANUQ FREE - per-user Windows installer (Inno Setup 6.3+/7.x)
; Built by build_installer.ps1. Payload = embedded CPython + preinstalled
; TANUQ wheel (see README.md in this folder).

#define AppName "TANUQ FREE"
#ifndef AppVersion
  #define AppVersion "0.6.0"
#endif
#ifndef PayloadDir
  #define PayloadDir ".\\work\\embed"
#endif
#ifndef OutDir
  #define OutDir ".\\out"
#endif

[Setup]
AppId={{9B1F42D0-6E6A-4B4E-9C41-3AF0D2E7C5A1}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=TANUQ
DefaultDirName={localappdata}\Programs\TANUQ
DefaultGroupName=TANUQ
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutDir}
OutputBaseFilename=TANUQ-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName={#AppName} {#AppVersion}
UninstallDisplayIcon={app}\python.exe

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "{#PayloadDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs

[Icons]
Name: "{group}\TANUQ"; Filename: "{app}\TANUQ-UI.cmd"; WorkingDir: "{app}"; Comment: "Start the TANUQ UI (local browser)"
Name: "{group}\TANUQ Licenses"; Filename: "{app}\licenses"; Comment: "Third-party license attributions"
Name: "{userdesktop}\TANUQ"; Filename: "{app}\TANUQ-UI.cmd"; WorkingDir: "{app}"; Tasks: desktopicon

[UninstallDelete]
; Make uninstall fully clean (everything under {app} belongs to this install).
Type: filesandordirs; Name: "{app}"
