; Inno Setup script del POS La Loma
; Compila: ISCC.exe PosLaLoma.iss /DVersion=1.0.0 /DOutput=E:\ruta
; Instala por usuario (%LOCALAPPDATA%\Programs\PosLaLoma) para que las
; actualizaciones no pidan permisos de administrador.

#ifndef Version
  #define Version "1.0.0"
#endif
#ifndef Output
  #define Output "."
#endif
#define AppName "POS La Loma"
#define AppId "{{7F3A1C2E-9B4D-4E6F-8A1B-2C3D4E5F6A7B}}"
#define SrcDir "..\dist\PosLaLoma"

[Setup]
AppId={#AppId}
AppName={#AppName}
AppVersion={#Version}
AppVerName={#AppName} {#Version}
AppPublisher=POS La Loma
VersionInfoVersion={#Version}
VersionInfoDescription=POS La Loma - Punto de Venta
DefaultDirName={localappdata}\Programs\PosLaLoma
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir={#Output}\dist
OutputBaseFilename=PosLaLoma_Setup_{#Version}
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\PosLaLoma.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
AppMutex=PosLaLomaMutex

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el escritorio"; GroupDescription: "Accesos directos:"

[Files]
Source: "{#SrcDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\PosLaLoma.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\PosLaLoma.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\PosLaLoma.exe"; Description: "Iniciar {#AppName} ahora"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; No se borran los datos del usuario (%APPDATA%\PosLaLoma) al desinstalar.
