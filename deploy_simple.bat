@echo off
REM Script de despliegue simple usando WinSCP o manual
REM Alternativa si PowerShell no funciona

echo ========================================
echo Script de Despliegue - Reporte Tickets
echo ========================================
echo.

set SERVER=10.48.12.63
set USER=aplicaciones
set PASSWORD=Cpgretail01
set REMOTE_PATH=/home/aplicaciones/reporte_tickets_monitor

echo Servidor: %SERVER%
echo Usuario: %USER%
echo Ruta remota: %REMOTE_PATH%
echo.

REM Verificar que existe .env
if not exist ".env" (
    echo ERROR: No se encontro el archivo .env
    echo Por favor, asegurate de que el archivo .env existe en el directorio actual.
    pause
    exit /b 1
)

echo Archivos a transferir:
echo   - main.py
echo   - config.py
echo   - glpi_db.py
echo   - charts.py
echo   - monitor.py
echo   - telegram_client.py
echo   - test_local.py
echo   - requirements.txt
echo   - .env
echo   - deploy_server.sh
echo.

echo ========================================
echo INSTRUCCIONES MANUALES
echo ========================================
echo.
echo Opcion 1: Usar WinSCP
echo   1. Abre WinSCP
echo   2. Conecta a: %USER%@%SERVER%
echo   3. Contrasena: %PASSWORD%
echo   4. Navega a: %REMOTE_PATH%
echo   5. Transfiere los archivos listados arriba
echo.
echo Opcion 2: Usar PowerShell
echo   1. Abre PowerShell en este directorio
echo   2. Ejecuta: .\deploy.ps1
echo.
echo Opcion 3: Usar PuTTY (si esta instalado)
echo   1. Abre PowerShell en este directorio
echo   2. Ejecuta: .\deploy_with_putty.ps1
echo.
echo Despues de transferir los archivos:
echo   1. Conectate al servidor: ssh %USER%@%SERVER%
echo   2. Contrasena: %PASSWORD%
echo   3. Navega: cd %REMOTE_PATH%
echo   4. Ejecuta: bash deploy_server.sh
echo.

pause

