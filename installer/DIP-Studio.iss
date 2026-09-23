#define MyAppName "DIP Studio"
#define MyAppPublisher "Emran025"
#define MyAppExeName "DIP-Studio.exe"
#define MyAppVersion GetDefineValue("MyAppVersion")

[Setup]
AppId={{C73D8F2D-3A85-4BF2-AE4D-6B5E8F0F0A01}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\DIP Studio
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist\installer
OutputBaseFilename=DIP-Studio-Setup
Compression=lzma
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
SetupIconFile=..\src\dip_studio\assets\DIP-Studio.ico
UninstallDisplayIcon={app}\{#MyAppExeName}

[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: postinstall nowait skipifsilent
