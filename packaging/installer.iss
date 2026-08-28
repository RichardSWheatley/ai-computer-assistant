; RITA modular installer (Inno Setup).
; Build:  ISCC packaging\installer.iss   (after pyinstaller packaging\rita.spec)

#define AppName "RITA"
#ifndef AppVersion
#define AppVersion "0.12.0"
#endif

[Setup]
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Methodical EP
DefaultDirName={autopf}\RITA
DefaultGroupName=RITA
OutputBaseFilename=RITA-Setup-{#AppVersion}
OutputDir=..\dist\installer
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
UninstallDisplayName={#AppName}
ArchitecturesInstallIn64BitMode=x64compatible

[Types]
Name: "full"; Description: "Full installation"
Name: "custom"; Description: "Custom installation"; Flags: iscustom

[Components]
Name: "core"; Description: "RITA core + GUI (required)"; Types: full custom; Flags: fixed
Name: "voice"; Description: "Voice modules (wake word, speech in/out)"; Types: full
Name: "mcpserve"; Description: "Workspace MCP server (coder-worker integration)"; Types: full
Name: "mod_runner"; Description: "Module: zephyr-runner (build/twister/flash)"; Types: full
Name: "mod_coder"; Description: "Module: coder-worker (the coding agent)"; Types: full
Name: "mod_scaffold"; Description: "Module: scaffold (application authoring)"; Types: full
Name: "mod_cerberus"; Description: "Module: CERBERUS static gate (downloads only if not already on this machine; needs git)"; Types: full
Name: "mod_joulescope"; Description: "Module: joulescope (stub until bench milestone)"; Types: full

[Files]
Source: "..\dist\RITA\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion; Components: core

[Icons]
Name: "{group}\RITA"; Filename: "{app}\RitaApp.exe"
Name: "{autodesktop}\RITA"; Filename: "{app}\RitaApp.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop icon"; GroupDescription: "Additional icons:"

[Run]
; Module registration = manifest writing into %USERPROFILE%\.rita\modules
; (the registry's native install mechanism). Only the selected components.
Filename: "{app}\rita.exe"; Parameters: "modules install --only {code:SelectedModules}"; \
    Flags: runhidden; StatusMsg: "Registering capability modules..."
; Downloads run ONLY when the tool isn't already in ~/.rita — an update
; install keeps what the user has (the Modules page updates on demand).
Filename: "{app}\rita.exe"; Parameters: "cerberus install"; Components: mod_cerberus; \
    Check: not CerberusPresent; \
    Flags: runhidden; StatusMsg: "Downloading CERBERUS (static gate)..."
Filename: "{app}\rita.exe"; Parameters: "unity install"; \
    Check: not UnityPresent; \
    Flags: runhidden; StatusMsg: "Downloading Unity (unit-test framework)..."
Filename: "{app}\RitaApp.exe"; Description: "Launch RITA"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
; App only — ~/.rita user data (config, boards, modules, task history) survives.

[Code]
function RitaHome: string;
begin
  Result := ExpandConstant('{%USERPROFILE}') + '\.rita';
end;

{ Same file the app's own detection checks — never a guess. }
function CerberusPresent: Boolean;
begin
  Result := FileExists(RitaHome + '\cerberus\cerberus\cli.py');
end;

function UnityPresent: Boolean;
begin
  Result := FileExists(RitaHome + '\unity\src\unity.c')
    or FileExists(RitaHome + '\unity\unity.c')
    or FileExists(RitaHome + '\cerberus\unity\src\unity.c')
    or FileExists(RitaHome + '\cerberus\unity\unity.c');
end;

function SelectedModules(Param: string): string;
var
  names: string;
begin
  names := '';
  if WizardIsComponentSelected('mod_runner') then names := names + 'zephyr-runner,';
  if WizardIsComponentSelected('mod_coder') then names := names + 'coder-worker,';
  if WizardIsComponentSelected('mod_scaffold') then names := names + 'scaffold,';
  if WizardIsComponentSelected('voice') then names := names + 'voice-in,voice-out,';
  if WizardIsComponentSelected('mod_cerberus') then names := names + 'cerberus,';
  if WizardIsComponentSelected('mod_joulescope') then names := names + 'joulescope,';
  if names = '' then names := 'scaffold,';
  Result := Copy(names, 1, Length(names) - 1);
end;
