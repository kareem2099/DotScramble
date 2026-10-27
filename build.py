#!/usr/bin/env python3
"""
Build Script for DotScramble
Builds a standalone executable using PyInstaller with Staging isolation.
"""

import os
import re
import sys
import subprocess
import shutil
import platform
from pathlib import Path

STAGING_DIR = Path("build_staging")

# `--no-sign`: build the packages only. CI writes SHA256SUMS and the GPG signatures
# in a separate job, so the build job never sees the signing key.
SIGN = "--no-sign" not in sys.argv

# The same desktop entry for every package; only the command differs.
DESKTOP_ENTRY = """[Desktop Entry]
Type=Application
Name=DotScramble
GenericName=Photo Privacy Editor
Comment=Blur faces, license plates and text in photos
Exec={exec_cmd}
Icon=dotscramble
Terminal=false
Categories=Graphics;2DGraphics;RasterGraphics;Photography;
Keywords=blur;pixelate;privacy;face;anonymize;redact;license plate;exif;metadata;
StartupWMClass=DotScramble
"""

APPSTREAM_ID = "dev.dotsuite.DotScramble"
METAINFO_TEMPLATE = Path("assets/linux") / f"{APPSTREAM_ID}.metainfo.xml"
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256, 512)  # assets/icons/png/dotscramble-<size>.png

# Embedded in the AppImage: AppImageUpdate and Gear Lever fetch this .zsync from the latest release
APPIMAGE_UPDATE_INFO = "gh-releases-zsync|kareem2099|DotScramble|latest|DotScramble-Linux-x86_64.AppImage.zsync"


def desktop_entry(exec_cmd):
    return DESKTOP_ENTRY.format(exec_cmd=exec_cmd)


def appstream_releases(changelog_text, limit=5):
    """The newest CHANGELOG.md versions as an AppStream <releases> block."""
    found = re.findall(r"^## \[(\d+\.\d+\.\d+)\] - (\d{4}-\d{2}-\d{2})", changelog_text, re.M)[:limit]
    lines = ["<releases>"]
    for version, date in found:
        lines += [f'    <release version="{version}" date="{date}">',
                  f'      <url type="details">https://github.com/kareem2099/DotScramble/releases/tag/v{version}</url>',
                  "    </release>"]
    lines.append("  </releases>")
    return found, "\n".join(lines)


def metainfo_xml(version):
    """The AppStream metainfo with its releases filled in; the newest must be `version`."""
    found, releases = appstream_releases(Path("CHANGELOG.md").read_text(encoding="utf-8"))
    if not found or found[0][0] != version:
        raise ValueError(f"CHANGELOG.md has no entry for {version} at the top")
    template = METAINFO_TEMPLATE.read_text(encoding="utf-8")
    if template.count("<releases/>") != 1:
        raise ValueError(f"{METAINFO_TEMPLATE} needs exactly one empty <releases/> element")
    return template.replace("<releases/>", releases)

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

    # Copy src, assets, presets.json, core, and gui to staging. Never copy the license
    # module's readable forms: its source, the Cython C file (which repeats the source
    # in comments) and any cached bytecode (__pycache__/*.pyc decompiles straight back).
    skip = shutil.ignore_patterns("__pycache__", "*.pyc", "license_manager.py", "license_manager.c")
    shutil.copytree("src", STAGING_DIR / "src", ignore=skip)
    shutil.copytree("core", STAGING_DIR / "core", ignore=skip)
    shutil.copytree("gui", STAGING_DIR / "gui", ignore=skip)
    shutil.copytree("assets", STAGING_DIR / "assets")
    shutil.copy2("presets.json", STAGING_DIR / "presets.json")

    if os.path.exists("config.py"):
        shutil.copy2("config.py", STAGING_DIR / "config.py")

    leaked = [p for p in STAGING_DIR.rglob("license_manager*") if p.suffix in (".py", ".c", ".pyc")]
    if leaked:
        print(f"   ❌ CRITICAL ERROR: readable license code in staging: {[str(p) for p in leaked]}")
        return False
    print("   ✅ No license source, C file or bytecode in staging.")

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

    # Add PIL data files (exclude ImageTk which pulls in tkinter — not needed for PySide6 apps)
    try:
        import PIL
        pil_path = os.path.dirname(PIL.__file__)
        datas.append((pil_path, 'PIL'))
    except ImportError:
        pass

    # Add MediaPipe data files and modules for PyInstaller
    try:
        import importlib
        mediapipe = importlib.import_module("mediapipe")
        mediapipe_path = os.path.dirname(mediapipe.__file__)
        datas.append((mediapipe_path, 'mediapipe'))
    except ImportError:
        pass

    spec_content = f'''# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from pathlib import Path

# Analysis configuration
a = Analysis(
    ["{main_script}"],
    pathex=["{STAGING_DIR}"],
    binaries=[],
    datas={repr(datas)},
    hiddenimports=[
        'cv2',
        'numpy',
        'PIL',
        'PIL.Image',
        'PIL.ImageFilter',
        'PIL.ImageEnhance',
        'PySide6',
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'src',
        'src.controllers',
        'src.models',
        'src.views',
        'src.managers',
        'src.managers.license_manager',
        'mediapipe',
        'mediapipe.python._framework_bindings',
    ],
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=['PIL.ImageTk', 'tkinter', '_tkinter'],  # App uses PySide6, not tkinter
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
        desktop_file.write_text(desktop_entry("dotscramble"))
        
        # 5. Create DEBIAN/control file
        try:
            from src.config import APP_VERSION
        except ImportError:
            from version_info import VERSION as APP_VERSION
            
        control_file = deb_staging / "DEBIAN/control"
        control_content = f"""Package: dotscramble
Version: {APP_VERSION}
Section: utils
Priority: optional
Architecture: amd64
Maintainer: FreeRave <kareem2099@users.noreply.github.com>
Description: Advanced image privacy studio designed to redact faces, text,
 and EXIF metadata from images.
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
        
        # 3. Icons: the 256 px one at the root (appimagetool makes it .DirIcon), plus the hicolor set
        shutil.copy2("assets/icons/png/dotscramble-256.png", appdir / "dotscramble.png")
        for size in ICON_SIZES:
            icon_dir = appdir / f"usr/share/icons/hicolor/{size}x{size}/apps"
            icon_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f"assets/icons/png/dotscramble-{size}.png", icon_dir / "dotscramble.png")
        scalable = appdir / "usr/share/icons/hicolor/scalable/apps"
        scalable.mkdir(parents=True)
        shutil.copy2("assets/icons/dotscramble.svg", scalable / "dotscramble.svg")

        # 4. Desktop entry, at the root (AppImage) and in usr/share/applications (AppStream's launchable)
        (appdir / "DotScramble.desktop").write_text(desktop_entry("DotScramble"))
        (appdir / "usr/share/applications").mkdir(parents=True)
        shutil.copy2(appdir / "DotScramble.desktop", appdir / "usr/share/applications/DotScramble.desktop")

        # 5. AppStream metainfo (what AppImageHub and software centers show)
        try:
            from src.config import APP_VERSION
        except ImportError:
            from version_info import VERSION as APP_VERSION
        (appdir / "usr/share/metainfo").mkdir(parents=True)
        (appdir / f"usr/share/metainfo/{APPSTREAM_ID}.metainfo.xml").write_text(metainfo_xml(APP_VERSION), encoding="utf-8")
        
        # 6. Get appimagetool
        appimagetool = Path("appimagetool-x86_64.AppImage")
        if not appimagetool.exists():
            print("Downloading appimagetool...")
            import urllib.request
            # AppImageKit's copy is frozen; appimagetool now lives in its own repo
            url = "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
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
        zsync_output = Path(f"{appimage_output}.zsync")
        for stale in (zsync_output, Path(zsync_output.name)):
            stale.unlink(missing_ok=True)
        # ARCH=x86_64, and the update information; with zsyncmake installed this also writes the .zsync
        cmd = f"ARCH=x86_64 ./appimagetool-x86_64.AppImage -u '{APPIMAGE_UPDATE_INFO}' {appdir} {appimage_output}"
        if run_command(cmd):
            # appimagetool writes the .zsync into the working folder
            if Path(zsync_output.name).exists() and not zsync_output.exists():
                shutil.move(zsync_output.name, zsync_output)
            print(f"   ✅ AppImage package created: {appimage_output.name}")
            if zsync_output.exists():
                print(f"   ✅ zsync file created: {zsync_output.name}")
            else:
                print("   ⚠️ No .zsync written (zsyncmake missing): AppImageUpdate can't update this build")
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
    sha_lines = []
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
            cmd = f"gpg --batch --yes --local-user 0F0467813146DE68272EDC82145D345956DE18D2 --detach-sign --armor --output {asc_path} {file_path}"
            print(f"Signing {file_path.name} with GPG...")
            if run_command(cmd):
                print(f"   ✅ Detached signature created: {asc_path.name}")
            else:
                print(f"   ⚠️ Detached signature failed for {file_path.name}. Make sure gpg is configured.")
                
    sha_file = release_dir / "SHA256SUMS"
    sha_file.write_text("".join(sha_lines))
    print(f"   ✅ Checksums written to: {sha_file.name}")

def build_arch_package(exe_path, release_dir):
    """Build an Arch Linux (.pkg.tar.zst) package"""
    print("Building Arch Linux (.pkg.tar.zst) package...")
    arch_staging = Path("arch_staging")
    if arch_staging.exists():
        shutil.rmtree(arch_staging)

    try:
        # Create directory structure
        (arch_staging / "usr/bin").mkdir(parents=True)
        (arch_staging / "usr/share/dotscramble").mkdir(parents=True)
        (arch_staging / "usr/share/applications").mkdir(parents=True)
        (arch_staging / "usr/share/pixmaps").mkdir(parents=True)

        # 1. Copy main executable
        shutil.copy2(exe_path, arch_staging / "usr/share/dotscramble/DotScramble")
        (arch_staging / "usr/share/dotscramble/DotScramble").chmod(0o755)

        # 2. Launcher script in /usr/bin
        launcher = arch_staging / "usr/bin/dotscramble"
        launcher.write_text("#!/bin/sh\nexec /usr/share/dotscramble/DotScramble \"$@\"\n")
        launcher.chmod(0o755)

        # 3. Copy icon
        icon_src = Path("assets/icons/Square150x150Logo.png")
        if not icon_src.exists():
            icon_src = Path("assets/icons/icon.png")
        if icon_src.exists():
            shutil.copy2(icon_src, arch_staging / "usr/share/pixmaps/dotscramble.png")

        # 4. Desktop entry
        (arch_staging / "usr/share/applications/DotScramble.desktop").write_text(desktop_entry("dotscramble"))

        # 5. Calculate installed size (in KiB — Arch standard)
        total_size = sum(f.stat().st_size for f in arch_staging.rglob("*") if f.is_file())
        installed_size_kib = (total_size + 1023) // 1024

        # 6. Get version
        try:
            from src.config import APP_VERSION
        except ImportError:
            from version_info import VERSION as APP_VERSION

        import time
        build_date = int(time.time())

        # 7. Write .PKGINFO (Arch package metadata — must be first in archive)
        pkginfo_content = f"""# Generated by DotScramble build.py
pkgname = dotscramble
pkgver = {APP_VERSION}-1
pkgdesc = Advanced image privacy studio designed to redact faces, text, and EXIF metadata
url = https://github.com/kareem2099/DotScramble
builddate = {build_date}
packager = FreeRave <kareem2099@users.noreply.github.com>
size = {installed_size_kib * 1024}
arch = x86_64
license = Apache-2.0
depend = tesseract
"""
        pkginfo_path = arch_staging / ".PKGINFO"
        pkginfo_path.write_text(pkginfo_content)

        # 8. Pack with bsdtar into .pkg.tar.zst
        pkg_output = release_dir / "DotScramble-Linux-x86_64.pkg.tar.zst"
        if pkg_output.exists():
            pkg_output.unlink()

        # bsdtar packs from inside arch_staging so paths are relative (no leading /)
        cmd = (
            f"bsdtar --zstd -cf {pkg_output} "
            f"--options zstd:compression-level=19 "
            f"-C {arch_staging} ."
        )
        if run_command(cmd):
            print(f"   ✅ Arch package created: {pkg_output.name}")
            return pkg_output
        else:
            print("   ❌ bsdtar build failed")
            return None
    finally:
        if arch_staging.exists():
            shutil.rmtree(arch_staging)


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
            zsync_file = Path(f"{appimage_file}.zsync")
            if zsync_file.exists():
                built_files.append(zsync_file)
            
        # 3. Build Arch Linux Package (.pkg.tar.zst)
        arch_file = build_arch_package(dest_file, release_dir)
        if arch_file:
            built_files.append(arch_file)

        # 4. Build Tar.gz Package
        print("Building tar.gz package...")
        try:
            import tarfile
            tar_output = release_dir / "DotScramble-Linux-x86_64.tar.gz"
            if tar_output.exists():
                tar_output.unlink()
            with tarfile.open(tar_output, "w:gz") as tar:
                # Pack the executable with its original filename
                tar.add(dest_file, arcname=dest_file.name)
            print(f"   ✅ Tar.gz package created: {tar_output.name}")
            built_files.append(tar_output)
        except Exception as e:
            print(f"   ❌ Failed to create tar.gz package: {e}")
            
        # 5. Create signatures & SHA256SUMS (skipped with --no-sign)
        if built_files and SIGN:
            sign_and_checksum_files(built_files, release_dir)
        elif built_files:
            print("Skipping SHA256SUMS and signatures (--no-sign)")
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