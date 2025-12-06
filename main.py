"""
Advanced Image Privacy Studio Pro - Main Entry Point
Production-ready version with error handling and logging
"""
import tkinter as tk
from tkinter import messagebox
import sys
import os
import logging
from pathlib import Path

# Configure logging
def setup_logging():
    """Setup application logging"""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_dir / 'privacy_studio.log'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)


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
        messagebox.showerror("Missing Dependencies", error_msg)
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
    messagebox.showerror("Error", error_msg)


def main():
    """Main application entry point"""
    global logger
    
    # Setup logging
    logger = setup_logging()
    logger.info("=" * 50)
    logger.info("Advanced Image Privacy Studio Pro - Starting")
    logger.info("=" * 50)
    
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
        
        # Import GUI (after dependency check)
        from gui.main_window import AdvancedPrivacyStudioPro
        
        # Create and run application
        logger.info("Initializing GUI...")
        root = tk.Tk()
        
        # Set application icon (if exists)
        try:
            if os.path.exists('icon.ico'):
                root.iconbitmap('icon.ico')
        except:
            pass
        
        app = AdvancedPrivacyStudioPro(root)
        logger.info("Application initialized successfully")
        
        # Start main loop
        logger.info("Starting main loop")
        root.mainloop()
        
    except ImportError as e:
        error_msg = f"Import error: {str(e)}\n\n"
        error_msg += "Please ensure all modules are in the correct location:\n"
        error_msg += "- gui/main_window.py\n"
        error_msg += "- gui/batch_window.py\n"
        error_msg += "- core/image_processor.py\n"
        error_msg += "- core/batch_processor.py\n"
        error_msg += "- core/utils.py\n"
        error_msg += "- config.py"
        
        logger.error(error_msg)
        messagebox.showerror("Import Error", error_msg)
        sys.exit(1)
        
    except Exception as e:
        logger.error(f"Fatal error during initialization: {str(e)}", exc_info=True)
        messagebox.showerror("Fatal Error", 
                           f"Failed to start application:\n\n{str(e)}\n\n"
                           "Please check the log file for details.")
        sys.exit(1)
    
    finally:
        logger.info("Application shutting down")
        logger.info("=" * 50)


if __name__ == "__main__":
    main()