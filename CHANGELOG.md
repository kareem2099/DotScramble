# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.5.3] - 2026-10-27

### Changed
- The AppStream metadata in the AppImage is now
  `usr/share/metainfo/dev.dotsuite.DotScramble.appdata.xml` (was `.metainfo.xml`): AppImageHub
  takes the summary and description for its listing only from a file with this name. The
  content is unchanged.

---

## [1.5.2] - 2026-10-27

Ready for AppImageHub and AppImage tools.

### Added
- **AppStream metadata in the AppImage** (`dev.dotsuite.DotScramble`): description, screenshots,
  links and release history, for AppImageHub and software centers.
- **AppImage update information.** The AppImage now says where its updates are, and every release
  ships `DotScramble-Linux-x86_64.AppImage.zsync` (checksummed and signed like the packages), so
  AppImageUpdate, Gear Lever and AppImageLauncher can update it. The built-in updater works as
  before.
- The AppImage carries the full icon set (16–512 px and SVG) instead of one 150 px icon.

### Fixed
- The app menu shortcut an AppImage creates for itself pointed at a temporary folder that is
  gone once the app closes; it now points at the `.AppImage` file.
- The app no longer appears twice in some app menus: it is listed under Graphics only
  (`Graphics;2DGraphics;RasterGraphics;Photography;`), with a clearer description and search
  keywords.

---

## [1.5.1] - 2026-10-27

### Fixed
- **Text and word detection in the installed packages.** The AppImage, `.deb`, Arch package
  and tarball passed their bundled library path on to the programs they start, so the system
  Tesseract loaded the bundle's older C++ library and exited (`GLIBCXX_3.4.32 not found`), and
  the Text and Targeted text modes reported Tesseract as missing. Programs DotScramble starts
  now get your normal library path back. Running from source was not affected.

---

## [1.5.0] - 2026-10-27

The biggest DotScramble update yet: a redesigned interface, a canvas you can preview, compare
and zoom on, five new languages, a safer updater, and releases built and signed by GitHub
Actions.

### Added
- **Redesigned interface.** One toolbar instead of a header, a toolbar and duplicate buttons; a
  sidebar in four numbered, collapsible steps (What to hide → How to hide it → Fine-tune →
  Metadata on save); effect tiles and detection chips instead of long radio lists; a single
  primary **Apply effect** button; crisp SVG icons that follow the theme instead of emoji.
- **Detect preview** (`Ctrl+F`): see every region that will be hidden before applying, and click
  one to skip it. With several faces, the faces you pick on the canvas are the ones protected.
- **Compare** (`Ctrl+Shift+C`): a before / after split view with a draggable divider.
- **Zoom and pan**: mouse-wheel zoom around the cursor, `Ctrl++` / `Ctrl+-`, `Ctrl+0` fit,
  `Ctrl+1` actual size, a Fit ↔ 100% toggle, and drag to pan. Zoom is kept after applying.
- **Five new languages**: فارسی (Persian, right to left), Español, Русский, Deutsch and Türkçe,
  for seven in total. The app starts in your system language when it is one of them.
- **Real plural forms** (CLDR rules for every language): "1 file / 3 files", Arabic's six forms
  ("ملف واحد / ملفين / 3 ملفات / 11 ملفًا"), Russian's three ("1 файл / 3 файла / 5 файлов").
- **Every screen translated**: the image picker, the metadata editor and save report, the
  batch window, and the factory metadata presets. User presets keep their names.
- **New app icon**: a dot dissolving into pixels, with an SVG source and every size.
- **Update-required screen**: `version_policy.json` in this repository sets the oldest supported
  version. An older copy shows a screen with a **Download the latest version** button. It never
  blocks offline use.
- **Continuous integration**: the test suite runs on every push (188 tests).

### Changed
- **Auto-updater rewritten.** It checks GitHub off the UI thread, picks the right file for how
  you installed DotScramble (AppImage, .deb, Arch package or portable tar.gz), and installs
  only after both `SHA256SUMS` and the GPG signature check out against the pinned FreeRave
  release key.
- **Releases are built by GitHub Actions** on Ubuntu 22.04, so the packages run on Ubuntu 22.04+,
  Debian 12+, Fedora 36+ and other distributions with glibc 2.35 or newer (earlier builds needed
  a much newer system). Every package is smoke-tested and signed before it is published.
- **Metadata on save** is now one clear choice: Keep / Strip / Decoy, with the Ghost, Troll,
  Artist and Custom decoy profiles.
- **Image picker** follows the active theme, and its grid adapts to the window width.
- **All styling lives in one stylesheet** (`assets/themes/theme_template.qss`), so every theme
  restyles the whole app, dialogs included.
- The window can be snapped to half the screen: the toolbar switches to icons when space is tight.
- Pro activation opens `dotsuite.dev` directly and verifies licences with `core.dotsuite.dev`.
- **Dependencies**: Python 3.14 support; PySide6 6.12, NumPy 2.5, Pillow 13, MediaPipe 1.1.
  OpenCV is pinned to the 4.x contrib build (`opencv-contrib-python<5`), because OpenCV 5 no
  longer ships the Haar cascade files that free-tier detection needs.
- `python src/main.py` now works from the project root, as well as `python -m src.main`.

### Fixed
- **Pro activation** failed with "Failed to fetch" after the dashboard moved to `dotsuite.dev`,
  then with "HTTP 404" from the old licence server. Both are fixed, and a rejected activation
  now shows the server's reason instead of a bare status code.
- A Pro licence is no longer removed when the licence server can't be reached; only an explicit
  rejection revokes it.
- Missing OpenCV cascade files no longer fail silently with "0 regions processed" while the face
  stays visible: the app shows an error, and batch processing marks the file as failed.
- Mouse-wheel zoom was reset on every redraw.
- Live preview stacked the effect on top of itself with every slider move.
- Redo worked only once in a row.
- Restored settings and presets didn't move the sliders; the live-preview preference wasn't saved.
- A Pro-only effect or mode restored from an earlier Pro session stayed selected while locked.
- A startup error crashed the app (core dump) instead of showing its message.
- The image picker cut off tiles on the right; the batch window and dialogs ignored the theme.
- A false "Tesseract not found" warning when the system Tesseract was in use, and a flood of
  harmless Qt Wayland text-input messages in the terminal.

### Security
- Packaged builds now contain only the compiled licence module. Earlier builds also carried its
  bytecode (`.pyc`) and generated C source; the build now refuses to package them, and the
  release workflow inspects every binary before publishing.
- Releases are now signed with the FreeRave ed25519 key
  `0F04 6781 3146 DE68 272E DC82 145D 3459 56DE 18D2` (replacing the RSA key that signed 1.4.1),
  and the updater checks every signature against that pinned fingerprint, so a different key
  can't sign an update. `public_key.asc` holds the new public key.

---

## [1.4.1] - 2026-07-10

### Added
- **Arch Linux package** (`DotScramble-Linux-x86_64.pkg.tar.zst`): Native package for Arch Linux and Manjaro, installable with `sudo pacman -U`. Includes proper `.PKGINFO` metadata, launcher script, desktop entry, and icon.
- **Public GPG key** (`public_key.asc`): FreeRave signing key (`0D9B71AF1791DA36`) now shipped as a release asset so users can verify signatures offline without a keyserver.
- **Security & Integrity Verification** section in README with step-by-step GPG verification guide for AppImage, .deb, and .pkg.tar.zst packages.

### Changed
- **GPG signing key**: Migrated from `kareem ehab` (D3EB5327471C8F22) to new **FreeRave** key (`0D9B71AF1791DA36`, RSA-4096, expires 2029). All release artifacts are now signed with the FreeRave identity.
- **Checksum file renamed**: `sha.txt` → `SHA256SUMS` to match the standard Linux convention compatible with `sha256sum -c` directly.
- **Build pipeline**: `build.py` now explicitly pins GPG signing to `--local-user 0D9B71AF1791DA36` and generates `.pkg.tar.zst` in addition to `.deb`, `.AppImage`, and `.tar.gz`.

### Fixed
- GPG `--detach-sign` in `build.py` no longer relies on the default key, preventing accidental signing with an expired key.

---

## [1.4.0] - 2026-07-09

### Added
- **AI Evasion System**: Black-box adversarial perturbation engine (`core/adversarial_engine.py`) using SPSA (Simultaneous Perturbation Stochastic Approximation) to generate mathematically-optimized noise that defeats AI face recognition models without requiring gradient access.
- **Adversarial Worker Thread**: `QThread`-based worker streaming real-time progress to the UI during adversarial optimization, keeping the interface fully responsive during multi-minute computation.
- **Pluggable Evasion Proxy Protocol**: Formal `EvasionProxy` protocol allowing advanced users to substitute their own face recognition model as the optimization target.
- **Layered Evasion Pipeline**: Ordered pipeline (adversarial perturbation → visual effect → EXIF strip) ensuring perturbations survive downstream processing steps.

### Changed
- **UI Framework: Tkinter → PySide6**: Full migration from Tkinter to PySide6 (Qt official binding, LGPL v3), resolving the Apache 2.0 / GPL v3 license incompatibility and enabling proper Arabic RTL support, native Wayland compatibility, and a modern widget toolkit.
- **Evasion Strength UI**: Exposed `epsilon` and `num_iters` parameters as a labeled slider with three presets (Subtle / Balanced / Maximum) in the processing panel.

### Fixed
- **Tesseract Binary Path on Linux**: `setup_tesseract_configuration()` now uses platform-aware binary name (`tesseract` on Linux/macOS, `tesseract.exe` on Windows only) instead of hard-coded `.exe` extension.
- **Frozen Build Crash (`No module named 'tkinter'`)**: Removed unused `from PIL import ImageTk` import in `core/utils.py` that pulled in tkinter at runtime, crashing the PyInstaller executable.
- **Core Dump on Startup (`QWidget: Must construct a QApplication before a QWidget`)**: Refactored `check_dependencies()` to log errors to console first and only attempt a Qt dialog after safely acquiring `QApplication.instance()`.
- **Auto-Updater Silent Failure**: Fixed version comparison mismatch (`"v1.3.0"` vs `"1.3.0"`) by stripping the leading `v` from GitHub tag names before comparing to `APP_VERSION`.
- **Auto-Updater Wrong Asset Name**: Updated `_get_asset_url()` to match actual release artifact names (`DotScramble-Linux-x86_64.AppImage`, `DotScramble-Linux-x86_64.deb`) instead of the non-existent `DotScramble-linux` target.
- **One Dark Theme Low Contrast**: Raised `text_secondary` in the One Dark theme from `#5c6370` (2.13:1 contrast ratio) to `#7f8795` (3.56:1) to meet the minimum 3:1 readability threshold.

## [1.3.0] - 2026-06-09


### Added
- **Advanced Metadata Spoofing & Stripping**: Native GUI dialog with preset values (e.g., Camera Model, GPS location) to spoof or strip EXIF metadata from processed images.
- **Local Authentication Server**: Multi-threaded CORS-restricted auth server (`auth_server.py`) handling secure seamless activation callbacks from the DotSuite web dashboard.
- **Secure Staging Build Pipeline**: Staging build compiler script (`build.py` and `setup_license.py`) that uses Cython to compile sensitive license verification modules to native machine code (`.so` / `.pyd`) and isolates the bundling workspace.

### Changed
- **Digital Signature Updater Hardening**: Implemented strict Ed25519 cryptographic signature checks on the auto-updater to verify binary signatures before hot-swapping executables.
- **Production Routing Redirect**: Pointed `AUTH_BASE_URL` to production endpoint `https://dotsuite.vercel.app` instead of local development port.
- **Arabic Preview Unicode Compatibility**: Replaced `cv2.imread` with Unicode-aware numpy decoders in `image_picker.py` to fix crashes on Arabic and unicode directory paths.

### Fixed
- **In-Memory License Verification Thread Safety**: Restricted disk I/O of license state to background/startup, using safe thread locks and event synchronization to eliminate UI thread frame drops.
- **Base64 Decoding Crashes**: Added dynamic padding logic to verify token parsing from OAuth endpoints without throwing unexpected errors.
- **Model Incomplete Download Handlers**: Enforced a minimum model file size constraint (>1MB) to automatically catch and recover from incomplete/zero-byte model downloads.
- **Text File Busy Build Glitch**: Fixed PyInstaller release copying error by unlinking files prior to overwrite on Linux systems.

## [1.2.3] - 2026-01-31

### Added
- **MVC Architecture**: Complete refactoring of the codebase into a robust Model-View-Controller pattern for improved stability and scalability.
- **Native Arabic Support**: Full RTL (Right-to-Left) layout engine that dynamically mirrors the interface for Arabic users.
- **Instant Auto-Save**: Integrated SQLite database (`DatabaseManager`) to automatically persist user preferences, window state, and effect settings in real-time.
- **Advanced Theme System**: New Theme Manager with persistent selection and optimized color palettes (e.g., Cyberpunk, One Dark).
- **Drag & Drop Support**: Native support for dragging images directly into the application window.
- **Enhanced UI Controls**: Replaced static numeric entry fields with intuitive sliders for Blur Strength, Pixel Size, and Opacity.
- **Secure Build Pipeline**: Advanced `build.py` script handling PyArmor obfuscation and PyInstaller compilation for Windows, Linux, and macOS.

### Changed
- **UI Logic**: Decoupled Toolbar buttons from Control Panel buttons to prevent state conflicts and ensure independent functionality.
- **Localization Engine**: The UI now completely rebuilds upon language change to ensure 100% text translation and correct text direction/alignment.
- **Project Structure**: Migrated source code to a modular `src/` directory structure complying with modern Python standards.
- **Performance**: Optimized real-time preview rendering pipeline for smoother adjustments.

### Fixed
- **Button State Management**: Resolved critical issue where buttons became unresponsive ("dead") after switching languages or themes.
- **CI/CD Build Paths**: Fixed `main.py` resolution errors in GitHub Actions pipeline by updating entry point logic.
- **Layout Glitches**: Fixed visual artifacts when resizing the window in RTL mode.

## [1.1.0] - 2025-12-10

### Added
- **Complete Auto-Update System**: Seamless over-the-air updates with silent background downloads and unobtrusive status bar notifications
- **Smart Auto-Update**: Passive update system that downloads updates without interrupting user workflow
- **Enterprise Directory Structure**: Professional AppData integration following OS standards (Windows %APPDATA%, Linux ~/.local/share, macOS ~/Library/Application Support)
- **GitHub Actions Integration**: Automated CI/CD pipeline with version injection and cross-platform builds
- **Enhanced Build System**: Improved PyInstaller configuration with PIL/Tkinter hooks for reliable executable generation
- **Status Bar Notifications**: Non-intrusive update ready indicators in the application status bar
- **Automatic Cleanup**: Background cleanup of temporary update files
- **Cross-Platform Path Handling**: Robust path management for Windows, Linux, and macOS
- **Version Management**: Dynamic version injection from GitHub tags with fallback support
- **Menu Enhancements**: Added "Open Exports Folder" and "Open App Data Folder" options for easy access
- **CLI Mode Preparation**: Foundation for command-line interface usage
- **Package Installation Support**: Setup.py configuration for potential APT/PIP distribution

### Changed
- **Directory Structure**: Migrated from portable folders to professional native app structure
- **Update Experience**: Transformed from modal dialogs to passive status bar notifications
- **Build Process**: Enhanced with comprehensive PyInstaller hooks and cross-platform compatibility
- **Code Architecture**: Improved separation of silent vs interactive update flows
- **Error Handling**: Added comprehensive error handling for all platforms and edge cases
- **User Experience**: Eliminated disruptive update prompts in favor of user-controlled updates

### Technical
- **Auto-Update Engine**: Implemented observer pattern with background threading for seamless updates
- **Path Abstraction**: Cross-platform directory handling with automatic parent directory creation
- **Binary Replacement**: Safe file replacement using absolute paths and proper batch scripting
- **Memory Management**: Minimal memory footprint with efficient background processing
- **Security**: HTTPS-only API calls and secure file operations
- **Compatibility**: Full support for Windows, Linux, and macOS with platform-specific optimizations

## [1.0.0] - 2023-12-06

### Added
- Initial production release of DotScramble
- Multiple detection modes: Face, Eye, Full Body, License Plate, Text (OCR), Manual Selection, Full Image
- Multiple effects: Gaussian Blur, Pixelation, Black Bar, Gradient Fade, Mosaic, Frosted Glass, Oil Paint
- Real-time preview functionality
- Batch processing for multiple images
- Undo/Redo history management
- Preset system for saving/loading effect settings
- Comparison view for before/after
- Keyboard shortcuts for fast workflow
- Opacity control for blending effects
- Image info display
- GUI interface with main and batch processing windows
- Modular code structure with core, gui, and utilities
