; Inno Setup 6 Script for PDF Image Extractor
; Copyright (C) Mitsuie. All rights reserved.

#define MyAppName "PDF Image Extractor"
#define MyAppPublisher "Mitsuie"
#define MyAppURL "https://github.com/Mitsuie/pdf-image-extractor"
#define MyAppExeName "PDFImageExtractor.exe"

#ifndef MyAppVersion
#define MyAppVersion "1.1.0"
#endif

[Setup]
; AppId uniquely identifies this application. Do not use the same AppId in other installers.
AppId={{E68A8D2A-94B5-4D6C-81F8-6A2CEB701D29}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputBaseFilename=PDFImageExtractor_Setup_v{#MyAppVersion}
OutputDir=dists
Compression=lzma2/ultra
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dists\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
