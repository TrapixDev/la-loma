# Genera el .exe (PyInstaller) y el instalador setup.exe (Inno Setup).
# Requiere:  python -m pip install -r requirements.txt pyinstaller
#            Inno Setup 6 (ISCC.exe) en %ProgramFiles(x86)%\Inno Setup 6
# Uso:       powershell -ExecutionPolicy Bypass -File build\build_pos.ps1
# Salida:    dist\PosLaLoma_Setup_1.0.0.exe

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Version = "1.0.0"
$Name = "PosLaLoma"
$Assets = Join-Path $Root "build\assets"
$Icon = Join-Path $Assets "icon.ico"

# ---------- 1) Pruebas ----------
Write-Host "== Ejecutando tests =="
python -m tests.run_all
if ($LASTEXITCODE -ne 0) { throw "Los tests fallaron; no se compila." }

# ---------- 2) PyInstaller (onedir, sin consola) ----------
Write-Host "== PyInstaller =="
Remove-Item -LiteralPath (Join-Path $Root "build\$Name") -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath (Join-Path $Root "dist\$Name") -Recurse -Force -ErrorAction SilentlyContinue

python -m PyInstaller --clean --noconfirm `
    --onedir --windowed `
    --name $Name `
    --icon $Icon `
    --version-file (Join-Path $Root "build\version_info.txt") `
    --paths $Root `
    main.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller falló." }

# ---------- 3) Inno Setup ----------
Write-Host "== Inno Setup =="
$iscc = Get-ChildItem "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
                      "${env:ProgramFiles}\Inno Setup 6\ISCC.exe",
                      "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" -ErrorAction SilentlyContinue |
        Select-Object -First 1
if (-not $iscc) {
    Write-Warning "Inno Setup no está instalado. El .exe quedó en dist\$Name\PosLaLoma.exe"
    Write-Warning "Instale Inno Setup 6 y vuelva a correr este script para generar el setup."
    exit 0
}

& $iscc.FullName (Join-Path $Root "build\PosLaLoma.iss") /DVersion=$Version /DOutput=$Root
if ($LASTEXITCODE -ne 0) { throw "Inno Setup falló." }

Write-Host ""
Write-Host "Listo: dist\PosLaLoma_Setup_$Version.exe"
