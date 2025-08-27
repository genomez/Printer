
## What This Installs

- **ustreamer** - Webcam streaming
- **KAMP Configuration** - Adaptive meshing and purging
- **Overrides Configuration** - Custom printer settings  
- **Cleanup Service** - Automatic backup management
- **Custom Resonance Tester** - Enhanced resonance testing
- **Bed Mesh Modifications** - System parameter adjustments
- **Moonraker Timelapse** - Timelapse functionality
- **Mainsail** - Web interface for 3D printer management

## Quick Start

1. SSH into your printer
2. Clone this repository: `git clone https://github.com/YOUR_USERNAME/3d-printer-installer.git`
3. Run the installer: `./install.sh`

## Usage Options

### Install All Components
```bash
 ./install.sh
```

### Dry Run (Preview Changes)
```bash
 ./install.sh --dry-run
```

### Install Specific Components
```bash
 ./install.sh --components kamp overrides cleanup
```

Available components: `ustreamer`, `kamp`, `overrides`, `cleanup`, `resonance`, `bed_mesh`, `timelapse`, `mainsail`
