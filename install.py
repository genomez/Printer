#!/usr/bin/env python3

import os
import sys
import subprocess
import shutil
import re
import argparse
from pathlib import Path

# Configuration - paths relative to the cloned repository
REPO_ROOT = Path(__file__).parent.absolute()
CONFIG_DIR = "/mnt/UDISK/printer_data/config"
CUSTOM_CONFIG_DIR = "/mnt/UDISK/printer_data/config/custom"
KLIPPER_EXTRAS_DIR = "/usr/share/klipper/klippy/extras"
INIT_D_DIR = "/etc/init.d"
MOONRAKER_ASVC_FILE = "/mnt/UDISK/printer_data/moonraker.asvc"

class PrinterInstaller:
    def __init__(self, dry_run=False, verbose=False):
        self.dry_run = dry_run
        self.verbose = verbose
        
    def log(self, message, level="INFO"):
        prefix = "[DRY RUN] " if self.dry_run else ""
        print(f"{prefix}[{level}] {message}")
        
    def run_command(self, command, capture_output=True):
        """Run a command locally on the printer"""
        if self.verbose:
            self.log(f"Running: {command}")
        
        try:
            result = subprocess.run(command, shell=True, capture_output=capture_output, text=True)
            if self.verbose and result.stdout:
                self.log(f"STDOUT: {result.stdout.strip()}")
            if result.stderr:
                self.log(f"STDERR: {result.stderr.strip()}")
            return result
        except Exception as e:
            self.log(f"Command failed: {e}", "ERROR")
            return None
            
    def check_file_exists(self, path):
        """Check if a file or path exists"""
        return os.path.exists(path)
        
    def check_dir_exists(self, path):
        """Check if a directory exists"""
        return os.path.isdir(path)
        
    def copy_file(self, src, dst):
        """Copy a file"""
        if not self.check_file_exists(src):
            self.log(f"Source file not found: {src}", "ERROR")
            return False
            
        if self.dry_run:
            self.log(f"Would copy {src} to {dst}")
            return True
            
        try:
            shutil.copy2(src, dst)
            self.log(f"Successfully copied {src} to {dst}")
            return True
        except Exception as e:
            self.log(f"Failed to copy {src}: {e}", "ERROR")
            return False
            
    def copy_dir(self, src, dst):
        """Copy a directory"""
        if not self.check_dir_exists(src):
            self.log(f"Source directory not found: {src}", "ERROR")
            return False
            
        if self.dry_run:
            self.log(f"Would copy directory {src} to {dst}")
            return True
            
        try:
            if os.path.exists(dst):
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            self.log(f"Successfully copied directory {src} to {dst}")
            return True
        except Exception as e:
            self.log(f"Failed to copy directory {src}: {e}", "ERROR")
            return False
            
    def install_ustreamer(self):
        """Install ustreamer using the existing script"""
        self.log("Installing ustreamer...")
        
        installer_path = REPO_ROOT / "scripts" / "ustreamer_install.py"
        if not self.check_file_exists(installer_path):
            self.log("ustreamer install script not found", "ERROR")
            return False
            
        if self.dry_run:
            self.log("Would run: python3 'scripts/ustreamer_install.py'")
            return True

        # Execute with optional live output only when verbose
        try:
            command = f"python3 '{installer_path}'"

            if self.verbose:
                self.log("Running ustreamer installer with live output...")
                process = subprocess.Popen(
                    command,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    universal_newlines=True,
                    bufsize=1,
                )
                for line in iter(process.stdout.readline, ''):
                    if line:
                        print(line.rstrip())
                process.stdout.close()
                return_code = process.wait()
            else:
                result = subprocess.run(command, shell=True, capture_output=True, text=True)
                return_code = result.returncode

            if return_code == 0:
                self.log("ustreamer installation completed successfully")
                return True
            else:
                self.log(f"ustreamer installation failed with return code {return_code}", "ERROR")
                return False
        except Exception as e:
            self.log(f"Failed to run ustreamer installer: {e}", "ERROR")
            return False
            
    def install_kamp(self):
        """Install KAMP configuration files"""
        self.log("Installing KAMP configuration...")
        
        # Copy KAMP folder
        kamp_src = REPO_ROOT / "configs" / "KAMP"
        kamp_dst = Path(CONFIG_DIR) / "KAMP"
        if not self.copy_dir(kamp_src, kamp_dst):
            return False
            
        # Copy KAMP_Settings.cfg
        kamp_settings_src = REPO_ROOT / "configs" / "KAMP_Settings.cfg"
        kamp_settings_dst = Path(CONFIG_DIR) / "KAMP_Settings.cfg"
        if not self.copy_file(kamp_settings_src, kamp_settings_dst):
            return False
            
        # Check if KAMP_Settings.cfg is already included in printer.cfg
        printer_cfg = Path(CONFIG_DIR) / "printer.cfg"
        if not self.check_file_exists(printer_cfg):
            self.log("printer.cfg not found - cannot add include line", "ERROR")
            return False
            
        with open(printer_cfg, 'r') as f:
            content = f.read()
            
        if '[include KAMP_Settings.cfg]' in content:
            self.log("KAMP_Settings.cfg already included in printer.cfg")
        else:
            # Add the include line safely
            if self.dry_run:
                self.log("Would add '[include KAMP_Settings.cfg]' to printer.cfg")
            else:
                lines = content.split('\n')
                include_lines = []
                for i, line in enumerate(lines):
                    if line.strip().startswith('[include'):
                        include_lines.append(i)
                
                if include_lines:
                    # Insert after the last include line
                    insert_pos = include_lines[-1] + 1
                    lines.insert(insert_pos, '[include KAMP_Settings.cfg]')
                else:
                    # If no include lines found, append at the end
                    # Ensure file ends with a newline before appending
                    if lines and lines[-1] != '':
                        lines.append('')
                    lines.append('[include KAMP_Settings.cfg]')
                    
                # Write back to file
                with open(printer_cfg, 'w') as f:
                    f.write('\n'.join(lines))
                self.log("Added KAMP_Settings.cfg include to printer.cfg")
                    
        return True
        
    def install_overrides(self):
        """Install overrides.cfg to custom config directory"""
        self.log("Installing overrides.cfg...")
        
        # Ensure custom directory exists
        if not self.dry_run:
            os.makedirs(CUSTOM_CONFIG_DIR, exist_ok=True)
            
        # Copy overrides.cfg (will overwrite existing)
        overrides_src = REPO_ROOT / "configs" / "overrides.cfg"
        overrides_dst = Path(CUSTOM_CONFIG_DIR) / "overrides.cfg"
        if not self.copy_file(overrides_src, overrides_dst):
            return False
            
        self.log("overrides.cfg installed successfully")
        return True
        
    def install_cleanup_service(self):
        """Install the cleanup service"""
        self.log("Installing cleanup service...")
        
        # Copy the service file
        service_src = REPO_ROOT / "services" / "cleanup_printer_backups"
        service_dst = Path(INIT_D_DIR) / "cleanup_printer_backups"
        if not self.copy_file(service_src, service_dst):
            return False
            
        # Make it executable
        if not self.dry_run:
            try:
                os.chmod(service_dst, 0o755)
            except Exception as e:
                self.log(f"Failed to chmod service file: {e}", "ERROR")
                return False
            
        # Check if service is already in moonraker.asvc
        if not self.check_file_exists(MOONRAKER_ASVC_FILE):
            self.log("moonraker.asvc not found - cannot add service", "ERROR")
            return False
            
        with open(MOONRAKER_ASVC_FILE, 'r') as f:
            content = f.read()
            
        if 'cleanup_printer_backups' in content:
            self.log("cleanup_printer_backups already in moonraker.asvc")
        else:
            # Add service to moonraker.asvc
            if self.dry_run:
                self.log("Would add 'cleanup_printer_backups' to moonraker.asvc")
            else:
                try:
                    with open(MOONRAKER_ASVC_FILE, 'a') as f:
                        if not content.endswith('\n'):
                            f.write('\n')
                        f.write('cleanup_printer_backups\n')
                    self.log("Added cleanup_printer_backups to moonraker.asvc")
                except Exception as e:
                    self.log(f"Failed to update moonraker.asvc: {e}", "ERROR")
                    return False
                
        return True
        
    def install_resonance_tester(self):
        """Install the custom resonance tester"""
        self.log("Installing custom resonance tester...")
        
        resonance_src = REPO_ROOT / "patches" / "resonance_tester.py"
        resonance_dst = Path(KLIPPER_EXTRAS_DIR) / "resonance_tester.py"
        if not self.copy_file(resonance_src, resonance_dst):
            return False
            
        self.log("resonance_tester.py installed successfully")
        return True
        
    def modify_bed_mesh(self):
        """Modify bed_mesh.py to change minval parameter"""
        self.log("Modifying bed_mesh.py...")
        
        bed_mesh_path = Path(KLIPPER_EXTRAS_DIR) / "bed_mesh.py"
        if not self.check_file_exists(bed_mesh_path):
            self.log("bed_mesh.py not found", "ERROR")
            return False
            
        # Check if the modification is already applied
        try:
            with open(bed_mesh_path, 'r') as f:
                content = f.read()
        except Exception as e:
            self.log(f"Failed to read bed_mesh.py: {e}", "ERROR")
            return False
            
        if 'minval=1.' in content:
            self.log("bed_mesh.py already has minval=1. (modification not needed)")
            return True
            
        # Apply the sed modification
        sed_command = f"sed -i '/move_check_distance.*minval=3\\./s/minval=3\\./minval=1./' '{bed_mesh_path}'"
        
        if self.dry_run:
            self.log(f"Would run: {sed_command}")
            return True
            
        result = self.run_command(sed_command)
        if result and result.returncode == 0:
            self.log("bed_mesh.py modified successfully")
            return True
        else:
            self.log("Failed to modify bed_mesh.py", "ERROR")
            return False
            
    def verify_installation(self, components=None):
        """Verify that only the requested components were installed correctly"""
        # Default to all components if none provided
        if components is None:
            components = ['ustreamer', 'kamp', 'overrides', 'cleanup', 'resonance', 'bed_mesh']

        self.log("Verifying installation...")
        all_good = True

        # kamp verification
        if 'kamp' in components:
            kamp_dir = Path(CONFIG_DIR) / "KAMP"
            kamp_cfg = Path(CONFIG_DIR) / "KAMP_Settings.cfg"
            if self.check_dir_exists(kamp_dir):
                self.log("✓ KAMP directory verified")
            else:
                self.log("✗ KAMP directory not found", "ERROR")
                all_good = False

            if self.check_file_exists(kamp_cfg):
                self.log("✓ KAMP_Settings.cfg verified")
            else:
                self.log("✗ KAMP_Settings.cfg not found", "ERROR")
                all_good = False

            printer_cfg = Path(CONFIG_DIR) / "printer.cfg"
            if self.check_file_exists(printer_cfg):
                try:
                    with open(printer_cfg, 'r') as f:
                        content = f.read()
                    if '[include KAMP_Settings.cfg]' in content:
                        self.log("✓ KAMP_Settings.cfg included in printer.cfg")
                    else:
                        self.log("✗ KAMP_Settings.cfg not included in printer.cfg", "ERROR")
                        all_good = False
                except Exception as e:
                    self.log(f"Failed to read printer.cfg: {e}", "ERROR")
                    all_good = False
            else:
                self.log("✗ printer.cfg not found", "ERROR")
                all_good = False

        # overrides verification
        if 'overrides' in components:
            overrides_path = Path(CUSTOM_CONFIG_DIR) / "overrides.cfg"
            if self.check_file_exists(overrides_path):
                self.log("✓ overrides.cfg verified")
            else:
                self.log("✗ overrides.cfg not found", "ERROR")
                all_good = False

        # cleanup service verification
        if 'cleanup' in components:
            service_path = Path(INIT_D_DIR) / "cleanup_printer_backups"
            if self.check_file_exists(service_path):
                self.log("✓ cleanup service file verified")
            else:
                self.log("✗ cleanup service file not found", "ERROR")
                all_good = False

            if self.check_file_exists(MOONRAKER_ASVC_FILE):
                try:
                    with open(MOONRAKER_ASVC_FILE, 'r') as f:
                        content = f.read()
                    if 'cleanup_printer_backups' in content:
                        self.log("✓ cleanup_printer_backups in moonraker.asvc")
                    else:
                        self.log("✗ cleanup_printer_backups not in moonraker.asvc", "ERROR")
                        all_good = False
                except Exception as e:
                    self.log(f"Failed to read moonraker.asvc: {e}", "ERROR")
                    all_good = False
            else:
                self.log("✗ moonraker.asvc not found", "ERROR")
                all_good = False

        # resonance tester verification
        if 'resonance' in components:
            resonance_dst = Path(KLIPPER_EXTRAS_DIR) / "resonance_tester.py"
            if self.check_file_exists(resonance_dst):
                self.log("✓ resonance_tester.py verified")
            else:
                self.log("✗ resonance_tester.py not found", "ERROR")
                all_good = False

        # bed_mesh modification verification
        if 'bed_mesh' in components:
            bed_mesh_path = Path(KLIPPER_EXTRAS_DIR) / "bed_mesh.py"
            if self.check_file_exists(bed_mesh_path):
                try:
                    with open(bed_mesh_path, 'r') as f:
                        content = f.read()
                    if 'minval=1.' in content:
                        self.log("✓ bed_mesh.py modification verified (minval=1.)")
                    else:
                        self.log("✗ bed_mesh.py modification not found (minval=1.)", "ERROR")
                        all_good = False
                except Exception as e:
                    self.log(f"Failed to read bed_mesh.py: {e}", "ERROR")
                    all_good = False
            else:
                self.log("✗ bed_mesh.py not found", "ERROR")
                all_good = False

        # ustreamer verification (best-effort)
        if 'ustreamer' in components:
            candidates = [
                shutil.which("ustreamer"),
                "/usr/local/bin/ustreamer",
                "/usr/bin/ustreamer",
                "/bin/ustreamer",
                "/usr/sbin/ustreamer",
                "/sbin/ustreamer",
            ]
            found = any(self.check_file_exists(p) for p in candidates if p)
            if found:
                self.log("✓ ustreamer binary found")
            else:
                self.log("✗ ustreamer binary not found in PATH or standard locations", "ERROR")
                all_good = False

        return all_good
        
    def run_installation(self, components=None):
        """Run the complete installation"""
        if components is None:
            components = ['ustreamer', 'kamp', 'overrides', 'cleanup', 'resonance', 'bed_mesh']
            
        self.log("Starting 3D Printer Installation...")
        self.log(f"Components to install: {', '.join(components)}")
        
        results = {}
        
        if 'ustreamer' in components:
            results['ustreamer'] = self.install_ustreamer()
            
        if 'kamp' in components:
            results['kamp'] = self.install_kamp()
            
        if 'overrides' in components:
            results['overrides'] = self.install_overrides()
            
        if 'cleanup' in components:
            results['cleanup'] = self.install_cleanup_service()
            
        if 'resonance' in components:
            results['resonance'] = self.install_resonance_tester()
            
        if 'bed_mesh' in components:
            results['bed_mesh'] = self.modify_bed_mesh()
            
        # Verify only the requested components
        if not self.dry_run:
            results['verification'] = self.verify_installation(components=components)
            
        # Print summary
        self.log("\n" + "="*50)
        self.log("INSTALLATION SUMMARY")
        self.log("="*50)
        
        for component, success in results.items():
            status = "✓ SUCCESS" if success else "✗ FAILED"
            self.log(f"{component:15} : {status}")
            
        all_success = all(results.values())
        if all_success:
            self.log("\n🎉 All components installed successfully!")
        else:
            self.log("\n⚠️  Some components failed to install. Check the logs above.")
            
        return all_success

def main():
    parser = argparse.ArgumentParser(description="3D Printer Automated Installer")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without actually doing it")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed output")
    parser.add_argument("--components", nargs="+", 
                       choices=['ustreamer', 'kamp', 'overrides', 'cleanup', 'resonance', 'bed_mesh'],
                       help="Specific components to install (default: all)")
    
    args = parser.parse_args()
    
    # Check if running as root
    if os.geteuid() != 0:
        print("ERROR: This installer must be run as root (use sudo)")
        sys.exit(1)
    
    installer = PrinterInstaller(dry_run=args.dry_run, verbose=args.verbose)
    
    try:
        success = installer.run_installation(components=args.components)
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nInstallation interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nInstallation failed with error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()