#!/usr/bin/env python3

import os
import sys
import subprocess
import shutil
import re
import argparse
from pathlib import Path

# Configuration - paths relative to the cloned repository
REPO_ROOT = Path(__file__).parent.parent.absolute()

class PrinterInstaller:
    def __init__(self, dry_run=False):
        self.dry_run = dry_run
        self.verbose = True  # Always verbose by default
        
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
        

            
    def run_installer(self, component_name, script_name):
        """Generic method to run any installer script"""
        self.log(f"Installing {component_name}...")
        
        installer_path = REPO_ROOT / "scripts" / script_name
        if not self.check_file_exists(installer_path):
            self.log(f"{component_name} install script not found", "ERROR")
            return False
            
        if self.dry_run:
            self.log(f"Would run: python3 'scripts/{script_name}'")
            return True

        # Execute with live output (always verbose)
        try:
            command = f"python3 '{installer_path}'"

            self.log(f"Running {component_name} installer with live output...")
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

            if return_code == 0:
                self.log(f"{component_name} installation completed successfully")
                return True
            else:
                self.log(f"{component_name} installation failed with return code {return_code}", "ERROR")
                return False
        except Exception as e:
            self.log(f"Failed to run {component_name} installer: {e}", "ERROR")
            return False

    def install_ustreamer(self):
        """Install ustreamer using the existing script"""
        return self.run_installer("ustreamer", "ustreamer_install.py")
            
    def install_kamp(self):
        """Install KAMP configuration files"""
        return self.run_installer("KAMP", "kamp_install.py")
        
    def install_overrides(self):
        """Install overrides.cfg to custom config directory"""
        return self.run_installer("overrides", "overrides_install.py")
        
    def install_cleanup_service(self):
        """Install the cleanup service"""
        return self.run_installer("cleanup service", "cleanup_install.py")
        
    def install_resonance_tester(self):
        """Install the custom resonance tester"""
        return self.run_installer("resonance tester", "resonance_install.py")
        
    def install_timelapse(self):
        """Install moonraker-timelapse component"""
        return self.run_installer("timelapse", "timelapse_install.py")
        
    def modify_bed_mesh(self):
        """Modify bed_mesh.py to change minval parameter"""
        return self.run_installer("bed_mesh", "bed_mesh_install.py")
            
    def verify_installation(self, components=None):
        """Verify that only the requested components were installed correctly"""
        self.log("Verifying installation...")
        
        installer_path = REPO_ROOT / "scripts" / "verification.py"
        if not self.check_file_exists(installer_path):
            self.log("verification script not found", "ERROR")
            return False

        # Build command with components if specified
        command = f"python3 '{installer_path}'"
        if components:
            components_str = " ".join(components)
            command += f" --components {components_str}"

        # Execute with live output (always verbose)
        try:
            self.log("Running verification with live output...")
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

            if return_code == 0:
                self.log("Verification completed successfully")
                return True
            else:
                self.log(f"Verification failed with return code {return_code}", "ERROR")
                return False
        except Exception as e:
            self.log(f"Failed to run verification: {e}", "ERROR")
            return False
        
    def run_installation(self, components=None):
        """Run the complete installation"""
        if components is None:
            components = ['ustreamer', 'kamp', 'overrides', 'cleanup', 'resonance', 'bed_mesh', 'timelapse']
            
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
            
        if 'timelapse' in components:
            results['timelapse'] = self.install_timelapse()
            
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

    parser.add_argument("--components", nargs="+", 
                       choices=['ustreamer', 'kamp', 'overrides', 'cleanup', 'resonance', 'bed_mesh', 'timelapse'],
                       help="Specific components to install (default: all)")
    
    args = parser.parse_args()
    
    # Check if running as root
    if os.geteuid() != 0:
        print("ERROR: This installer must be run as root (use sudo)")
        sys.exit(1)
    
    installer = PrinterInstaller(dry_run=args.dry_run)
    
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