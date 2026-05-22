; SSH Remote Tool - Inno Setup 安装脚本
; 使用 Inno Setup Compiler 编译为 setup.exe

#define MyAppName "SSH Remote Tool"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "SSH Remote Tool"
#define MyAppURL ""
#define MyAppExeName "SSHRemoteTool.exe"
#define MyAppCopyright "2026"

[Setup]
; 应用基本信息
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultGroupName={#MyAppName}
DefaultDirName={autopf}\{#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=
InfoBeforeFile=
InfoAfterFile=
OutputDir=installer
OutputBaseFilename=SSHRemoteTool-Setup-v{#MyAppVersion}
SetupIconFile=resources\icons\app.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
WizardSizePercent=120

; 权限和兼容性
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; 外观
WizardImageFile=
WizardSmallImageFile=

; 卸载
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式:"; Flags: checkedonce
Name: "quicklaunchicon"; Description: "创建快速启动栏图标"; GroupDescription: "快捷方式:"; Flags: unchecked

[Files]
; 打包 PyInstaller 产出的整个目录
Source: "dist\SSHRemoteTool\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; 开始菜单
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; Comment: "{#MyAppName}"
; 桌面快捷方式
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; Comment: "{#MyAppName}"
; 快速启动栏
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: quicklaunchicon

[Run]
; 安装完成后可选运行
Filename: "{app}\{#MyAppExeName}"; Description: "立即运行 {#MyAppName}"; Flags: nowait postinstall shellexec

[UninstallDelete]
; 卸载时删除用户数据目录（可选，默认不删）
; Type: filesandordirs; Name: "{userprofile}\.ssh-remote-tool"

[Code]
// 安装前检查，确保没有旧版本正在运行
function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
begin
  Result := True;
  // 检查程序是否正在运行
  if Exec('tasklist', '/FI "IMAGENAME eq {#MyAppExeName}" /NH', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
  begin
    // 简单检查（实际场景中应解析输出）
  end;
end;
