#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
import shutil
import socket
import subprocess
from pathlib import Path
from urllib import request, parse, error

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

REPORT_INSTALL_STATUS=""
REPORT_BACKUPS_CREATED=""
REPORT_SERVICES_CONFIGURED=""
REPORT_ERRORS=""
REPORT_IP=""
REPORT_CAMERAS=""
REPORT_CAMERA_ACTIONS=""
REPORT_CAMERA_STATUS=""
REPORT_MJPG_PORT="8080"
REPORT_MJPG_RESOLUTION="1920x1080"
REPORT_MJPG_FPS="10"
REPORT_AUTO_RESTART_INTERVAL="15"


def log_action(msg: str) -> None:
    print(msg)


def log_error(msg: str) -> None:
    global REPORT_ERRORS
    sys.stderr.write(f"{RED}ERROR: {msg}{NC}\n")
    REPORT_ERRORS += f"{msg}\n"


def log_backup(msg: str) -> None:
    global REPORT_BACKUPS_CREATED
    REPORT_BACKUPS_CREATED += f"{msg}\n"


def log_service(msg: str) -> None:
    global REPORT_SERVICES_CONFIGURED
    REPORT_SERVICES_CONFIGURED += f"{msg}\n"


def run(cmd: str) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, shell=True, text=True, capture_output=True)


def run_ok(cmd: str) -> bool:
    r = run(cmd)
    if r.returncode != 0:
        return False
    return True


def install_mjpg_streamer() -> None:
    global REPORT_INSTALL_STATUS
    log_action("Installing mjpg_streamer...")

    if run_ok("/etc/init.d/cron enable"):
        log_service("cron service enabled")
    else:
        log_error("Failed to enable cron service")

    log_action("Updating package list...")
    if run_ok("opkg update"):
        log_action("Installing mjpg_streamer packages...")
        if run_ok("opkg install mjpg-streamer mjpg-streamer-input-uvc mjpg-streamer-output-http mjpg-streamer-www"):
            REPORT_INSTALL_STATUS = "mjpg_streamer installed successfully"
        else:
            log_error("Failed to install mjpg_streamer packages")
            REPORT_INSTALL_STATUS = "mjpg_streamer installation failed"
    else:
        log_error("Failed to update package list")
        REPORT_INSTALL_STATUS = "Package update failed"

    # Remove old Optware init script if present
    if Path("/opt/etc/init.d/S99mjpg_streamer").exists():
        try:
            Path("/opt/etc/init.d/S99mjpg_streamer").unlink()
            log_action("Removed old Optware init script")
        except Exception:
            pass


def backup_and_disable_services() -> None:
    log_action("Backing up and disabling conflicting services...")

    # webrtc_local
    if Path("/usr/bin/webrtc_local").exists():
        if not Path("/usr/bin/webrtc_local.bak").exists():
            try:
                shutil.copy2("/usr/bin/webrtc_local", "/usr/bin/webrtc_local.bak")
                log_backup("Backed up /usr/bin/webrtc_local → /usr/bin/webrtc_local.bak")
            except Exception:
                pass
        else:
            log_backup("/usr/bin/webrtc_local.bak already exists (skipped)")

        try:
            os.replace("/usr/bin/webrtc_local", "/usr/bin/webrtc_local.disabled")
            log_action("Disabled webrtc_local")
            log_service("webrtc_local disabled (was using port 8000)")
        except Exception:
            pass

        run("killall webrtc_local 2>/dev/null || true")

    # cam_app
    if Path("/usr/bin/cam_app").exists():
        if not Path("/usr/bin/cam_app.backup").exists():
            try:
                shutil.copy2("/usr/bin/cam_app", "/usr/bin/cam_app.backup")
                log_backup("Backed up /usr/bin/cam_app → /usr/bin/cam_app.backup")
            except Exception:
                pass
        else:
            log_backup("/usr/bin/cam_app.backup already exists (skipped)")

        try:
            os.replace("/usr/bin/cam_app", "/usr/bin/cam_app.orig")
            with open("/usr/bin/cam_app", "w") as f:
                f.write("#!/bin/sh\nexit 0\n")
            os.chmod("/usr/bin/cam_app", 0o755)
            log_action("Replaced cam_app with dummy script")
            log_service("cam_app replaced with dummy (prevents camera conflicts)")
        except Exception:
            pass


def create_mjpg_streamer_service() -> None:
    log_action("Creating mjpg_streamer service...")

    init_content = r'''#!/bin/sh /etc/rc.common
# Tunables
VIDEO_DEV="/dev/video0"
RESOLUTION="1920x1080"
FPS="10"
PORT="8080"
WWW_DIR="/opt/share/www_mjpg-streamer"
BIN="/opt/bin/mjpg_streamer"
LD_LIBRARY_PATH="/opt/lib/mjpg-streamer"
RESTART_INTERVAL="15"
DEDICATED_LOG="/var/log/mjpg_streamer.log"
MAX_LOG_SIZE="1048576"

START=99
STOP=10
USE_PROCD=1
EXTRA_COMMANDS="status restart_service_only"
EXTRA_HELP="    status                Show mjpg_streamer status
    restart_service_only  Restart service without touching cron job"
TAG="mjpg_streamer"
CRON_COMMENT="# mjpg_streamer auto-restart"
AUTO_RESTART_FLAG="/tmp/.mjpg_streamer_auto_restart"

tstamp() { TZ=PST8PDT date '+%Y-%m-%d %I:%M:%S %p %Z'; }
log() {
    local msg="[$(tstamp)] $*"
    echo "$msg"
    logger -t "$TAG" "$*"
    echo "$msg" >> "$DEDICATED_LOG"
    
    if [ -f "$DEDICATED_LOG" ] && [ "$(stat -c%s "$DEDICATED_LOG" 2>/dev/null || echo 0)" -gt "$MAX_LOG_SIZE" ]; then
        mv "$DEDICATED_LOG" "${DEDICATED_LOG}.old"
        echo "[$(tstamp)] Log rotated due to size limit" > "$DEDICATED_LOG"
    fi
}

setup_auto_restart() {
    if [ "$RESTART_INTERVAL" -gt 0 ] 2>/dev/null; then
        if ! crontab -l 2>/dev/null | grep -q "$CRON_COMMENT"; then
            log "Setting up auto-restart every $RESTART_INTERVAL minutes"
            {
                crontab -l 2>/dev/null
                echo "*/$RESTART_INTERVAL * * * * /etc/init.d/mjpg_streamer restart_service_only $CRON_COMMENT"
            } | crontab -
            log "Auto-restart scheduled every $RESTART_INTERVAL minutes"
        else
            log "Auto-restart already configured ($RESTART_INTERVAL min intervals)"
        fi
    else
        log "Auto-restart disabled (RESTART_INTERVAL=$RESTART_INTERVAL)"
    fi
}

remove_auto_restart() {
    if crontab -l 2>/dev/null | grep -q "$CRON_COMMENT"; then
        crontab -l 2>/dev/null | grep -v "$CRON_COMMENT" | crontab -
        log "Auto-restart cron job removed"
    fi
}

start_service() {
    local is_auto_restart=0
    [ -f "$AUTO_RESTART_FLAG" ] && is_auto_restart=1
    
    if [ "$is_auto_restart" -eq 1 ]; then
        log "=== mjpg_streamer auto-restart requested ==="
    else
        log "=== mjpg_streamer start requested ==="
    fi
    
    mkdir -p "$(dirname "$DEDICATED_LOG")"
    
    for i in $(seq 1 30); do
        [ -x "$BIN" ] && break
        log "Waiting for $BIN ($i/30)..."
        sleep 1
    done
    [ -x "$BIN" ] || { log "FATAL: $BIN not found"; return 1; }
    
    [ -c "$VIDEO_DEV" ] || { log "FATAL: $VIDEO_DEV missing"; return 1; }
    
    if fuser "$VIDEO_DEV" 2>/dev/null | grep -q '[0-9]'; then
        log "$VIDEO_DEV busy -- attempting graceful termination"
        fuser -k -TERM "$VIDEO_DEV" 2>/dev/null || true
        sleep 2
        
        if fuser "$VIDEO_DEV" 2>/dev/null | grep -q '[0-9]'; then
            log "$VIDEO_DEV STILL BUSY -- FORCE KILL"
            fuser -k -9 "$VIDEO_DEV" 2>/dev/null || true
            sleep 1
        else
            log "Camera released gracefully"
        fi
    fi
    
    CMD="$BIN -i \"input_uvc.so -d $VIDEO_DEV -r $RESOLUTION -f $FPS\" \\
-o \"output_http.so -p $PORT -w $WWW_DIR\""
    log "Launching: $CMD"
    
    procd_open_instance
    procd_set_param pidfile /var/run/mjpg_streamer.pid
    procd_set_param env LD_LIBRARY_PATH="$LD_LIBRARY_PATH"
    procd_set_param command \\
        $BIN \\
        -i "input_uvc.so -d $VIDEO_DEV -r $RESOLUTION -f $FPS" \\
        -o "output_http.so -p $PORT -w $WWW_DIR"
    procd_set_param file "$VIDEO_DEV"
    procd_set_param respawn 3600 5 5
    procd_set_param stdout 1
    procd_set_param stderr 1
    procd_close_instance
    log "mjpg_streamer handed off to procd (respawn enabled)"
    
    if [ "$is_auto_restart" -eq 0 ]; then
        setup_auto_restart
    fi
    
    rm -f "$AUTO_RESTART_FLAG"
}

stop_service() {
    local is_auto_restart=0
    [ -f "$AUTO_RESTART_FLAG" ] && is_auto_restart=1
    
    log "Stopping mjpg_streamer"
    
    if [ "$is_auto_restart" -eq 0 ]; then
        remove_auto_restart
    fi
}

restart_service_only() {
    log "=== mjpg_streamer auto-restart triggered ==="
    touch "$AUTO_RESTART_FLAG"
    /etc/init.d/mjpg_streamer restart
}

status() {
    if pidof mjpg_streamer >/dev/null; then
        echo "running";  logger -t "$TAG" "queried status: running"
        echo "[$(tstamp)] Status queried: running" >> "$DEDICATED_LOG"
        echo "PID: $(pidof mjpg_streamer)"
        
        local cam_users=$(fuser "$VIDEO_DEV" 2>/dev/null)
        [ -n "$cam_users" ] && echo "Camera users: $cam_users"
        
        if crontab -l 2>/dev/null | grep -q "$CRON_COMMENT"; then
            echo "auto-restart: enabled ($RESTART_INTERVAL min intervals)"
        else
            echo "auto-restart: disabled"
        fi
        
        if [ -f "$DEDICATED_LOG" ]; then
            echo "dedicated log: $DEDICATED_LOG ($(stat -c%s "$DEDICATED_LOG" 2>/dev/null || echo 0) bytes)"
        fi
    else
        echo "stopped"; logger -t "$TAG" "queried status: stopped"
        echo "[$(tstamp)] Status queried: stopped" >> "$DEDICATED_LOG"
    fi
}
'''

    try:
        with open("/etc/init.d/mjpg_streamer", "w") as f:
            f.write(init_content)
        os.chmod("/etc/init.d/mjpg_streamer", 0o755)
        log_action("Created mjpg_streamer init script")
        log_service(f"mjpg_streamer service created with auto-restart every {REPORT_AUTO_RESTART_INTERVAL} minutes")
    except Exception:
        log_error("Failed to set permissions on mjpg_streamer init script")


def configure_services() -> None:
    log_action("Configuring services...")

    try:
        with open("/mnt/UDISK/printer_data/moonraker.asvc", "a") as f:
            f.write("\nmjpg_streamer\n")
        log_action("Registered mjpg_streamer with Moonraker supervisor")
        log_service("mjpg_streamer registered with Moonraker")
    except Exception:
        log_error("Failed to register with Moonraker")

    if run_ok("/etc/init.d/mjpg_streamer restart"):
        log_action("Started mjpg_streamer service")
        log_service("mjpg_streamer service started")
    else:
        log_error("Failed to start mjpg_streamer service")

    if run_ok("/etc/init.d/mjpg_streamer enable"):
        log_action("Enabled mjpg_streamer service")
        log_service("mjpg_streamer service enabled at boot")
    else:
        log_error("Failed to enable mjpg_streamer service")


def get_ip_address() -> str:
    # Same behavior as shell: try best effort
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        pass
    return "127.0.0.1"


def http_get(url: str) -> tuple[int, str]:
    try:
        with request.urlopen(url, timeout=3) as resp:
            return resp.getcode(), resp.read().decode("utf-8", "ignore")
    except Exception:
        return 0, ""


def http_post(url: str, data: dict) -> int:
    try:
        data_bytes = json.dumps(data).encode("utf-8")
        req = request.Request(url, data=data_bytes, headers={"Content-Type": "application/json"}, method="POST")
        with request.urlopen(req, timeout=3) as resp:
            return resp.getcode()
    except error.HTTPError as e:
        return e.code
    except Exception:
        return 0


def http_delete(url: str) -> int:
    try:
        req = request.Request(url, method="DELETE")
        with request.urlopen(req, timeout=3) as resp:
            return resp.getcode()
    except error.HTTPError as e:
        return e.code
    except Exception:
        return 0


def get_existing_cameras(ip_address: str) -> str:
    code, body = http_get(f"http://{ip_address}:7125/server/webcams/list")
    if code and body and '"webcams"' in body:
        return body
    return ""


def check_camera_exists(json_response: str, target_ip: str) -> bool:
    return f"{target_ip}:8080" in json_response


def extract_camera_name(json_response: str) -> str:
    import re
    m = re.search(r'"name"\s*:\s*"([^"]*)"', json_response)
    return m.group(1) if m else ""


def check_camera_configured_correctly(json_response: str, target_ip: str) -> bool:
    good_stream = f'"stream_url"\s*:\s*"http://{target_ip}:8080/?action=stream"' in json_response
    good_snap = f'"snapshot_url"\s*:\s*"http://{target_ip}:8080/?action=snapshot"' in json_response
    good_service = '"service"\s*:\s*"mjpegstreamer"' in json_response
    return good_stream and good_snap and good_service


def extract_camera_details_for_report(json_response: str) -> None:
    global REPORT_CAMERAS
    import re
    name = extract_camera_name(json_response)
    m_service = re.search(r'"service"\s*:\s*"([^"]*)"', json_response)
    m_enabled = re.search(r'"enabled"\s*:\s*([^,}]*)', json_response)
    service = m_service.group(1) if m_service else ""
    enabled = (m_enabled.group(1).strip() if m_enabled else "").replace('true', 'True').replace('false','False')
    REPORT_CAMERAS = f"NAME:{name}|SERVICE:{service}|ENABLED:{enabled}"


def delete_camera(ip_address: str, camera_name: str) -> bool:
    encoded_name = parse.quote(camera_name)
    code = http_delete(f"http://{ip_address}:7125/server/webcams/item?name={encoded_name}")
    if code in (200, 204):
        log_action(f"  • Deleted camera: {camera_name}")
        global REPORT_CAMERA_ACTIONS
        REPORT_CAMERA_ACTIONS += f"Deleted camera: {camera_name}\n"
        return True
    return False


def update_camera(ip_address: str, camera_name: str) -> bool:
    encoded_name = parse.quote(camera_name)
    payload = {
        "name": camera_name,
        "service": "mjpegstreamer",
        "stream_url": f"http://{ip_address}:8080/?action=stream",
        "snapshot_url": f"http://{ip_address}:8080/?action=snapshot",
    }
    code = http_post(f"http://{ip_address}:7125/server/webcams/item?name={encoded_name}", payload)
    if code in (200, 201):
        log_action(f"  • Updated camera: {camera_name}")
        global REPORT_CAMERA_ACTIONS
        REPORT_CAMERA_ACTIONS += f"Updated camera: {camera_name}\n"
        return True
    return False


def create_camera(ip_address: str) -> bool:
    payload = {
        "name": "Front",
        "service": "mjpegstreamer",
        "stream_url": f"http://{ip_address}:8080/?action=stream",
        "snapshot_url": f"http://{ip_address}:8080/?action=snapshot",
    }
    code = http_post(f"http://{ip_address}:7125/server/webcams/item", payload)
    if code in (200, 201):
        log_action("  • Camera created successfully")
        global REPORT_CAMERA_ACTIONS, REPORT_CAMERA_STATUS
        REPORT_CAMERA_ACTIONS += "Created new camera: Front\n"
        REPORT_CAMERA_STATUS = "configured"
        return True
    else:
        log_error(f"Failed to create camera (HTTP {code})")
        REPORT_CAMERA_STATUS = "error"
        return False


def manage_camera(ip_address: str) -> None:
    log_action("Configuring Moonraker webcam...")
    log_action("Checking for existing cameras...")

    resp = get_existing_cameras(ip_address)
    if not resp:
        log_action("  • No response from server, creating new camera...")
        create_camera(ip_address)
        return

    if check_camera_exists(resp, ip_address):
        name = extract_camera_name(resp) or "Front"
        log_action(f"  • Found camera: {name}")
        extract_camera_details_for_report(resp)
        if check_camera_configured_correctly(resp, ip_address):
            log_action("  • Configuration is correct, no changes needed")
            global REPORT_CAMERA_STATUS
            REPORT_CAMERA_STATUS = "already_configured"
        else:
            log_action("  • Configuration needs updating...")
            if update_camera(ip_address, name):
                REPORT_CAMERA_STATUS = "updated"
            else:
                if delete_camera(ip_address, name):
                    create_camera(ip_address)
    else:
        log_action("  • No camera found for this IP, creating new one...")
        create_camera(ip_address)


def restart_moonraker() -> None:
    log_action("Restarting Moonraker service...")
    if run_ok("/etc/init.d/moonraker restart"):
        log_action("Moonraker service restarted successfully")
        log_service("Moonraker service restarted")
    else:
        log_error("Failed to restart Moonraker")


def print_final_report() -> None:
    print("")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("         MJPG STREAMER INSTALLATION COMPLETE")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("")

    if not REPORT_ERRORS:
        print(f"{GREEN}✓ Installation Status:{NC} {REPORT_INSTALL_STATUS}")

        if REPORT_BACKUPS_CREATED:
            print(f"{GREEN}✓ Backups:{NC}")
            for line in REPORT_BACKUPS_CREATED.strip().splitlines():
                print(f"    • {line}")

        # Service status
        if run("pidof mjpg_streamer").returncode == 0:
            p = run("pidof mjpg_streamer")
            pid = p.stdout.strip()
            print(f"{GREEN}✓ Service Status:{NC} Running (PID: {pid}") if pid else print(f"{GREEN}✓ Service Status:{NC} Running")
        else:
            print(f"{RED}✗ Service Status:{NC} Not running")

        # Camera status
        if REPORT_CAMERA_STATUS == "already_configured":
            print(f"{GREEN}✓ Camera:{NC} Already configured")
        elif REPORT_CAMERA_STATUS in ("configured", "updated"):
            print(f"{GREEN}✓ Camera:{NC} Configured successfully")
        else:
            print(f"{RED}✗ Camera:{NC} Configuration failed")

        print("")
        print(f"{YELLOW}Configuration:{NC}")
        print(f"  • Resolution: {REPORT_MJPG_RESOLUTION} @ {REPORT_MJPG_FPS} fps")
        print(f"  • Port: {REPORT_MJPG_PORT}")
        print(f"  • Auto-restart: Every {REPORT_AUTO_RESTART_INTERVAL} minutes")

        print("")
        print(f"{YELLOW}Access URLs:{NC}")
        print(f"  • Stream: http://{REPORT_IP}:{REPORT_MJPG_PORT}/?action=stream")
        print(f"  • Snapshot: http://{REPORT_IP}:{REPORT_MJPG_PORT}/?action=snapshot")

    else:
        print(f"{RED}⚠ ERRORS ENCOUNTERED{NC}")
        print("")
        if REPORT_INSTALL_STATUS:
            print(f"Installation: {REPORT_INSTALL_STATUS}")
        print("")
        print(f"{RED}Errors:{NC}")
        for line in REPORT_ERRORS.strip().splitlines():
            print(f"  • {line}")
        print("")
        print("Despite errors, attempting to show current status:")
        if run("pidof mjpg_streamer").returncode == 0:
            print(f"  {GREEN}✓{NC} mjpg_streamer is running")
        else:
            print(f"  {RED}✗{NC} mjpg_streamer is not running")

    print("")
    print(f"{YELLOW}Quick Commands:{NC}")
    print("  • Status: /etc/init.d/mjpg_streamer status")
    print("  • Logs: tail -f /var/log/mjpg_streamer.log")
    print("  • Restart: /etc/init.d/mjpg_streamer restart")
    print("")


def main() -> None:
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("         MJPG STREAMER INSTALLATION STARTING")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("")

    global REPORT_IP
    REPORT_IP = get_ip_address()
    print(f"System IP: {REPORT_IP}")
    print("")

    install_mjpg_streamer()
    backup_and_disable_services()
    create_mjpg_streamer_service()
    configure_services()
    manage_camera(REPORT_IP)
    restart_moonraker()
    print_final_report()


if __name__ == "__main__":
    if os.geteuid() != 0:
        print("ERROR: This script must be run as root", file=sys.stderr)
        sys.exit(1)
    main()
