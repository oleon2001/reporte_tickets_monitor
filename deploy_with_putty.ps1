# Script de despliegue usando PuTTY (plink/pscp)
# Requiere PuTTY instalado: https://www.putty.org/
# Si PuTTY no está instalado, usa deploy.ps1 en su lugar

$SERVER = "10.48.12.63"
$USER = "aplicaciones"
$PASSWORD = "Cpgretail01"
$REMOTE_PATH = "/home/aplicaciones/reporte_tickets_monitor"
$LOCAL_PATH = $PSScriptRoot

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Script de Despliegue - Reporte Tickets" -ForegroundColor Cyan
Write-Host "Usando PuTTY (plink/pscp)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Verificar que existe el archivo .env
if (-Not (Test-Path "$LOCAL_PATH\.env")) {
    Write-Host "ERROR: No se encontró el archivo .env" -ForegroundColor Red
    Write-Host "Por favor, asegúrate de que el archivo .env existe en el directorio actual." -ForegroundColor Yellow
    exit 1
}

# Buscar plink y pscp
$plinkPath = Get-Command plink -ErrorAction SilentlyContinue
$pscpPath = Get-Command pscp -ErrorAction SilentlyContinue

if (-Not $plinkPath -Or -Not $pscpPath) {
    Write-Host "ERROR: PuTTY no está instalado o no está en el PATH" -ForegroundColor Red
    Write-Host ""
    Write-Host "Opciones:" -ForegroundColor Yellow
    Write-Host "1. Instalar PuTTY desde: https://www.putty.org/" -ForegroundColor White
    Write-Host "2. Agregar PuTTY al PATH del sistema" -ForegroundColor White
    Write-Host "3. Usar deploy.ps1 en su lugar (pedirá contraseña manualmente)" -ForegroundColor White
    exit 1
}

$plink = $plinkPath.Source
$pscp = $pscpPath.Source

Write-Host "PuTTY encontrado:" -ForegroundColor Green
Write-Host "  plink: $plink" -ForegroundColor White
Write-Host "  pscp: $pscp" -ForegroundColor White
Write-Host ""

# Verificar conexión SSH
Write-Host "Verificando conexión al servidor..." -ForegroundColor Yellow
$testResult = & $plink -ssh "${USER}@${SERVER}" -pw $PASSWORD "echo 'Conexion exitosa'" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: No se puede conectar al servidor $SERVER" -ForegroundColor Red
    Write-Host "Verifica la conexión y las credenciales." -ForegroundColor Yellow
    exit 1
}

Write-Host "Conexión exitosa. Transfiriendo archivos..." -ForegroundColor Green
Write-Host ""

try {
    # Crear directorio remoto si no existe
    Write-Host "Creando directorio remoto..." -ForegroundColor Yellow
    & $plink -ssh "${USER}@${SERVER}" -pw $PASSWORD "mkdir -p $REMOTE_PATH" | Out-Null
    
    # Transferir archivos
    $FILES = @(
        "main.py", "config.py", "glpi_db.py", "charts.py", "monitor.py",
        "telegram_client.py", "test_local.py",
        "requirements.txt", ".env", "deploy_server.sh"
    )
    foreach ($f in $FILES) {
        Write-Host "Transfiriendo $f..." -ForegroundColor Yellow
        & $pscp -pw $PASSWORD "$LOCAL_PATH\$f" "${USER}@${SERVER}:${REMOTE_PATH}/" | Out-Null
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
    
    # Opción para ejecutar el script de configuración automáticamente
    Write-Host "¿Deseas ejecutar el script de configuración ahora? (s/n)" -ForegroundColor Yellow
    $response = Read-Host
    if ($response -eq "s" -or $response -eq "S") {
        Write-Host ""
        Write-Host "Ejecutando script de configuración en el servidor..." -ForegroundColor Yellow
        Write-Host "Nota: El script puede hacer preguntas interactivas." -ForegroundColor Gray
        Write-Host ""
        & $plink -ssh "${USER}@${SERVER}" -pw $PASSWORD "cd $REMOTE_PATH && bash deploy_server.sh"
    }
    
} catch {
    Write-Host ""
    Write-Host "ERROR durante la transferencia: $_" -ForegroundColor Red
    exit 1
}

