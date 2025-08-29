#!/usr/bin/env python3

import os
import sys
import shutil
import argparse
from pathlib import Path

# Configuration
CONFIG_DIR = "/mnt/UDISK/printer_data/config"
CUSTOM_CONFIG_DIR = "/mnt/UDISK/printer_data/config/custom"
KLIPPER_EXTRAS_DIR = "/usr/share/klipper/klippy/extras"
INIT_D_DIR = "/etc/init.d"
MOONRAKER_ASVC_FILE = "/mnt/UDISK/printer_data/moonraker.asvc"

def log(message, level="INFO"):
    print(f"[{level}] {message}")

def check_file_exists(path):
    return os.path.exists(path)

def check_dir_exists(path):
    return os.path.isdir(path)

def verify_kamp():
    """Verify KAMP installation"""
    all_good = True
    
    kamp_dir = Path(CONFIG_DIR) / "KAMP"
    kamp_cfg = Path(CONFIG_DIR) / "KAMP_Settings.cfg"
    
    if check_dir_exists(kamp_dir):
        log("✓ KAMP directory verified")
    else:
        log("✗ KAMP directory not found", "ERROR")
        all_good = False

    if check_file_exists(kamp_cfg):
        log("✓ KAMP_Settings.cfg verified")
    else:
        log("✗ KAMP_Settings.cfg not found", "ERROR")
        all_good = False

    printer_cfg = Path(CONFIG_DIR) / "printer.cfg"
    if check_file_exists(printer_cfg):
        try:
            with open(printer_cfg, 'r') as f:
                content = f.read()
            if '[include KAMP_Settings.cfg]' in content:
                log("✓ KAMP_Settings.cfg included in printer.cfg")
            else:
                log("✗ KAMP_Settings.cfg not included in printer.cfg", "ERROR")
                all_good = False
        except Exception as e:
            log(f"Failed to read printer.cfg: {e}", "ERROR")
            all_good = False
    else:
        log("✗ printer.cfg not found", "ERROR")
        all_good = False
        
    return all_good

def verify_overrides():
    """Verify overrides installation"""
    overrides_path = Path(CUSTOM_CONFIG_DIR) / "overrides.cfg"
    if check_file_exists(overrides_path):
        log("✓ overrides.cfg verified")
        return True
    else:
        log("✗ overrides.cfg not found", "ERROR")
        return False

def verify_cleanup():
    """Verify cleanup service installation"""
    all_good = True
    
    service_path = Path(INIT_D_DIR) / "cleanup_printer_backups"
    if check_file_exists(service_path):
        log("✓ cleanup service file verified")
    else:
        log("✗ cleanup service file not found", "ERROR")
        all_good = False

    if check_file_exists(MOONRAKER_ASVC_FILE):
        try:
            with open(MOONRAKER_ASVC_FILE, 'r') as f:
                content = f.read()
            if 'cleanup_printer_backups' in content:
                log("✓ cleanup_printer_backups in moonraker.asvc")
            else:
                log("✗ cleanup_printer_backups not in moonraker.asvc", "ERROR")
                all_good = False
        except Exception as e:
            log(f"Failed to read moonraker.asvc: {e}", "ERROR")
            all_good = False
    else:
        log("✗ moonraker.asvc not found", "ERROR")
        all_good = False
        
    return all_good

def verify_resonance():
    """Verify resonance tester installation"""
    resonance_dst = Path(KLIPPER_EXTRAS_DIR) / "resonance_tester.py"
    if check_file_exists(resonance_dst):
        log("✓ resonance_tester.py verified")
        return True
    else:
        log("✗ resonance_tester.py not found", "ERROR")
        return False

def verify_bed_mesh():
    """Verify bed_mesh modification"""
    bed_mesh_path = Path(KLIPPER_EXTRAS_DIR) / "bed_mesh.py"
    if check_file_exists(bed_mesh_path):
        try:
            with open(bed_mesh_path, 'r') as f:
                content = f.read()
            if 'minval=1.' in content:
                log("✓ bed_mesh.py modification verified (minval=1.)")
                return True
            else:
                log("✗ bed_mesh.py modification not found (minval=1.)", "ERROR")
                return False
        except Exception as e:
            log(f"Failed to read bed_mesh.py: {e}", "ERROR")
            return False
    else:
        log("✗ bed_mesh.py not found", "ERROR")
        return False

def verify_timelapse():
    """Verify timelapse installation"""
    all_good = True
    
    timelapse_component = Path("/mnt/UDISK/root/moonraker/moonraker/components/timelapse.py")
    timelapse_cfg = Path(CONFIG_DIR) / "timelapse.cfg"
    
    if check_file_exists(timelapse_component):
        log("✓ timelapse.py component verified")
    else:
        log("✗ timelapse.py component not found", "ERROR")
        all_good = False

    if check_file_exists(timelapse_cfg):
        log("✓ timelapse.cfg verified")
    else:
        log("✗ timelapse.cfg not found", "ERROR")
        all_good = False

    printer_cfg = Path(CONFIG_DIR) / "printer.cfg"
    if check_file_exists(printer_cfg):
        try:
            with open(printer_cfg, 'r') as f:
                content = f.read()
            if '[include timelapse.cfg]' in content:
                log("✓ timelapse.cfg included in printer.cfg")
            else:
                log("✗ timelapse.cfg not included in printer.cfg", "ERROR")
                all_good = False
        except Exception as e:
            log(f"Failed to read printer.cfg: {e}", "ERROR")
            all_good = False
    else:
        log("✗ printer.cfg not found", "ERROR")
        all_good = False

    # Verify [timelapse] section in moonraker.conf
    moonraker_conf = Path(CONFIG_DIR) / "moonraker.conf"
    if check_file_exists(moonraker_conf):
        try:
            with open(moonraker_conf, 'r') as f:
                content = f.read()
            if '[timelapse]' in content:
                log("✓ [timelapse] section found in moonraker.conf")
            else:
                log("✗ [timelapse] section not found in moonraker.conf", "ERROR")
                all_good = False
        except Exception as e:
            log(f"Failed to read moonraker.conf: {e}", "ERROR")
            all_good = False
    else:
        log("✗ moonraker.conf not found", "ERROR")
        all_good = False
        
    return all_good

def verify_ustreamer():
    """Verify ustreamer installation (best-effort)"""
    candidates = [
        shutil.which("ustreamer"),
        "/usr/local/bin/ustreamer",
        "/usr/bin/ustreamer",
        "/bin/ustreamer",
        "/usr/sbin/ustreamer",
        "/sbin/ustreamer",
    ]
    found = any(check_file_exists(p) for p in candidates if p)
    if found:
        log("✓ ustreamer binary found")
        return True
    else:
        log("✗ ustreamer binary not found in PATH or standard locations", "ERROR")
        return False

def verify_mainsail():
    """Verify mainsail installation"""
    all_good = True
    
    # Check if mainsail directory exists
    mainsail_dir = "/mnt/UDISK/root/mainsail"
    if check_dir_exists(mainsail_dir):
        log("✓ mainsail directory found")
    else:
        log("✗ mainsail directory not found", "ERROR")
        all_good = False
    
    # Check if symlink exists
    symlink_path = "/usr/share/mainsail"
    if os.path.islink(symlink_path):
        log("✓ mainsail symlink found")
    else:
        log("✗ mainsail symlink not found", "ERROR")
        all_good = False
    
    # Check if nginx config was replaced
    nginx_conf = "/etc/nginx/nginx.conf"
    if check_file_exists(nginx_conf):
        try:
            with open(nginx_conf, 'r') as f:
                content = f.read()
            if 'mainsail' in content and '4409' in content:
                log("✓ nginx config contains mainsail configuration")
            else:
                log("✗ nginx config does not contain mainsail configuration", "ERROR")
                all_good = False
        except Exception as e:
            log(f"Failed to read nginx config: {e}", "ERROR")
            all_good = False
    else:
        log("✗ nginx config not found", "ERROR")
        all_good = False
    
    # Check if update manager is configured in moonraker.conf
    moonraker_conf = "/mnt/UDISK/printer_data/config/moonraker.conf"
    if check_file_exists(moonraker_conf):
        try:
            with open(moonraker_conf, 'r') as f:
                content = f.read()
            if '[update_manager mainsail]' in content:
                log("✓ [update_manager mainsail] found in moonraker.conf")
            else:
                log("✗ [update_manager mainsail] not found in moonraker.conf", "ERROR")
                all_good = False
        except Exception as e:
            log(f"Failed to read moonraker.conf: {e}", "ERROR")
            all_good = False
    else:
        log("✗ moonraker.conf not found", "ERROR")
        all_good = False
        
    return all_good

def verify_installation(components=None):
    """Verify that only the requested components were installed correctly"""
    # Default to all components if none provided
    if components is None:
        components = ['ustreamer', 'kamp', 'overrides', 'cleanup', 'resonance', 'bed_mesh', 'timelapse', 'mainsail']

    log("Verifying installation...")
    all_good = True

    # kamp verification
    if 'kamp' in components:
        if not verify_kamp():
            all_good = False

    # overrides verification
    if 'overrides' in components:
        if not verify_overrides():
            all_good = False

    # cleanup service verification
    if 'cleanup' in components:
        if not verify_cleanup():
            all_good = False

    # resonance tester verification
    if 'resonance' in components:
        if not verify_resonance():
            all_good = False

    # bed_mesh modification verification
    if 'bed_mesh' in components:
        if not verify_bed_mesh():
            all_good = False

    # timelapse verification
    if 'timelapse' in components:
        if not verify_timelapse():
            all_good = False

    # ustreamer verification (best-effort)
    if 'ustreamer' in components:
        if not verify_ustreamer():
            all_good = False

    # mainsail verification
    if 'mainsail' in components:
        if not verify_mainsail():
            all_good = False

    return all_good

def main():
    parser = argparse.ArgumentParser(description="Installation Verification Tool")
    parser.add_argument("--components", nargs="+", 
                       choices=['ustreamer', 'kamp', 'overrides', 'cleanup', 'resonance', 'bed_mesh', 'timelapse', 'timelapseh264', 'mainsail'],
                       help="Specific components to verify (default: all)")
    
    args = parser.parse_args()
    
    # Check if running as root
    if os.geteuid() != 0:
        log("This verification tool must be run as root (use sudo)", "ERROR")
        sys.exit(1)
    
    try:
        success = verify_installation(components=args.components)
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        log("Verification interrupted by user", "ERROR")
        sys.exit(1)
    except Exception as e:
        log(f"Verification failed with error: {e}", "ERROR")
        sys.exit(1)

if __name__ == "__main__":
    main()
