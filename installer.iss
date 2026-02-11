[Setup]
AppName=DiskPilot
AppVersion=1.0.0
AppVerName=DiskPilot 1.0
AppPublisher=DiskPilot
AppPublisherURL=https://diskpilot.dk
DefaultDirName={autopf}\DiskPilot
DefaultGroupName=DiskPilot
OutputDir=installer_output
OutputBaseFilename=DiskPilot_Setup
SetupIconFile=diskpilot.ico
Compression=lzma2
SolidCompression=yes
UninstallDisplayIcon={app}\DiskPilot.exe
PrivilegesRequired=lowest
WizardStyle=modern
DisableProgramGroupPage=yes
LicenseFile=
InfoBeforeFile=

[Files]
Source: "dist\DiskPilot.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "diskpilot.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\DiskPilot"; Filename: "{app}\DiskPilot.exe"; IconFilename: "{app}\diskpilot.ico"
Name: "{autodesktop}\DiskPilot"; Filename: "{app}\DiskPilot.exe"; IconFilename: "{app}\diskpilot.ico"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create desktop shortcut"; GroupDescription: "Additional icons:"

[Run]
Filename: "{app}\DiskPilot.exe"; Description: "Launch DiskPilot"; Flags: postinstall nowait skipifsilent
