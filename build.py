#!/usr/bin/env python3
"""
Advanced Build Script for DotScramble
Handles code obfuscation with PyArmor and executable creation with PyInstaller
"""

import os
import sys
import subprocess
import shutil
import platform
from pathlib import Path

def run_command(cmd, cwd=None):
    """Run a command and return success status"""
    try:
        result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Command failed: {cmd}")
            print(f"Error: {result.stderr}")
            return False
        return True
    except Exception as e:
        print(f"Exception running command: {e}")
        return False

def obfuscate_code():
    """Obfuscate Python code using PyArmor"""
    print("Obfuscating code with PyArmor...")

    # Remove old obfuscated code
    if os.path.exists("dist_obf"):
        shutil.rmtree("dist_obf")

    # Obfuscate the entire project
    cmd = "pyarmor gen --output dist_obf --recursive ."
    if not run_command(cmd):
        print("PyArmor obfuscation failed")
        return False

    print("Code obfuscation completed")
    return True

def create_spec_file():
    """Create PyInstaller spec file for the obfuscated code"""
    print("Creating PyInstaller spec file...")

    # Get the obfuscated entry point
    obf_main = Path("dist_obf") / "main.py"

    # Get OpenCV data path dynamically
    try:
        import cv2
        cv2_data_dir = os.path.dirname(cv2.data.haarcascades)
    except ImportError:
        cv2_data_dir = None

    # Build datas list
    datas = [
        ('dist_obf', '.'),  # Include all obfuscated files
        ('config.py', '.'),  # Include config
        ('presets.json', '.'),  # Include presets
    ]

    # Add OpenCV data if available
    if cv2_data_dir and os.path.exists(cv2_data_dir):
        datas.append((cv2_data_dir, 'cv2/data'))

    # Add PIL data files for Tkinter integration
    try:
        import PIL
        pil_path = os.path.dirname(PIL.__file__)
        datas.append((pil_path, 'PIL'))
    except ImportError:
        pass

    spec_content = f'''# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from pathlib import Path

# Analysis configuration
a = Analysis(
    ["{obf_main}"],
    pathex=[],
    binaries=[],
    datas={repr(datas)},
    hiddenimports=[
        'cv2',
        'numpy',
        'PIL',
        'PIL.Image',
        'PIL.ImageTk',
        'PIL.ImageFilter',
        'PIL.ImageDraw',
        'PIL.ImageFont',
        'PIL.ImageEnhance',
        'PIL.ImageColor',
        'PIL.ImageFile',
        'PIL.ImageOps',
        'PIL.ImagePalette',
        'PIL.PngImagePlugin',
        'PIL.JpegImagePlugin',
        'PIL.BmpImagePlugin',
        'PIL._tkinter_finder',  # Critical for PIL-Tkinter integration
        'tkinter',
        'tkinter.ttk',
        'tkinter.filedialog',
        'tkinter.messagebox',
        'tkinter.simpledialog',
        '_tkinter',  # Core Tkinter module
        'os',
        'sys',
        'pathlib',
        'subprocess',
        'shutil',
        'logging',
        'json',
        'time',
        'datetime',
        'platform',
        'webbrowser',
        'pytesseract',
        'opencv-python',
        'requests',  # For auto-updater
        'threading',  # For background operations
    ],
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

# Remove unnecessary files
pyz = PYZ(a.pure, a.zipped_data, cipher=None)

# Create executable
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='DotScramble',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Hide console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Add icon later if available
)
'''

    with open('DotScramble.spec', 'w') as f:
        f.write(spec_content)

    print("Spec file created")
    return True

def build_executable():
    """Build executable using PyInstaller"""
    print("Building executable with PyInstaller...")

    # Remove old builds
    if os.path.exists("dist"):
        shutil.rmtree("dist")
    if os.path.exists("build"):
        shutil.rmtree("build")

    # Build with PyInstaller using the spec file
    # Add additional flags for PIL/Tkinter integration
    cmd = "pyinstaller --clean --hidden-import=PIL._tkinter_finder --hidden-import=_tkinter DotScramble.spec"
    if not run_command(cmd):
        print("PyInstaller build failed")
        return False

    print("Executable build completed")
    return True

def create_release_package():
    """Create a release package with the executable"""
    print("Creating release package...")

    system = platform.system().lower()
    machine = platform.machine().lower()

    # Possible executable names to check
    possible_names = ["DotScramble", "DotScramble.exe", "DotScramble.app"]

    # Find the actual executable
    exe_path = None
    for name in possible_names:
        candidate = Path("dist") / name
        if candidate.exists():
            exe_path = candidate
            break

    if exe_path is None:
        print("Executable not found in dist directory. Contents:")
        if Path("dist").exists():
            for item in Path("dist").iterdir():
                print(f"  {item.name}")
        return False

    if system == "windows":
        release_name = f"DotScramble-Windows-{machine}"
    elif system == "darwin":  # macOS
        release_name = f"DotScramble-macOS-{machine}"
    elif system == "linux":
        release_name = f"DotScramble-Linux-{machine}"
    else:
        release_name = f"DotScramble-{system}-{machine}"

    # Create release directory
    release_dir = Path("release")
    release_dir.mkdir(exist_ok=True)

    # Copy executable
    shutil.copy2(exe_path, release_dir / exe_path.name)

    # Clean up to free disk space before archiving
    print("Cleaning up temporary files...")
    if os.path.exists("build"):
        shutil.rmtree("build")
    if os.path.exists("dist_obf"):
        shutil.rmtree("dist_obf")

    # Create tar.gz archive (supports unlimited file sizes)
    archive_name = f"release/{release_name}"
    shutil.make_archive(archive_name, 'gztar', release_dir)

    print(f"Release package created: {archive_name}.tar.gz")
    return True

def main():
    """Main build process"""
    print("Starting Advanced Build Process for DotScramble")
    print("=" * 50)

    # Check if we're in the right directory
    if not Path("main.py").exists():
        print("Error: main.py not found. Run from project root.")
        sys.exit(1)

    steps = [
        ("Obfuscating code", obfuscate_code),
        ("Creating spec file", create_spec_file),
        ("Building executable", build_executable),
        ("Creating release package", create_release_package),
    ]

    for step_name, step_func in steps:
        print(f"\nProcessing: {step_name}...")
        if not step_func():
            print(f"Build failed at: {step_name}")
            sys.exit(1)

    print("\nBuild completed successfully!")
    print("Check the 'release' directory for your executable")

if __name__ == "__main__":
    main()
