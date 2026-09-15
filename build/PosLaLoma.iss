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

[Messages]
FinishedLabel=La instalación de POS La Loma finalizó.%n%nSi Windows o el antivirus bloquean el POS:%n  1) Clic derecho al instalador > Propiedades > marque "Desbloquear" y vuelva a ejecutarlo.%n  2) Si SmartScreen lo bloquea: "Más información" > "Ejecutar de todas formas".%n  3) En Seguridad de Windows agregue una exclusión (Protección antivirus > Exclusiones) para la carpeta del programa y para AppData\Roaming\PosLaLoma.%n%nSi algo falla, entre a Configuración > "Probar instalación" y copie el diagnóstico.

[Code]
function InitializeSetup(): Boolean;
var
  Version: TWindowsVersion;
begin
  GetWindowsVersionEx(Version);
  if Version.Major < 10 then
  begin
    MsgBox('POS La Loma requiere Windows 10 o superior.' + #13#10 +
           'Este equipo tiene una versión anterior de Windows.',
           mbCriticalError, MB_OK);
    Result := False;
    Exit;
  end;
  Result := True;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  { Cierra la app y su servidor local (--server) para poder reemplazar los
    archivos; si no se cierran, quedarían bloqueando la instalación. }
  Exec('taskkill.exe', '/F /IM PosLaLoma.exe', '', SW_HIDE,
       ewWaitUntilTerminated, ResultCode);
  Sleep(500);
  Result := '';
end;

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
