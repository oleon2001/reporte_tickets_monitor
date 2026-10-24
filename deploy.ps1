# Script de despliegue - Transferir archivos al servidor
# Ejecutar desde PowerShell en Windows

$SERVER = "10.48.12.63"
$USER = "aplicaciones"
$PASSWORD = "Cpgretail01"
$REMOTE_PATH = "/home/aplicaciones/reporte_tickets_monitor"
$LOCAL_PATH = $PSScriptRoot

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Script de Despliegue - Reporte Tickets" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Verificar que existe el archivo .env
if (-Not (Test-Path "$LOCAL_PATH\.env")) {
    Write-Host "ERROR: No se encontró el archivo .env" -ForegroundColor Red
    Write-Host "Por favor, asegúrate de que el archivo .env existe en el directorio actual." -ForegroundColor Yellow
    exit 1
}

$FILES = @(
    "main.py",
    "config.py",
    "glpi_db.py",
    "charts.py",
    "monitor.py",
    "telegram_client.py",
    "test_local.py",
    "requirements.txt",
    ".env",
    "deploy_server.sh"
)

Write-Host "Archivos a transferir:" -ForegroundColor Green
foreach ($f in $FILES) { Write-Host "  - $f" -ForegroundColor White }
Write-Host ""

# Verificar conexión SSH
Write-Host "Verificando conexión al servidor..." -ForegroundColor Yellow
$testConnection = Test-Connection -ComputerName $SERVER -Count 1 -Quiet
if (-Not $testConnection) {
    Write-Host "ERROR: No se puede conectar al servidor $SERVER" -ForegroundColor Red
    exit 1
}

Write-Host "Conexión exitosa. Transfiriendo archivos..." -ForegroundColor Green
Write-Host ""

# Función para ejecutar comando SSH con contraseña
function Invoke-SSHWithPassword {
    param(
        [string]$Command,
        [string]$Server,
        [string]$User,
        [string]$Password
    )
    
    # Intentar usar plink (PuTTY) si está disponible
    $plinkPath = Get-Command plink -ErrorAction SilentlyContinue
    if ($plinkPath) {
        $plinkPath = $plinkPath.Source
        $echo = $Password | & $plinkPath -ssh "${User}@${Server}" -pw $Password $Command
        return $echo
    }
    
    # Si no hay plink, usar OpenSSH (pedirá contraseña manualmente)
    Write-Host "Nota: Se te pedirá ingresar la contraseña: $Password" -ForegroundColor Yellow
    ssh "${User}@${Server}" $Command
}

# Función para transferir archivo con SCP y contraseña
function Invoke-SCPWithPassword {
    param(
        [string]$LocalFile,
        [string]$RemotePath,
        [string]$Server,
        [string]$User,
        [string]$Password
    )
    
    # Intentar usar pscp (PuTTY) si está disponible
    $pscpPath = Get-Command pscp -ErrorAction SilentlyContinue
    if ($pscpPath) {
        $pscpPath = $pscpPath.Source
        & $pscpPath -pw $Password "$LocalFile" "${User}@${Server}:${RemotePath}"
        return $true
    }
    
    # Si no hay pscp, usar OpenSSH (pedirá contraseña manualmente)
    Write-Host "Nota: Se te pedirá ingresar la contraseña: $Password" -ForegroundColor Yellow
    scp "$LocalFile" "${User}@${Server}:${RemotePath}"
    return $true
}

# Transferir archivos usando SCP
try {
    # Crear directorio remoto si no existe
    Write-Host "Creando directorio remoto..." -ForegroundColor Yellow
    Invoke-SSHWithPassword -Command "mkdir -p $REMOTE_PATH" -Server $SERVER -User $USER -Password $PASSWORD
    
    # Transferir archivos
    foreach ($f in $FILES) {
        Write-Host "Transfiriendo $f..." -ForegroundColor Yellow
        Invoke-SCPWithPassword -LocalFile "$LOCAL_PATH\$f" -RemotePath "$REMOTE_PATH/" -Server $SERVER -User $USER -Password $PASSWORD
    }
    
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "Archivos transferidos exitosamente!" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Siguiente paso:" -ForegroundColor Cyan
    Write-Host "1. Conéctate al servidor: ssh ${USER}@${SERVER}" -ForegroundColor White
    Write-Host "   Contraseña: $PASSWORD" -ForegroundColor Gray
    Write-Host "2. Navega al directorio: cd $REMOTE_PATH" -ForegroundColor White
    Write-Host "3. Ejecuta el script de configuración: bash deploy_server.sh" -ForegroundColor White
    Write-Host ""
    Write-Host "Nota: Si prefieres automatizar la conexión SSH, instala PuTTY (plink/pscp)" -ForegroundColor Yellow
    Write-Host "      desde https://www.putty.org/ para transferencias automáticas sin pedir contraseña." -ForegroundColor Yellow
    Write-Host ""
    
} catch {
    Write-Host ""
    Write-Host "ERROR durante la transferencia: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "Alternativa manual:" -ForegroundColor Yellow
    Write-Host "Si SCP no está disponible, puedes usar WinSCP, FileZilla u otro cliente SFTP" -ForegroundColor White
    Write-Host "para transferir los archivos a: ${USER}@${SERVER}:${REMOTE_PATH}" -ForegroundColor White
    exit 1
}

