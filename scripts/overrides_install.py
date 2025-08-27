#!/usr/bin/env python3

import os
import sys
import shutil
import argparse
from pathlib import Path

# Configuration
REPO_ROOT = Path(__file__).parent.parent.absolute()
CONFIG_DIR = "/mnt/UDISK/printer_data/config"
CUSTOM_CONFIG_DIR = "/mnt/UDISK/printer_data/config/custom"

def log(message, level="INFO"):
    print(f"[{level}] {message}")

def check_file_exists(path):
    return os.path.exists(path)

def copy_file(src, dst):
    if not check_file_exists(src):
        log(f"Source file not found: {src}", "ERROR")
        return False
        
    try:
        shutil.copy2(src, dst)
        log(f"Successfully copied {src} to {dst}")
        return True
    except Exception as e:
        log(f"Failed to copy {src}: {e}", "ERROR")
        return False

def install_overrides():
    """Install overrides.cfg to custom config directory"""
    log("Installing overrides.cfg...")
    
    # Ensure custom directory exists
    os.makedirs(CUSTOM_CONFIG_DIR, exist_ok=True)
        
    # Copy overrides.cfg (will overwrite existing)
    overrides_src = REPO_ROOT / "configs" / "overrides.cfg"
    overrides_dst = Path(CUSTOM_CONFIG_DIR) / "overrides.cfg"
    if not copy_file(overrides_src, overrides_dst):
        return False
        
    log("overrides.cfg installed successfully")
    return True

def main():
    parser = argparse.ArgumentParser(description="Overrides Configuration Installer")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without actually doing it")
    
    args = parser.parse_args()
    
    # Check if running as root
    if os.geteuid() != 0:
        log("This installer must be run as root (use sudo)", "ERROR")
        sys.exit(1)
    
    if args.dry_run:
        log("DRY RUN: Would install overrides.cfg")
        sys.exit(0)
    
    try:
        success = install_overrides()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        log("Installation interrupted by user", "ERROR")
        sys.exit(1)
    except Exception as e:
        log(f"Installation failed with error: {e}", "ERROR")
        sys.exit(1)

if __name__ == "__main__":
    main()
