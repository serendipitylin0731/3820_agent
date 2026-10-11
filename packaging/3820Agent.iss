#define AppName "3820 战略知识助手"
#define AppVersion "0.7.0"
#define AppUserModelID "edu.sjtu.serendipity.3820Agent"

[Setup]
AppId={{D684B40D-1361-4438-BD51-3820A6F7C811}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=3820 Agent Project
DefaultDirName={localappdata}\Programs\3820Agent
DisableDirPage=no
UsePreviousAppDir=yes
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist\installer
OutputBaseFilename=3820Agent-Setup-x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=3820Agent.ico
UninstallDisplayIcon={app}\3820Agent.ico
CloseApplications=yes

[Languages]
Name: "chinesesimp"; MessagesFile: "ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加选项："; Flags: unchecked

[Files]
Source: "..\dist\3820Agent\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "3820Agent.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\3820Agent.exe"; IconFilename: "{app}\3820Agent.ico"; AppUserModelID: "{#AppUserModelID}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\3820Agent.exe"; IconFilename: "{app}\3820Agent.ico"; AppUserModelID: "{#AppUserModelID}"; Tasks: desktopicon

[Run]
Filename: "{app}\3820Agent.exe"; Description: "启动 {#AppName}"; Flags: nowait postinstall skipifsilent
