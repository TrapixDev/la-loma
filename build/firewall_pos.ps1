# Crea la regla de Firewall de Windows para el servidor POS, limitada a la
# red local (nunca acepta conexiones desde Internet).
#
# Uso (como Administrador):
#   powershell -ExecutionPolicy Bypass -File build\firewall_pos.ps1
#   powershell -ExecutionPolicy Bypass -File build\firewall_pos.ps1 -Puerto 8000

param([int]$Puerto = 8000)

$ErrorActionPreference = "Stop"
$Regla = "POS La Loma"

if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "Este script requiere una consola de Administrador." -ForegroundColor Yellow
    exit 1
}

netsh advfirewall firewall delete rule name="$Regla" | Out-Null
netsh advfirewall firewall add rule `
    name="$Regla" `
    dir=in action=allow protocol=TCP localport=$Puerto `
    remoteip=LocalSubnet profile=private,domain | Out-Null

if ($LASTEXITCODE -ne 0) {
    Write-Host "No se pudo crear la regla de firewall." -ForegroundColor Red
    exit 1
}

Write-Host "Regla creada: acepta TCP $Puerto solo desde la red local ($Regla)."
Write-Host "Verificar con:  netsh advfirewall firewall show rule name=`"$Regla`""
