# Guía de Despliegue - Reporte Tickets GLPI

## Requisitos Previos

1. **En tu máquina local (Windows):**
   - PowerShell
   - OpenSSH instalado (generalmente viene con Windows 10/11) O PuTTY instalado
   - Archivo `.env` configurado con las credenciales

2. **En el servidor (Linux):**
   - Acceso SSH al servidor `10.48.12.63`
   - Usuario: `aplicaciones`
   - Contraseña: `Cpgretail01`
   - Python3 instalado
   - Permisos para crear directorios y archivos en `/home/aplicaciones/reporte_tickets_monitor`

## Información del Servidor

- **Servidor:** 10.48.12.63
- **Usuario:** aplicaciones
- **Contraseña:** Cpgretail01
- **Ruta de despliegue:** /home/aplicaciones/reporte_tickets_monitor

## Pasos de Despliegue

### Paso 1: Preparar archivos localmente

Asegúrate de tener estos archivos en el directorio del proyecto:
- `main.py`
- `config.py`
- `glpi_db.py`
- `charts.py`
- `monitor.py`
- `telegram_client.py`
- `test_local.py`
- `requirements.txt`
- `.env` (con tus credenciales)
- `deploy.ps1` o `deploy_with_putty.ps1` (script de transferencia)
- `deploy_server.sh` (script de configuración)

### Paso 2: Transferir archivos al servidor

**Opción A: Usando PowerShell con OpenSSH (recomendado si OpenSSH está instalado)**

Abre PowerShell en el directorio del proyecto y ejecuta:

```powershell
.\deploy.ps1
```

Este script:
- Verifica que existe el archivo `.env`
- Verifica la conexión al servidor
- Transfiere todos los archivos necesarios a `/home/aplicaciones/reporte_tickets_monitor`
- Te pedirá ingresar la contraseña cuando se solicite

**Opción B: Usando PowerShell con PuTTY (automático, sin pedir contraseña)**

Si tienes PuTTY instalado (plink/pscp), usa:

```powershell
.\deploy_with_putty.ps1
```

Este script:
- Usa PuTTY para transferencias automáticas
- No requiere ingresar contraseña manualmente
- Puede ejecutar el script de configuración automáticamente

**Opción C: Manual con WinSCP o FileZilla**

Ejecuta `deploy_simple.bat` para ver instrucciones, o:
1. Abre WinSCP/FileZilla
2. Conecta a: `aplicaciones@10.48.12.63`
3. Contraseña: `Cpgretail01`
4. Navega a: `/home/aplicaciones/reporte_tickets_monitor`
5. Transfiere: `main.py`, `requirements.txt`, `.env`, `deploy_server.sh`

**Opción C: Manual con WinSCP o FileZilla**

Ejecuta `deploy_simple.bat` para ver instrucciones, o:
1. Abre WinSCP/FileZilla
2. Conecta a: `aplicaciones@10.48.12.63`
3. Contraseña: `Cpgretail01`
4. Navega a: `/home/aplicaciones/reporte_tickets_monitor`
5. Transfiere: `main.py`, `requirements.txt`, `.env`, `deploy_server.sh`

### Paso 3: Configurar en el servidor

Conéctate al servidor:

```bash
ssh aplicaciones@10.48.12.63
# Contraseña: Cpgretail01
```

Navega al directorio y ejecuta el script de configuración:

```bash
cd ~/reporte_tickets_monitor
bash deploy_server.sh
```

El script de configuración:
- Crea el entorno virtual
- Instala las dependencias
- Crea el directorio de logs
- Configura permisos
- Prueba la ejecución del script
- Opcionalmente configura Cron o Systemd

### Paso 4: Verificar funcionamiento

**Probar manualmente:**
```bash
cd ~/reporte_tickets_monitor
source venv/bin/activate
python3 main.py
```

Presiona `Ctrl+C` después de verificar que funciona.

**Ver logs:**
```bash
# Si usas Cron
tail -f ~/reporte_tickets_monitor/logs/cron.log

# Si usas Systemd
sudo journalctl -u reporte-tickets.service -f
```

## Reporte de tickets: mensajes, gráfica y envío por integrante

El script envía **siempre un resumen al grupo** con el total y el desglose por
técnico, y además un **mensaje privado a cada integrante** con sus casos (si su
`chat_id` está configurado).

### Separación de reportes (sin datos duplicados)
- `Vencidos`: el ticket ya pasó su `time_to_resolve`.
- `Próximos a vencer`: aún vigentes y faltan `NEAR_DUE_HOURS` horas o menos.
- `Al 70%`: consumieron ≥70% del tiempo y les resta **más** que `NEAR_DUE_HOURS`.

Son mutuamente excluyentes: un ticket aparece en un solo bloque.

### Configurar los privados (chat_id por técnico)
En `.env`:
```
TG_MEMBERS=jperez:123456789,mlopez:987654321
```
También se acepta JSON (`{"jperez":"123456789"}`) o un archivo
`telegram_members.json` en la carpeta del proyecto (ver
`telegram_members.json.example`). La clave es el **login de GLPI** (recomendado)
o el nombre del técnico. Los técnicos sin `chat_id` se listan en el resumen del
grupo con ⚠️.

> Para que un técnico reciba su privado debe haber iniciado un chat con el bot
> al menos una vez (Telegram no permite escribir primero a un usuario).

### Gráfica PNG (opcional)
Con `SEND_CHART=1` (o sin `--no-chart`) se genera una imagen con barras por
técnico y una dona de totales, y se envía al grupo. Requiere `matplotlib`
(incluido en `requirements.txt`). Si no está instalado, el reporte textual
sigue enviándose normalmente.

### Monitor de Ventas EPA (SV con doble refresh)
Al final del ciclo, si no se usa `--no-monitor`, se consulta el Monitor de Ventas
por país vía su **API REST** (igual que `reporte_joseph`) y se envía al grupo el
total de ventas por país + un screenshot. La UI se abre con Playwright y se
refresca `config.COUNTRIES[país]["refresh_count"]` veces; **SV usa 2 refresh**
porque la herramienta no renderiza bien a la primera. La API requiere
`MONITOR_API_PASS` definida en `.env`. Si Playwright no está instalado, los datos
por API siguen funcionando (solo se omite el screenshot).

### Flags útiles de `main.py`
```bash
python main.py --once --dry-run        # imprime todo sin enviar (prueba)
python main.py --mock --dry-run        # datos simulados, sin BD ni red
python main.py --no-chart              # sin gráfica PNG
python main.py --only SV               # solo el Monitor de un país
python main.py --no-monitor            # solo los reportes GLPI
python main.py --inspect               # vuelca HTML/screenshots del Monitor
python main.py --test-chat 12345       # envía todo a un chat de prueba
```

## Estructura Final en el Servidor

```
/home/aplicaciones/reporte_tickets_monitor/
├── main.py
├── config.py
├── glpi_db.py
├── charts.py
├── monitor.py
├── telegram_client.py
├── requirements.txt
├── .env
├── deploy_server.sh
├── telegram_members.json (opcional: mapeo login -> chat_id)
├── venv/
│   └── (entorno virtual con dependencias)
├── salidas/
│   └── YYYY-MM-DD/ (gráficas PNG generadas)
└── logs/
    ├── cron.log (si usas Cron)
    ├── service.log (si usas Systemd)
    └── service_error.log (si usas Systemd)
```

## Configuración de Ejecución Automática

### Opción 1: Cron (Recomendado para ejecución cada hora)

El script `deploy_server.sh` puede configurar Cron automáticamente. Si prefieres hacerlo manualmente:

```bash
crontab -e
```

Agregar esta línea:
```
0 * * * * cd /home/aplicaciones/reporte_tickets_monitor && /home/aplicaciones/reporte_tickets_monitor/venv/bin/python3 /home/aplicaciones/reporte_tickets_monitor/main.py >> /home/aplicaciones/reporte_tickets_monitor/logs/cron.log 2>&1
```

### Opción 2: Systemd (Servicio continuo)

El script `deploy_server.sh` puede configurar Systemd automáticamente. Si prefieres hacerlo manualmente:

```bash
sudo nano /etc/systemd/system/reporte-tickets.service
```

Pegar el contenido del servicio (ver `deploy_server.sh` para el contenido completo).

Luego:
```bash
sudo systemctl daemon-reload
sudo systemctl enable reporte-tickets.service
sudo systemctl start reporte-tickets.service
```

## Comandos Útiles

### Ver estado del servicio (Systemd)
```bash
sudo systemctl status reporte-tickets.service
```

### Ver logs en tiempo real (Systemd)
```bash
sudo journalctl -u reporte-tickets.service -f
```

### Ver crontab
```bash
crontab -l
```

### Ver logs de Cron
```bash
tail -f ~/reporte_tickets_monitor/logs/cron.log
```

### Reiniciar servicio (Systemd)
```bash
sudo systemctl restart reporte-tickets.service
```

### Detener servicio (Systemd)
```bash
sudo systemctl stop reporte-tickets.service
```

## Solución de Problemas

### Error: "No se puede conectar al servidor"
- Verifica que el servidor esté accesible: `ping 10.48.12.63`
- Verifica que SSH esté habilitado en el servidor
- Verifica las credenciales de acceso

### Error: "Python3 no está instalado"
- Instala Python3: `sudo yum install python3` (RedHat/CentOS) o `sudo apt-get install python3` (Debian/Ubuntu)

### Error: "Permission denied"
- Verifica permisos del directorio: `ls -la ~/reporte_tickets_monitor`
- Ajusta permisos si es necesario: `chmod 755 ~/reporte_tickets_monitor`

### El script no envía mensajes a Telegram
- Verifica que el archivo `.env` tenga las credenciales correctas
- Verifica que el bot de Telegram esté configurado correctamente
- Revisa los logs para ver errores específicos

## Actualización del Código

Para actualizar el código después de cambios:

1. Modifica los archivos localmente
2. Ejecuta `deploy.ps1` nuevamente para transferir los archivos
3. En el servidor, solo necesitas reiniciar el servicio o esperar a la próxima ejecución de Cron

Si usas Systemd:
```bash
sudo systemctl restart reporte-tickets.service
```

