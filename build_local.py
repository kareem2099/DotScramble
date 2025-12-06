#!/usr/bin/env python3
"""
Local Build Script for DotScramble (without PyArmor obfuscation for testing)
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

def create_spec_file():
    """Create PyInstaller spec file for direct build"""
    print("📝 Creating PyInstaller spec file...")

    # Get OpenCV data path dynamically
    try:
        import cv2
        cv2_data_dir = os.path.dirname(cv2.data.haarcascades)
    except ImportError:
        cv2_data_dir = None

    # Build datas list
    datas = [
        ("config.py", "."),  # Include config
        ("presets.json", "."),  # Include presets
    ]

    # Add OpenCV data if available
    if cv2_data_dir and os.path.exists(cv2_data_dir):
        datas.append((cv2_data_dir, 'cv2/data'))

    spec_content = f'''# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from pathlib import Path

# Analysis configuration
a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas={repr(datas)},
    hiddenimports=[
        "cv2",
        "numpy",
        "PIL",
        "PIL.Image",
        "PIL.ImageTk",
        "PIL.ImageFilter",
        "PIL.ImageDraw",
        "PIL.ImageFont",
        "PIL.ImageEnhance",
        "PIL.ImageColor",
        "tkinter",
        "tkinter.ttk",
        "tkinter.filedialog",
        "tkinter.messagebox",
        "tkinter.simpledialog",
        "os",
        "sys",
        "pathlib",
        "subprocess",
        "shutil",
        "logging",
        "json",
        "time",
        "datetime",
        "platform",
        "webbrowser",
        "pytesseract",
        "opencv-python",
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
    name="DotScramble",
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
    icon=None,
)
'''

    with open('DotScramble.spec', 'w') as f:
        f.write(spec_content)

    print("✅ Spec file created")
    return True

def build_executable():
    """Build executable using PyInstaller"""
    print("🔨 Building executable with PyInstaller...")

    # Remove old builds
    if os.path.exists("dist"):
        shutil.rmtree("dist")
    if os.path.exists("build"):
        shutil.rmtree("build")

    # Build with PyInstaller using the spec file
    cmd = "pyinstaller --clean DotScramble.spec"
    if not run_command(cmd):
        print("❌ PyInstaller build failed")
        return False

    print("✅ Executable build completed")
    return True

def create_release_package():
    """Create a release package with the executable"""
    print("📦 Creating release package...")

    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "windows":
        ext = ".exe"
        release_name = f"DotScramble-Windows-{machine}"
    elif system == "darwin":  # macOS
        ext = ".app"
        release_name = f"DotScramble-macOS-{machine}"
    elif system == "linux":
        ext = ""  # Linux executables don't have extension
        release_name = f"DotScramble-Linux-{machine}"
    else:
        release_name = f"DotScramble-{system}-{machine}"

    # Create release directory
    release_dir = Path("release")
    release_dir.mkdir(exist_ok=True)

    # Copy executable
    exe_path = Path("dist") / f"DotScramble{ext}"
    if exe_path.exists():
        shutil.copy2(exe_path, release_dir / f"DotScramble{ext}")

        # Create zip archive
        shutil.make_archive(f"release/{release_name}", 'zip', release_dir)

        print(f"✅ Release package created: release/{release_name}.zip")
        return True
    else:
        print("❌ Executable not found in dist directory")
        return False

def main():
    """Main build process"""
    print("🚀 Starting Local Build Process for DotScramble")
    print("=" * 50)

    # Check if we're in the right directory
    if not Path("main.py").exists():
        print("❌ Error: main.py not found. Run from project root.")
        sys.exit(1)

    steps = [
        ("Creating spec file", create_spec_file),
        ("Building executable", build_executable),
        ("Creating release package", create_release_package),
    ]

    for step_name, step_func in steps:
        print(f"\n📋 {step_name}...")
        if not step_func():
            print(f"❌ Build failed at: {step_name}")
            sys.exit(1)

    print("\n🎉 Local build completed successfully!")
    print("📁 Check the 'release' directory for your executable")

if __name__ == "__main__":
    main()
