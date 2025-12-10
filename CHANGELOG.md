# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
- Initial production release of Advanced Image Privacy Studio Pro
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
