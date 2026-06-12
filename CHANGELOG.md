# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
