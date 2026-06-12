#!/usr/bin/env python3
"""
Build Script for DotScramble
Builds a standalone executable using PyInstaller with Staging isolation.
"""

import os
import sys
import subprocess
import shutil
import platform
from pathlib import Path

STAGING_DIR = Path("build_staging")

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

def prepare_staging():
    """Prepare temporary build staging directory and remove original python source"""
    print("Preparing staging directory...")
    if STAGING_DIR.exists():
        shutil.rmtree(STAGING_DIR)

    STAGING_DIR.mkdir(parents=True, exist_ok=True)

    # Copy src, assets, presets.json to staging
    shutil.copytree("src", STAGING_DIR / "src")
    shutil.copytree("assets", STAGING_DIR / "assets")
    shutil.copy2("presets.json", STAGING_DIR / "presets.json")

    if os.path.exists("config.py"):
        shutil.copy2("config.py", STAGING_DIR / "config.py")

    # Remove raw license_manager.py from staging
    raw_license = STAGING_DIR / "src" / "managers" / "license_manager.py"
    if raw_license.exists():
        raw_license.unlink()
        print("   ✅ Removed raw license_manager.py from staging.")

    # Verification check for the compiled binary (.so or .pyd file)
    compiled_exts = list((STAGING_DIR / "src" / "managers").glob("license_manager.*"))
    has_binary = any(f.suffix in ['.so', '.pyd'] for f in compiled_exts)

    if not has_binary:
        print("   ❌ CRITICAL ERROR: Compiled license_manager (.so/.pyd) NOT FOUND!")
        print("   Please run: python3 setup_license.py build_ext --inplace")
        return False

    print("   ✅ Verified compiled license_manager exists.")
    return True

def cleanup_staging():
    """Clean up staging directory"""
    if STAGING_DIR.exists():
        print("Cleaning up staging directory...")
        shutil.rmtree(STAGING_DIR)

def create_spec_file():
    """Create PyInstaller spec file pointing to the staging directory"""
    print("Creating PyInstaller spec file...")

    # Point to entry point inside the staging folder
    main_script = STAGING_DIR / "src" / "main.py"

    # Get OpenCV data path dynamically
    try:
        import cv2
        cv2_data_dir = os.path.dirname(cv2.data.haarcascades)
    except ImportError:
        cv2_data_dir = None

    # Build datas list targeting staging files
    datas = [
        (str(STAGING_DIR / 'src'), 'src'),
        (str(STAGING_DIR / 'assets'), 'assets'),
        (str(STAGING_DIR / 'presets.json'), '.'),
    ]

    if (STAGING_DIR / "config.py").exists():
        datas.append((str(STAGING_DIR / "config.py"), '.'))

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
    ["{main_script}"],
    pathex=[],
    binaries=[],
    datas={repr(datas)},
    hiddenimports=[
        'cv2',
        'numpy',
        'PIL',
        'PIL._tkinter_finder',
        'tkinter',
        'src',
        'src.controllers',
        'src.models',
        'src.views',
        'src.managers',
        'src.managers.license_manager',
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

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

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
    console=False,
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

    print("Spec file created")
    return True

def build_executable():
    """Build executable using PyInstaller"""
    print("Building executable with PyInstaller...")

    if os.path.exists("dist"):
        shutil.rmtree("dist")
    if os.path.exists("build"):
        shutil.rmtree("build")

    # Use sys.executable to ensure we use PyInstaller from the current environment (e.g. venv)
    cmd = f"{sys.executable} -m PyInstaller --clean DotScramble.spec"
    if not run_command(cmd):
        print("PyInstaller build failed")
        return False

    print("Executable build completed")
    return True

def generate_sha256(file_path):
    """Generate SHA-256 checksum of a file"""
    import hashlib
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        while True:
            data = f.read(65536)
            if not data:
                break
            sha256.update(data)
    return sha256.hexdigest()

def build_deb_package(exe_path, release_dir):
    """Build a Debian (.deb) package for Linux"""
    print("Building Debian (.deb) package...")
    deb_staging = Path("deb_staging")
    if deb_staging.exists():
        shutil.rmtree(deb_staging)
        
    try:
        # Create directory structure
        (deb_staging / "DEBIAN").mkdir(parents=True)
        (deb_staging / "usr/bin").mkdir(parents=True)
        (deb_staging / "usr/share/dotscramble").mkdir(parents=True)
        (deb_staging / "usr/share/applications").mkdir(parents=True)
        (deb_staging / "usr/share/pixmaps").mkdir(parents=True)
        
        # 1. Copy executable
        shutil.copy2(exe_path, deb_staging / "usr/share/dotscramble/DotScramble")
        
        # 2. Create shell script launcher in /usr/bin/dotscramble
        launcher = deb_staging / "usr/bin/dotscramble"
        launcher_content = """#!/bin/sh
exec /usr/share/dotscramble/DotScramble "$@"
"""
        launcher.write_text(launcher_content)
        launcher.chmod(launcher.stat().st_mode | 0o111) # make executable
        
        # 3. Copy icon to pixmaps
        icon_src = Path("assets/icons/Square150x150Logo.png")
        if not icon_src.exists():
            icon_src = Path("assets/icons/icon.png")
        if icon_src.exists():
            shutil.copy2(icon_src, deb_staging / "usr/share/pixmaps/dotscramble.png")
            
        # 4. Create desktop entry in /usr/share/applications/DotScramble.desktop
        desktop_file = deb_staging / "usr/share/applications/DotScramble.desktop"
        desktop_content = """[Desktop Entry]
Type=Application
Name=DotScramble
Comment=Advanced Privacy Studio Pro
Exec=dotscramble
Icon=dotscramble
Terminal=false
Categories=Utility;Graphics;
StartupWMClass=DotScramble
"""
        desktop_file.write_text(desktop_content)
        
        # 5. Create DEBIAN/control file
        try:
            from src.config import APP_VERSION
        except ImportError:
            APP_VERSION = "1.3.0"
            
        control_file = deb_staging / "DEBIAN/control"
        control_content = f"""Package: dotscramble
Version: {APP_VERSION}
Section: utils
Priority: optional
Architecture: amd64
Maintainer: Description: Advanced image privacy studio designed to redact faces, text, and EXIF metadata from images.
"""
        control_file.write_text(control_content)
        
        # Build the package
        deb_output = release_dir / "DotScramble-Linux-x86_64.deb"
        if deb_output.exists():
            deb_output.unlink()
        cmd = f"dpkg-deb --build {deb_staging} {deb_output}"
        if run_command(cmd):
            print(f"   ✅ Debian package created: {deb_output.name}")
            return deb_output
        else:
            print("   ❌ dpkg-deb build failed")
            return None
    finally:
        if deb_staging.exists():
            shutil.rmtree(deb_staging)

def build_appimage_package(exe_path, release_dir):
    """Build an AppImage package for Linux"""
    print("Building AppImage package...")
    appdir = Path("AppDir")
    if appdir.exists():
        shutil.rmtree(appdir)
        
    try:
        # Create directory structure
        (appdir / "usr/bin").mkdir(parents=True)
        
        # 1. Copy executable
        shutil.copy2(exe_path, appdir / "usr/bin/DotScramble")
        
        # 2. Create AppRun script at root of AppDir
        apprun = appdir / "AppRun"
        apprun_content = """#!/bin/sh
SELF=$(readlink -f "$0")
HERE=$(dirname "$SELF")
exec "$HERE/usr/bin/DotScramble" "$@"
"""
        apprun.write_text(apprun_content)
        apprun.chmod(apprun.stat().st_mode | 0o111) # make executable
        
        # 3. Copy icon to root of AppDir
        icon_src = Path("assets/icons/Square150x150Logo.png")
        if not icon_src.exists():
            icon_src = Path("assets/icons/icon.png")
        if icon_src.exists():
            shutil.copy2(icon_src, appdir / "dotscramble.png")
            
        # 4. Create desktop entry at root of AppDir
        desktop_file = appdir / "DotScramble.desktop"
        desktop_content = """[Desktop Entry]
Type=Application
Name=DotScramble
Comment=Advanced Privacy Studio Pro
Exec=DotScramble
Icon=dotscramble
Terminal=false
Categories=Utility;Graphics;
StartupWMClass=DotScramble
"""
        desktop_file.write_text(desktop_content)
        
        # 5. Get appimagetool
        appimagetool = Path("appimagetool-x86_64.AppImage")
        if not appimagetool.exists():
            print("Downloading appimagetool...")
            import urllib.request
            url = "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"
            try:
                urllib.request.urlretrieve(url, appimagetool)
                appimagetool.chmod(appimagetool.stat().st_mode | 0o111) # make executable
                print("   ✅ Downloaded appimagetool")
            except Exception as e:
                print(f"   ❌ Failed to download appimagetool: {e}")
                return None
                
        # Build the AppImage
        appimage_output = release_dir / "DotScramble-Linux-x86_64.AppImage"
        if appimage_output.exists():
            appimage_output.unlink()
        # Run appimagetool with ARCH=x86_64 env var
        cmd = f"ARCH=x86_64 ./appimagetool-x86_64.AppImage {appdir} {appimage_output}"
        if run_command(cmd):
            print(f"   ✅ AppImage package created: {appimage_output.name}")
            return appimage_output
        else:
            print("   ❌ appimagetool build failed")
            return None
    finally:
        if appdir.exists():
            shutil.rmtree(appdir)

def sign_and_checksum_files(files, release_dir):
    """Generate SHA-256 hashes and GPG signatures for built files"""
    print("\nGenerating signatures and checksums...")
    
    # Calculate and write SHA-256 hashes
    sha_lines = ["[SHA-256 Checksums]\n"]
    for file_path in files:
        if file_path and file_path.exists():
            # Calculate SHA256
            sha = generate_sha256(file_path)
            sha_lines.append(f"{sha}  {file_path.name}\n")
            
            # GPG Detached signature
            asc_path = file_path.with_suffix(file_path.suffix + ".asc")
            if asc_path.exists():
                asc_path.unlink()
            
            # Detached armor signature
            cmd = f"gpg --batch --yes --detach-sign --armor --output {asc_path} {file_path}"
            print(f"Signing {file_path.name} with GPG...")
            if run_command(cmd):
                print(f"   ✅ Detached signature created: {asc_path.name}")
            else:
                print(f"   ⚠️ Detached signature failed for {file_path.name}. Make sure gpg is configured.")
                
    sha_file = release_dir / "sha.txt"
    sha_file.write_text("".join(sha_lines))
    print(f"   ✅ Checksums written to: {sha_file.name}")

def create_release_package():
    """Create a release package with the executable, .deb, and AppImage targets"""
    print("Creating release package...")

    system = platform.system().lower()
    machine = platform.machine().lower()

    possible_names = ["DotScramble", "DotScramble.exe", "DotScramble.app"]

    exe_path = None
    for name in possible_names:
        candidate = Path("dist") / name
        if candidate.exists():
            exe_path = candidate
            break

    if exe_path is None:
        print("Executable not found in dist directory.")
        return False

    release_dir = Path("release")
    release_dir.mkdir(exist_ok=True)

    dest_file = release_dir / exe_path.name
    if dest_file.exists():
        try:
            dest_file.unlink()
        except Exception as e:
            print(f"⚠️ Warning: Could not unlink existing release file {dest_file}: {e}")
            print("Make sure no running instances of the app are locking it.")
            
    shutil.copy2(exe_path, dest_file)

    print("Cleaning up temporary files...")
    if os.path.exists("build"):
        shutil.rmtree("build")

    # If platform is Linux, build .deb and .AppImage and sign them
    if system == "linux":
        built_files = []
        
        # 1. Build Debian Package
        deb_file = build_deb_package(dest_file, release_dir)
        if deb_file:
            built_files.append(deb_file)
            
        # 2. Build AppImage
        appimage_file = build_appimage_package(dest_file, release_dir)
        if appimage_file:
            built_files.append(appimage_file)
            
        # 3. Create signatures & sha.txt
        if built_files:
            sign_and_checksum_files(built_files, release_dir)
    else:
        # Standard .tar.gz fallback for Windows/macOS
        release_name = f"DotScramble-{system.capitalize()}-{machine}"
        archive_name = f"release/{release_name}"
        shutil.make_archive(archive_name, 'gztar', release_dir)
        print(f"Release package created: {archive_name}.tar.gz")

    return True

def main():
    """Main build process"""
    print("Starting Secure Staging Build Process for DotScramble")
    print("=" * 50)

    if not Path("src/main.py").exists():
        print("Error: src/main.py not found. Please ensure you are in the project root.")
        sys.exit(1)

    try:
        if not prepare_staging():
            print("Staging preparation failed")
            sys.exit(1)

        steps = [
            ("Creating spec file", create_spec_file),
            ("Building executable", build_executable),
            ("Creating release package", create_release_package),
        ]

        for step_name, step_func in steps:
            print(f"\nProcessing: {step_name}...")
            if not step_func():
                print(f"Build failed at: {step_name}")
                sys.exit(1)

    finally:
        cleanup_staging()

    print("\nBuild completed successfully!")
    print("Check the 'release' directory for your executable")

if __name__ == "__main__":
    main()