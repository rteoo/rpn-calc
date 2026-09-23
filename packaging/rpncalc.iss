; Inno Setup script for rpn-calc
; Build with: iscc.exe packaging/rpncalc.iss

#define MyAppName "RPN Calc"
#define MyAppVersion "0.6.3"
#define MyAppPublisher "Rodrigo Teodoro"
#define MyAppURL "https://github.com/rteoo/rpn-calc"
#define MyAppExeName "rpncalc.exe"
#define SourceDir "..\dist\rpncalc"

[Setup]
AppId={{1F4D4FB5-E8B1-4B5F-A5B7-3C8D9E2F5A1B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE
OutputBaseFilename=rpncalc-{#MyAppVersion}-installer
OutputDir=..\dist
SetupIconFile=..\src\rpncalc\icons\rpncalc.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=force
AllowUNCPath=no
MinVersion=10.0.17763
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
UsePreviousAppDir=yes
UsePreviousGroup=no
UsePreviousTasks=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked; OnlyBelowVersion: 6.1,6.1
Name: "startmenu"; Description: "Create Start Menu shortcut"; GroupDescription: "{cm:AdditionalIcons}"
Name: "associatecalckey"; Description: "Bind Windows Calculator key"; GroupDescription: "Windows integration"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion

[InstallDelete]
; Shortcuts left by releases named "rpn-calc".
Type: filesandordirs; Name: "{autoprograms}\rpn-calc"
Type: files; Name: "{autodesktop}\rpn-calc.lnk"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\rpncalc.exe"; Comment: "HP 50g-style RPN calculator"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\rpncalc.exe"; Tasks: desktopicon; Comment: "HP 50g-style RPN calculator"
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\rpncalc.exe"; Tasks: quicklaunchicon; Comment: "HP 50g-style RPN calculator"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent; Check: not AssociateCalcKey

[Code]
function AssociateCalcKey: Boolean;
begin
  Result := WizardIsTaskSelected('associatecalckey');
  if Result then
  begin
    RegWriteStringValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Explorer\AppKey\18', 'ShellExecute', ExpandConstant('"{app}\rpncalc.exe"'));
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  UninstallKey: string;
begin
  if CurStep = ssPostInstall then
  begin
    UninstallKey := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#SetupSetting("AppId")}';
    if (GetWindowsVersion >= $0A000E) then
    begin
      RegWriteStringValue(HKEY_LOCAL_MACHINE, UninstallKey, 'DisplayVersion', '{#MyAppVersion}');
    end;
  end;
end;
