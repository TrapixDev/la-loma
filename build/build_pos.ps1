# Genera el .exe (PyInstaller) y el instalador setup.exe (Inno Setup).
# Requiere:  python -m pip install -r requirements.txt pyinstaller
#            Inno Setup 6 (ISCC.exe) en %ProgramFiles(x86)%\Inno Setup 6
# Uso:       powershell -ExecutionPolicy Bypass -File build\build_pos.ps1
# Salida:    dist\PosLaLoma_Setup_1.0.2.exe

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Version = "1.0.2"
$Name = "PosLaLoma"
$Assets = Join-Path $Root "build\assets"
$Icon = Join-Path $Assets "icon.ico"

# ---------- 1) Pruebas ----------
Write-Host "== Ejecutando tests =="
python -m tests.run_all
if ($LASTEXITCODE -ne 0) { throw "Los tests fallaron; no se compila." }

# ---------- 1b) Auditoría de dependencias (opcional, no bloquea) ----------
python -m pip_audit --version *> $null
if ($LASTEXITCODE -eq 0) {
    Write-Host "== Auditoría de dependencias (pip-audit) =="
    python -m pip_audit -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "pip-audit reportó vulnerabilidades; revise antes de publicar."
    }
} else {
    Write-Host "pip-audit no está instalado; se omite la auditoría (pip install pip-audit)."
}

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

# ---------- 2b) Herramientas que viajan en el instalador ----------
$Herramientas = Join-Path $Root "dist\$Name\herramientas"
New-Item -ItemType Directory -Path $Herramientas -Force | Out-Null
Copy-Item (Join-Path $Root "build\firewall_pos.ps1") $Herramientas -Force

# El logo del ticket viaja junto al .exe (el POS lo usa en el encabezado).
$Logo = Join-Path $Root "logo-colegio.png"
if (Test-Path $Logo) {
    Copy-Item $Logo (Join-Path $Root "dist\$Name") -Force
}

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

# ---------- 4) Firma del setup (si existe la clave privada) ----------
$Firma = Join-Path $env:APPDATA "PosLaLoma\updates\update-signing.key"
$Setup = Join-Path $Root "dist\PosLaLoma_Setup_$Version.exe"
if (Test-Path $Firma) {
    Write-Host "== Firmando el setup =="
    python (Join-Path $Root "tools\firmar_setup.py") $Setup --key $Firma
    if ($LASTEXITCODE -ne 0) { Write-Warning "No se pudo firmar el setup." }
} else {
    Write-Host "Sin clave de firma (tools\generar_claves_update.py); el setup queda sin firmar."
}

Write-Host ""
Write-Host "Listo: dist\PosLaLoma_Setup_$Version.exe"
