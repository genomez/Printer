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
REPORT_USTREAMER_PORT="8080"
REPORT_USTREAMER_RESOLUTION="1920x1080"
REPORT_USTREAMER_FPS="30"
REPORT_AUTO_RESTART_INTERVAL="30"


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


def install_ustreamer() -> None:
    global REPORT_INSTALL_STATUS
    log_action("Installing ustreamer...")

    # Stop existing service/process to avoid "Text file busy" on replace
    run("/etc/init.d/ustreamer stop 2>/dev/null || true")
    run("killall ustreamer 2>/dev/null || true")

    if run_ok("/etc/init.d/cron enable"):
        log_service("cron service enabled")
    else:
        log_error("Failed to enable cron service")

    # Copy ustreamer binary to system
    repo_root = Path(__file__).resolve().parent.parent
    binary_src = repo_root / "binaries" / "ustreamer_static_arm32"
    binary_dst = Path("/usr/local/bin/ustreamer")
    
    try:
        # Create directory if it doesn't exist
        binary_dst.parent.mkdir(parents=True, exist_ok=True)

        # Copy to a temporary path, chmod, then atomically replace to avoid busy-text errors
        tmp_path = binary_dst.parent / "ustreamer.new"
        shutil.copy2(binary_src, tmp_path)
        os.chmod(tmp_path, 0o755)
        os.replace(tmp_path, binary_dst)
        log_action("Installed ustreamer binary to /usr/local/bin/ustreamer (atomic replace)")

        # Test binary
        if run_ok("/usr/local/bin/ustreamer --help"):
            REPORT_INSTALL_STATUS = "ustreamer installed successfully"
        else:
            log_error("ustreamer binary test failed")
            REPORT_INSTALL_STATUS = "ustreamer installation failed"

    except Exception as e:
        log_error(f"Failed to install ustreamer binary: {e}")
        REPORT_INSTALL_STATUS = "ustreamer installation failed"


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

    # Disable old mjpg_streamer if present
    if Path("/etc/init.d/mjpg_streamer").exists():
        try:
            run("/etc/init.d/mjpg_streamer stop")
            run("/etc/init.d/mjpg_streamer disable")
            log_action("Stopped and disabled old mjpg_streamer service")
            log_service("mjpg_streamer service stopped and disabled")
        except Exception:
            pass


def create_ustreamer_service() -> None:
    log_action("Creating ustreamer service...")
    # Determine repo root from this script location
    repo_root = Path(__file__).resolve().parent.parent
    src = repo_root / "services" / "ustreamer"
    try:
        shutil.copyfile(src, "/etc/init.d/ustreamer")
        os.chmod("/etc/init.d/ustreamer", 0o755)
        log_action("Created ustreamer init script")
        log_service(f"ustreamer service created with auto-restart every {REPORT_AUTO_RESTART_INTERVAL} minutes")
    except Exception:
        log_error("Failed to create ustreamer init script")


def configure_services() -> None:
    log_action("Configuring services...")

    try:
        asvc_path = "/mnt/UDISK/printer_data/moonraker.asvc"
        existing = ""
        if Path(asvc_path).exists():
            with open(asvc_path, "r") as f:
                existing = f.read()
        if "\nustreamer\n" in f"\n{existing}\n":
            log_action("ustreamer already registered with Moonraker supervisor")
        else:
            with open(asvc_path, "a") as f:
                if not existing.endswith('\n'):
                    f.write('\n')
                f.write("ustreamer\n")
            log_action("Registered ustreamer with Moonraker supervisor")
            log_service("ustreamer registered with Moonraker")
    except Exception:
        log_error("Failed to register with Moonraker")

    if run_ok("/etc/init.d/ustreamer restart"):
        log_action("Started ustreamer service")
        log_service("ustreamer service started")
    else:
        log_error("Failed to start ustreamer service")

    if run_ok("/etc/init.d/ustreamer enable"):
        log_action("Enabled ustreamer service")
        log_service("ustreamer service enabled at boot")
    else:
        log_error("Failed to enable ustreamer service")


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
    good_stream = f'"stream_url"\s*:\s*"http://{target_ip}:8080/stream"' in json_response
    good_snap = f'"snapshot_url"\s*:\s*"http://{target_ip}:8080/snapshot"' in json_response
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
        "stream_url": f"http://{ip_address}:8080/stream",
        "snapshot_url": f"http://{ip_address}:8080/snapshot",
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
        "stream_url": f"http://{ip_address}:8080/stream",
        "snapshot_url": f"http://{ip_address}:8080/snapshot",
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
    print("         USTREAMER INSTALLATION COMPLETE")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("")

    if not REPORT_ERRORS:
        print(f"{GREEN}✓ Installation Status:{NC} {REPORT_INSTALL_STATUS}")

        if REPORT_BACKUPS_CREATED:
            print(f"{GREEN}✓ Backups:{NC}")
            for line in REPORT_BACKUPS_CREATED.strip().splitlines():
                print(f"    • {line}")

        # Service status
        if run("pidof ustreamer").returncode == 0:
            p = run("pidof ustreamer")
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
        print(f"  • Resolution: {REPORT_USTREAMER_RESOLUTION} @ {REPORT_USTREAMER_FPS} fps")
        print(f"  • Port: {REPORT_USTREAMER_PORT}")
        print(f"  • Auto-restart: Every {REPORT_AUTO_RESTART_INTERVAL} minutes")

        print("")
        print(f"{YELLOW}Access URLs:{NC}")
        print(f"  • Stream: http://{REPORT_IP}:{REPORT_USTREAMER_PORT}/stream")
        print(f"  • Snapshot: http://{REPORT_IP}:{REPORT_USTREAMER_PORT}/snapshot")

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
        if run("pidof ustreamer").returncode == 0:
            print(f"  {GREEN}✓{NC} ustreamer is running")
        else:
            print(f"  {RED}✗{NC} ustreamer is not running")

    # Always show configuration and URLs, regardless of errors
    print("")
    print(f"{YELLOW}Configuration:{NC}")
    print(f"  • Resolution: {REPORT_USTREAMER_RESOLUTION} @ {REPORT_USTREAMER_FPS} fps")
    print(f"  • Port: {REPORT_USTREAMER_PORT}")
    print(f"  • Auto-restart: Every {REPORT_AUTO_RESTART_INTERVAL} minutes")

    print("")
    print(f"{YELLOW}Access URLs:{NC}")
    print(f"  • Stream: http://{REPORT_IP}:{REPORT_USTREAMER_PORT}/stream")
    print(f"  • Snapshot: http://{REPORT_IP}:{REPORT_USTREAMER_PORT}/snapshot")

    print("")
    print(f"{YELLOW}Quick Commands:{NC}")
    print("  • Status: /etc/init.d/ustreamer status")
    print("  • Logs: tail -f /var/log/ustreamer.log")
    print("  • Restart: /etc/init.d/ustreamer restart")
    print("")


def main() -> None:
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("         USTREAMER INSTALLATION STARTING")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("")

    global REPORT_IP
    REPORT_IP = get_ip_address()
    print(f"System IP: {REPORT_IP}")
    print("")

    install_ustreamer()
    backup_and_disable_services()
    create_ustreamer_service()
    configure_services()
    manage_camera(REPORT_IP)
    restart_moonraker()
    print_final_report()


if __name__ == "__main__":
    if os.geteuid() != 0:
        print("ERROR: This script must be run as root", file=sys.stderr)
        sys.exit(1)
    main()
