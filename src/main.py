"""
DotScramble - Main Entry Point (PySide6 version)
"""
import sys
import os
import logging
from pathlib import Path

# Configure logging
logger = logging.getLogger(__name__)

def setup_logging():
    """Setup application logging"""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_dir / 'dot_scramble.log'),
            logging.StreamHandler()
        ]
    )


def check_dependencies():
    """Check if all required dependencies are installed"""
    missing_deps = []
    
    try:
        import cv2
    except ImportError:
        missing_deps.append("opencv-python")
    
    try:
        import numpy
    except ImportError:
        missing_deps.append("numpy")
    
    try:
        import PIL
    except ImportError:
        missing_deps.append("Pillow")
    
    # Optional dependencies
    try:
        import pytesseract
    except ImportError:
        logging.warning("pytesseract not installed - text detection will be limited")
    
    if missing_deps:
        error_msg = f"Missing required dependencies:\n\n{', '.join(missing_deps)}\n\n"
        error_msg += "Please install them using:\n"
        error_msg += f"pip install {' '.join(missing_deps)}"
        
        # Log to console first — GUI may not be ready yet
        logging.error(error_msg)
        
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox
            # QApplication MUST exist before any QWidget (including QMessageBox)
            app = QApplication.instance() or QApplication(sys.argv)
            QMessageBox.critical(None, "Missing Dependencies", error_msg)
        except Exception:
            pass  # If Qt is unavailable, console log above is enough
        
        return False
    
    return True


def verify_opencv_cascades():
    """Verify OpenCV cascade files are available"""
    import cv2
    
    required_cascades = {
        'Face': 'haarcascade_frontalface_default.xml',
        'Eye': 'haarcascade_eye.xml',
        'Body': 'haarcascade_fullbody.xml'
    }
    
    missing_cascades = []
    for name, cascade_file in required_cascades.items():
        cascade_path = cv2.data.haarcascades + cascade_file
        if not os.path.exists(cascade_path):
            missing_cascades.append(f"{name}: {cascade_file}")
    
    if missing_cascades:
        logging.warning(f"Missing cascade files: {', '.join(missing_cascades)}")
        logging.warning("Some detection modes may not work properly")
    
    return True


def create_required_directories():
    """Create required application directories"""
    directories = ['backups', 'logs', 'exports']
    
    for directory in directories:
        Path(directory).mkdir(exist_ok=True)


def handle_exception(exc_type, exc_value, exc_traceback):
    """Global exception handler"""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    
    logger.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))
    
    error_msg = f"An unexpected error occurred:\n\n{exc_value}\n\n"
    error_msg += "Please check the log file for details."
    
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
        app = QApplication.instance()
        if not app:
            app = QApplication(sys.argv)
        QMessageBox.critical(None, "Error", error_msg)
    except Exception:
        print(error_msg, file=sys.stderr)


def setup_tesseract_configuration():
    """Configure Tesseract path for bundled environments"""
    try:
        import pytesseract
        
        # Platform-aware binary name: .exe on Windows, plain name elsewhere
        tesseract_bin = "tesseract.exe" if sys.platform == "win32" else "tesseract"
        
        # Determine the base path based on how the app is running
        if getattr(sys, 'frozen', False):
            # If running as a compiled executable
            base_path = os.path.dirname(sys.executable)
        else:
            # If running from source script
            base_path = os.path.dirname(os.path.abspath(__file__))
            
        # Look for the bundled Tesseract folder
        tesseract_path = os.path.join(base_path, "Tesseract-OCR", tesseract_bin)
        
        # If running from source, sometimes Tesseract is one level up or in current dir
        if not os.path.exists(tesseract_path) and not getattr(sys, 'frozen', False):
             # Fallback check for dev environment
             tesseract_path = os.path.join(base_path, "..", "Tesseract-OCR", tesseract_bin)

        if os.path.exists(tesseract_path):
            pytesseract.pytesseract.tesseract_cmd = tesseract_path
            logging.info(f"✅ Bundled Tesseract found and configured at: {tesseract_path}")
        else:
            logging.warning(f"⚠️ Tesseract executable not found at: {tesseract_path}")
            
    except Exception as e:
        logging.error(f"Error configuring Tesseract: {e}")


def setup_linux_desktop_entry():
    """Automatically create a .desktop entry for Linux systems if running as a frozen executable"""
    if not sys.platform.startswith('linux') or not getattr(sys, 'frozen', False):
        return
        
    try:
        import stat
        import shutil
        from src.config import SYSTEM_DIR
        
        current_exe = sys.executable
        base_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
        # Determine the target .desktop file path
        home = Path.home()
        desktop_dir = home / ".local" / "share" / "applications"
        desktop_dir.mkdir(parents=True, exist_ok=True)
        desktop_file = desktop_dir / "DotScramble.desktop"
        
        # Clean up old lowercase desktop file if it exists
        old_desktop = desktop_dir / "dotscramble.desktop"
        if old_desktop.exists():
            try:
                old_desktop.unlink()
            except:
                pass
                
        # Ensure our persistent data directory exists
        SYSTEM_DIR.mkdir(parents=True, exist_ok=True)
        icon_dest = SYSTEM_DIR / "icon.png"
        
        # Copy the icon from the frozen bundle to the persistent app data directory
        icon_src = os.path.join(base_dir, 'assets', 'icons', 'Square150x150Logo.png')
        if not os.path.exists(icon_src):
            icon_src = os.path.join(base_dir, 'assets', 'icons', 'icon.png')
            
        if os.path.exists(icon_src):
            shutil.copy2(icon_src, icon_dest)
            
        desktop_content = f"""[Desktop Entry]
Type=Application
Name=DotScramble
Comment=Advanced Privacy Studio Pro
Exec="{current_exe}"
Icon={icon_dest}
Terminal=false
Categories=Utility;Graphics;
StartupWMClass=DotScramble
"""
        # Only write if it doesn't exist, or if the Exec path or StartupWMClass is missing/different
        write_needed = True
        if desktop_file.exists():
            try:
                content = desktop_file.read_text()
                if (f'Exec="{current_exe}"' in content or f'Exec={current_exe}' in content) and 'StartupWMClass' in content:
                    write_needed = False
            except:
                pass
                
        if write_needed:
            desktop_file.write_text(desktop_content)
            # Make the .desktop file executable
            st = os.stat(desktop_file)
            os.chmod(desktop_file, st.st_mode | stat.S_IEXEC)
            logger.info("✅ Created Linux desktop shortcut at: %s", desktop_file)
    except Exception as e:
        logger.warning("⚠️ Could not create Linux desktop entry: %s", e)


def main():
    """Main application entry point"""
    # Setup logging
    setup_logging()
    logger.info("=" * 50)
    logger.info("DotScramble - Starting")
    logger.info("=" * 50)
    
    # Configure Bundled Tesseract
    setup_tesseract_configuration()
    
    # Set global exception handler
    sys.excepthook = handle_exception
    
    try:
        # Check dependencies
        if not check_dependencies():
            logger.error("Dependency check failed")
            sys.exit(1)
        
        # Verify OpenCV cascades
        verify_opencv_cascades()
        
        # Create required directories
        create_required_directories()
        logger.info("Required directories created/verified")
        
        # Automatically setup desktop entry on Linux
        setup_linux_desktop_entry()
        
        from PySide6.QtWidgets import QApplication
        from PySide6.QtGui import QIcon
        from src.views.main_window import AdvancedPrivacyStudioPro
        
        # Create QApplication
        app = QApplication(sys.argv)
        logger.info("Initializing GUI...")
        
        # Instantiate main window view
        main_window = AdvancedPrivacyStudioPro()
        
        # Set application icon
        try:
            base_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            png_path = os.path.join(base_dir, 'assets', 'icons', 'Square150x150Logo.png')
            if not os.path.exists(png_path):
                png_path = os.path.join(base_dir, 'assets', 'icons', 'icon.png')
            
            if os.path.exists(png_path):
                app_icon = QIcon(png_path)
                app.setWindowIcon(app_icon)
                main_window.setWindowIcon(app_icon)
        except Exception as e:
            logger.debug(f"Failed to set application icon: {e}")
            
        main_window.show()
        logger.info("Application initialized successfully")
        
        # Start main loop
        logger.info("Starting main loop")
        sys.exit(app.exec())
        
    except ImportError as e:
        error_msg = f"Import error: {str(e)}\n\n"
        error_msg += "Please ensure all modules are in the correct location:\n"
        error_msg += "- src/views/main_window.py\n"
        error_msg += "- gui/batch_window.py\n"
        error_msg += "- core/image_processor.py\n"
        error_msg += "- core/batch_processor.py\n"
        error_msg += "- core/utils.py\n"
        error_msg += "- config.py"
        
        logger.error(error_msg)
        try:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(None, "Import Error", error_msg)
        except Exception:
            print(error_msg, file=sys.stderr)
        sys.exit(1)
        
    except Exception as e:
        logger.error(f"Fatal error during initialization: {str(e)}", exc_info=True)
        try:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(None, "Fatal Error", 
                                 f"Failed to start application:\n\n{str(e)}\n\n"
                                 "Please check the log file for details.")
        except Exception:
            print(f"Fatal Error: {e}", file=sys.stderr)
        sys.exit(1)
    
    finally:
        logger.info("Application shutting down")
        logger.info("=" * 50)


if __name__ == "__main__":
    main()