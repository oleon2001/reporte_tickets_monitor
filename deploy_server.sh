#!/bin/bash

# Script de despliegue - Configuración en el servidor
# Ejecutar en el servidor después de transferir los archivos

set -e  # Salir si hay algún error

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Directorio del proyecto
PROJECT_DIR="/home/aplicaciones/reporte_tickets_monitor"
VENV_DIR="$PROJECT_DIR/venv"
LOGS_DIR="$PROJECT_DIR/logs"

echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}Configuración del Servidor - Reporte Tickets${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""

# Verificar que estamos en el directorio correcto
if [ ! -f "$PROJECT_DIR/main.py" ]; then
    echo -e "${RED}ERROR: No se encontró main.py en $PROJECT_DIR${NC}"
    echo -e "${YELLOW}Asegúrate de estar en el directorio correcto o que los archivos fueron transferidos.${NC}"
    exit 1
fi

cd "$PROJECT_DIR"

# Verificar que existe .env
if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo -e "${RED}ERROR: No se encontró el archivo .env${NC}"
    echo -e "${YELLOW}Por favor, asegúrate de que el archivo .env fue transferido.${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Archivos encontrados${NC}"
echo ""

# Verificar Python3
echo -e "${YELLOW}Verificando Python3...${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}ERROR: Python3 no está instalado${NC}"
    exit 1
fi

PYTHON_VERSION=$(python3 --version)
echo -e "${GREEN}✓ $PYTHON_VERSION encontrado${NC}"
echo ""

# Crear entorno virtual
echo -e "${YELLOW}Creando entorno virtual...${NC}"
if [ -d "$VENV_DIR" ]; then
    echo -e "${YELLOW}El entorno virtual ya existe. ¿Deseas recrearlo? (s/n)${NC}"
    read -r response
    if [[ "$response" =~ ^[Ss]$ ]]; then
        rm -rf "$VENV_DIR"
        python3 -m venv "$VENV_DIR"
        echo -e "${GREEN}✓ Entorno virtual recreado${NC}"
    else
        echo -e "${GREEN}✓ Usando entorno virtual existente${NC}"
    fi
else
    python3 -m venv "$VENV_DIR"
    echo -e "${GREEN}✓ Entorno virtual creado${NC}"
fi
echo ""

# Activar entorno virtual e instalar dependencias
echo -e "${YELLOW}Instalando dependencias...${NC}"
source "$VENV_DIR/bin/activate"
pip install --upgrade pip > /dev/null 2>&1
pip install -r "$PROJECT_DIR/requirements.txt"
echo -e "${GREEN}✓ Dependencias instaladas${NC}"
echo ""

# Crear directorio de logs
echo -e "${YELLOW}Creando directorio de logs...${NC}"
mkdir -p "$LOGS_DIR"
echo -e "${GREEN}✓ Directorio de logs creado${NC}"
echo ""

# Verificar permisos
echo -e "${YELLOW}Ajustando permisos...${NC}"
chmod +x "$PROJECT_DIR/main.py"
chmod 600 "$PROJECT_DIR/.env"  # Proteger archivo .env
echo -e "${GREEN}✓ Permisos configurados${NC}"
echo ""

# Probar ejecución del script
echo -e "${YELLOW}Probando ejecución del script (5 segundos)...${NC}"
timeout 5 "$VENV_DIR/bin/python3" "$PROJECT_DIR/main.py" > /dev/null 2>&1 || true
echo -e "${GREEN}✓ Script ejecutado correctamente${NC}"
echo ""

# Configurar Cron
echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}Configuración de Cron${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""
echo -e "${YELLOW}¿Deseas configurar Cron para ejecutar el script cada 6 horas? (s/n)${NC}"
read -r response

if [[ "$response" =~ ^[Ss]$ ]]; then
    CRON_JOB="0 */6 * * * cd $PROJECT_DIR && $VENV_DIR/bin/python3 $PROJECT_DIR/main.py --once >> $LOGS_DIR/cron.log 2>&1"
    
    # Verificar si ya existe el cron job
    if crontab -l 2>/dev/null | grep -q "$PROJECT_DIR/main.py"; then
        echo -e "${YELLOW}Ya existe un cron job para este script.${NC}"
        echo -e "${YELLOW}¿Deseas reemplazarlo? (s/n)${NC}"
        read -r replace_response
        if [[ "$replace_response" =~ ^[Ss]$ ]]; then
            # Remover el cron job existente
            crontab -l 2>/dev/null | grep -v "$PROJECT_DIR/main.py" | crontab -
            # Agregar el nuevo
            (crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -
            echo -e "${GREEN}✓ Cron job actualizado${NC}"
        else
            echo -e "${YELLOW}Cron job no modificado${NC}"
        fi
    else
        (crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -
        echo -e "${GREEN}✓ Cron job configurado${NC}"
    fi
    
    echo ""
    echo -e "${CYAN}Cron jobs actuales:${NC}"
    crontab -l
    echo ""
fi

# Opción de Systemd
echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}Configuración de Systemd (Opcional)${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""
echo -e "${YELLOW}¿Deseas configurar Systemd como servicio? (s/n)${NC}"
read -r systemd_response

if [[ "$systemd_response" =~ ^[Ss]$ ]]; then
    SERVICE_FILE="/etc/systemd/system/reporte-tickets.service"
    
    if [ -f "$SERVICE_FILE" ]; then
        echo -e "${YELLOW}El servicio ya existe. ¿Deseas reemplazarlo? (s/n)${NC}"
        read -r replace_service
        if [[ ! "$replace_service" =~ ^[Ss]$ ]]; then
            echo -e "${YELLOW}Servicio no modificado${NC}"
        fi
    fi
    
    if [[ ! -f "$SERVICE_FILE" ]] || [[ "$replace_service" =~ ^[Ss]$ ]]; then
        sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=Reporte Tickets GLPI - Ejecución cada 6 horas
After=network.target

[Service]
Type=simple
User=aplicaciones
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$VENV_DIR/bin"
ExecStart=$VENV_DIR/bin/python3 $PROJECT_DIR/main.py
Restart=always
RestartSec=3600
StandardOutput=append:$LOGS_DIR/service.log
StandardError=append:$LOGS_DIR/service_error.log

[Install]
WantedBy=multi-user.target
EOF
        
        sudo systemctl daemon-reload
        sudo systemctl enable reporte-tickets.service
        sudo systemctl start reporte-tickets.service
        
        echo -e "${GREEN}✓ Servicio Systemd configurado e iniciado${NC}"
        echo ""
        echo -e "${CYAN}Comandos útiles:${NC}"
        echo -e "  Ver estado: ${YELLOW}sudo systemctl status reporte-tickets.service${NC}"
        echo -e "  Ver logs: ${YELLOW}sudo journalctl -u reporte-tickets.service -f${NC}"
        echo -e "  Reiniciar: ${YELLOW}sudo systemctl restart reporte-tickets.service${NC}"
        echo ""
    fi
fi

# Resumen final
echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}Despliegue Completado${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""
echo -e "${GREEN}✓ Configuración completada exitosamente${NC}"
echo ""
echo -e "${CYAN}Información del despliegue:${NC}"
echo -e "  Directorio: ${YELLOW}$PROJECT_DIR${NC}"
echo -e "  Entorno virtual: ${YELLOW}$VENV_DIR${NC}"
echo -e "  Logs: ${YELLOW}$LOGS_DIR${NC}"
echo ""
echo -e "${CYAN}Comandos útiles:${NC}"
echo -e "  Ejecutar manualmente: ${YELLOW}cd $PROJECT_DIR && source venv/bin/activate && python3 main.py${NC}"
echo -e "  Ver logs de cron: ${YELLOW}tail -f $LOGS_DIR/cron.log${NC}"
echo -e "  Ver crontab: ${YELLOW}crontab -l${NC}"
echo ""
echo -e "${GREEN}¡Listo para usar!${NC}"
echo ""

