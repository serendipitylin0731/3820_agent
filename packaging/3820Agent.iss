#define AppName "3820 战略知识助手"
#define AppVersion "0.1.0"

[Setup]
AppId={{D684B40D-1361-4438-BD51-3820A6F7C811}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=3820 Agent Project
DefaultDirName={localappdata}\Programs\3820Agent
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist\installer
OutputBaseFilename=3820Agent-Setup-x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\3820Agent.exe
CloseApplications=yes

[Languages]
Name: "chinesesimp"; MessagesFile: "ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加选项："; Flags: unchecked

[Files]
Source: "..\dist\3820Agent\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\3820Agent.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\3820Agent.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\3820Agent.exe"; Description: "启动 {#AppName}"; Flags: nowait postinstall skipifsilent
