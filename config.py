"""
Configuration settings for Advanced Privacy Studio Pro
Enhanced version with validation and environment support
"""
import os
import sys
from pathlib import Path

# ============================================================================
# APPLICATION INFO & VERSION INJECTION
# ============================================================================
APP_NAME = "DotScramble"  # Keep the name matching the repository name
APP_AUTHOR = "Privacy Studio Team"

# The magical attempt to read version from GitHub Action
try:
    from version_info import VERSION as APP_VERSION
except ImportError:
    APP_VERSION = "1.1.1-dev"  # Developer version

# ============================================================================
# DIRECTORIES (Enterprise Standard - AppData)
# ============================================================================
def get_app_data_path():
    """
    Determine data storage path based on OS standards
    Windows: %APPDATA%/DotScramble
    Linux/Mac: ~/.local/share/DotScramble
    """
    home = Path.home()

    if sys.platform == "win32":
        # C:\Users\User\AppData\Roaming\DotScramble
        base_path = Path(os.getenv('APPDATA')) / APP_NAME
    elif sys.platform == "darwin":
        # /Users/User/Library/Application Support/DotScramble
        base_path = home / "Library" / "Application Support" / APP_NAME
    else:
        # /home/user/.local/share/DotScramble
        base_path = home / ".local" / "share" / APP_NAME

    return base_path

# 1. System files (hidden from regular user view)
SYSTEM_DIR = get_app_data_path()

# 2. Export files (user images) - should be visible
# Put them in Documents for easy access
DOCUMENTS_DIR = Path.home() / "Documents" / f"{APP_NAME}_Exports"

# ============================================================================
# UI COLORS - Modern Dark Theme
# ============================================================================
COLORS = {
    'bg_dark': '#0a0a0f',
    'bg_medium': '#16213e',
    'bg_light': '#1a2332',
    'accent_cyan': '#00fff5',
    'accent_pink': '#ff6b9d',
    'accent_red': '#e94560',
    'accent_orange': '#f39c12',
    'accent_green': '#26a69a',
    'accent_purple': '#533483',
    'text_white': '#ffffff',
    'text_gray': '#888888',
    'canvas_bg': '#0f0f1e'
}

# ============================================================================
# EFFECT PARAMETERS
# ============================================================================
BLUR_RANGE = {
    'min': 15,
    'max': 199,
    'default': 51,
    'step': 2
}

PIXEL_RANGE = {
    'min': 5,
    'max': 50,
    'default': 15,
    'step': 1
}

OPACITY_RANGE = {
    'min': 0,
    'max': 100,
    'default': 100,
    'step': 1
}

EDGE_BLUR_RANGE = {
    'min': 0,
    'max': 50,
    'default': 10,
    'step': 1
}

# ============================================================================
# EFFECTS CONFIGURATION
# ============================================================================
EFFECTS = {
    'blur': {
        'name': 'Gaussian Blur',
        'icon': '🌫️',
        'description': 'Smooth blur effect using Gaussian algorithm',
        'parameters': ['blur_strength', 'opacity']
    },
    'pixelation': {
        'name': 'Pixelation',
        'icon': '🔲',
        'description': 'Classic pixel censoring effect',
        'parameters': ['pixel_size', 'opacity']
    },
    'black_bar': {
        'name': 'Black Bar',
        'icon': '⬛',
        'description': 'Solid black censoring bar',
        'parameters': ['opacity']
    },
    'gradient': {
        'name': 'Gradient Fade',
        'icon': '🎭',
        'description': 'Artistic gradient fade effect',
        'parameters': ['opacity']
    },
    'mosaic': {
        'name': 'Mosaic',
        'icon': '🔳',
        'description': 'Mosaic tile effect',
        'parameters': ['opacity']
    },
    'glass': {
        'name': 'Frosted Glass',
        'icon': '❄️',
        'description': 'Glass-like blur effect',
        'parameters': ['blur_strength', 'opacity']
    },
    'oil_paint': {
        'name': 'Oil Paint',
        'icon': '🎨',
        'description': 'Artistic oil painting effect',
        'parameters': ['opacity']
    }
}



# ============================================================================
# EFFECT LIST (For GUI Rendering)
# ============================================================================
EFFECT_LIST = [
    (EFFECTS['blur']['icon'] + " Blur", "blur"),
    (EFFECTS['pixelation']['icon'] + " Pixelation", "pixelation"),
    (EFFECTS['black_bar']['icon'] + " Black Bar", "black_bar"),
    (EFFECTS['gradient']['icon'] + " Gradient", "gradient"),
    (EFFECTS['mosaic']['icon'] + " Mosaic", "mosaic"),
    (EFFECTS['glass']['icon'] + " Frosted Glass", "glass"),
    (EFFECTS['oil_paint']['icon'] + " Oil Paint", "oil_paint"),
]

# ============================================================================
# DETECTION MODES
# ============================================================================
DETECTION_MODES = {
    'face': {
        'name': 'Face Detection',
        'icon': '🎭',
        'description': 'Detect and process human faces',
        'cascade': 'haarcascade_frontalface_default.xml'
    },
    'eye': {
        'name': 'Eye Detection',
        'icon': '👁️',
        'description': 'Detect and process eyes',
        'cascade': 'haarcascade_eye.xml'
    },
    'body': {
        'name': 'Full Body',
        'icon': '🧍',
        'description': 'Detect and process full body',
        'cascade': 'haarcascade_fullbody.xml'
    },
    'license_plate': {
        'name': 'License Plate',
        'icon': '🚗',
        'description': 'Detect and process license plates',
        'cascade': None  # Uses custom algorithm
    },
    'text': {
        'name': 'Text Detection',
        'icon': '📝',
        'description': 'Detect and process text regions (requires Tesseract)',
        'cascade': None  # Uses OCR
    },
    'manual': {
        'name': 'Manual Selection',
        'icon': '✏️',
        'description': 'Manually draw regions to process',
        'cascade': None
    },
    'full': {
        'name': 'Full Image',
        'icon': '🌍',
        'description': 'Process entire image',
        'cascade': None
    }
}

# ============================================================================
# DETECTION LIST (For GUI Rendering)
# ============================================================================
DETECTION_LIST = [
    (DETECTION_MODES['face']['icon'] + " Face", "face"),
    (DETECTION_MODES['eye']['icon'] + " Eyes", "eye"),
    (DETECTION_MODES['body']['icon'] + " Full Body", "body"),
    (DETECTION_MODES['license_plate']['icon'] + " License Plate", "license_plate"),
    (DETECTION_MODES['text']['icon'] + " Text", "text"),
    (DETECTION_MODES['manual']['icon'] + " Manual", "manual"),
    (DETECTION_MODES['full']['icon'] + " Full Image", "full"),
]

# ============================================================================
# FILE HANDLING
# ============================================================================
SUPPORTED_FORMATS = [
    ("All Supported Images", "*.jpg *.jpeg *.png *.bmp *.gif *.tiff *.webp"),
    ("JPEG Images", "*.jpg *.jpeg"),
    ("PNG Images", "*.png"),
    ("BMP Images", "*.bmp"),
    ("TIFF Images", "*.tiff *.tif"),
    ("WebP Images", "*.webp"),
    ("All Files", "*.*")
]

SAVE_FORMATS = [
    ("JPEG (High Quality)", "*.jpg"),
    ("PNG (Lossless)", "*.png"),
    ("BMP (Uncompressed)", "*.bmp"),
    ("TIFF (Archive Quality)", "*.tiff")
]

# Image size limits (pixels)
MAX_IMAGE_WIDTH = 4000
MAX_IMAGE_HEIGHT = 4000
MAX_IMAGE_SIZE_MB = 50  # Maximum file size in MB

# ============================================================================
# HISTORY & PERFORMANCE
# ============================================================================
MAX_HISTORY = 20  # Maximum undo/redo steps
PREVIEW_DELAY = 100  # Milliseconds delay for real-time preview
AUTO_SAVE_INTERVAL = 300  # Seconds (5 minutes)

# ============================================================================
# DIRECTORY MAPPING
# ============================================================================
DIRS = {
    # System files go to the hidden location
    'backups': SYSTEM_DIR / 'backups',
    'logs': SYSTEM_DIR / 'logs',
    'presets': SYSTEM_DIR / 'presets',
    'temp': SYSTEM_DIR / 'temp',

    # Images go to Documents (user-visible)
    'exports': DOCUMENTS_DIR
}

# Create all directories
for directory in DIRS.values():
    directory.mkdir(parents=True, exist_ok=True)

# ============================================================================
# BATCH PROCESSING
# ============================================================================
BATCH_OUTPUT_FOLDER = "processed_images"
BATCH_THREAD_COUNT = 1  # Number of processing threads (be careful with OpenCV)
BATCH_AUTO_SAVE = True  # Auto-save settings after batch

# ============================================================================
# PRESETS
# ============================================================================
PRESET_FILE = DIRS['presets'] / 'user_presets.json'

EFFECT_PRESETS = {
    'Light Privacy': {
        'description': 'Subtle privacy protection',
        'effect': 'blur',
        'blur_strength': 31,
        'opacity': 70,
        'detection_mode': 'face'
    },
    'Medium Privacy': {
        'description': 'Balanced privacy and visibility',
        'effect': 'pixelation',
        'pixel_size': 15,
        'opacity': 100,
        'detection_mode': 'face'
    },
    'Maximum Privacy': {
        'description': 'Complete censoring',
        'effect': 'black_bar',
        'opacity': 100,
        'detection_mode': 'face'
    },
    'Artistic Blur': {
        'description': 'Aesthetic blur effect',
        'effect': 'glass',
        'blur_strength': 41,
        'opacity': 90,
        'detection_mode': 'face'
    },
    'License Plate Blur': {
        'description': 'For vehicle privacy',
        'effect': 'blur',
        'blur_strength': 75,
        'opacity': 100,
        'detection_mode': 'license_plate'
    },
    'Text Redaction': {
        'description': 'Hide sensitive text',
        'effect': 'black_bar',
        'opacity': 100,
        'detection_mode': 'text'
    }
}

# ============================================================================
# KEYBOARD SHORTCUTS
# ============================================================================
SHORTCUTS = {
    'load': '<Control-o>',
    'save': '<Control-s>',
    'save_as': '<Control-Shift-S>',
    'undo': '<Control-z>',
    'redo': '<Control-y>',
    'process': '<Control-p>',
    'clear': '<Control-d>',
    'batch': '<Control-b>',
    'quit': '<Control-q>',
    'export': '<Control-e>',
    'preferences': '<Control-comma>'
}

# ============================================================================
# UI SETTINGS
# ============================================================================
WINDOW_SETTINGS = {
    'main': {
        'width': 1400,
        'height': 900,
        'min_width': 1000,
        'min_height': 700
    },
    'batch': {
        'width': 900,
        'height': 650,
        'min_width': 700,
        'min_height': 500
    }
}

# Canvas settings
CANVAS_PADDING = 20
CANVAS_BG_COLOR = COLORS['canvas_bg']

# Fonts
FONTS = {
    'title': ('Helvetica', 24, 'bold'),
    'heading': ('Helvetica', 18, 'bold'),
    'subheading': ('Helvetica', 13, 'bold'),
    'normal': ('Helvetica', 10),
    'small': ('Helvetica', 9),
    'code': ('Courier', 10)
}

# ============================================================================
# RADIOBUTTON THEME (Unified Style)
# ============================================================================
RADIO_BASE = {
    "font": ("Helvetica", 10),
    "bg": COLORS['bg_medium'],
    "fg": COLORS['text_white'],
}

RADIO_STYLE = {
    # Remove borders / highlight
    "highlightthickness": 0,
    "borderwidth": 0,
    "highlightbackground": COLORS['bg_medium'],
    "highlightcolor": COLORS['bg_medium'],

    # Active colors
    "activebackground": COLORS['bg_medium'],
    "activeforeground": COLORS['text_white'],

    # Selection fill (the small dot background)
    "selectcolor": COLORS['bg_light'],
}

# ============================================================================
# UPDATE CONFIGURATION
# ============================================================================
UPDATE_CONFIG = {
    'repo_owner': 'kareem2099',
    'repo_name': 'DotScramble',
    'auto_check': True,  # Enable automatic update checks
    'check_interval_days': 7  # How often to check for updates
}

# ============================================================================
# ADVANCED SETTINGS
# ============================================================================
ADVANCED = {
    'enable_gpu': False,  # Enable GPU acceleration (requires opencv-contrib)
    'compression_quality': 95,  # JPEG compression quality (0-100)
    'png_compression': 6,  # PNG compression level (0-9)
    'backup_originals': True,  # Create backup of originals
    'show_tooltips': True,  # Show tooltips on UI elements
    'auto_detect_on_load': False,  # Auto-detect regions when loading image
    'preview_quality': 'medium',  # Preview quality: 'low', 'medium', 'high'
    'memory_limit_mb': 500  # Maximum memory usage in MB
}

# ============================================================================
# LOGGING
# ============================================================================
LOGGING = {
    'level': 'INFO',  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    'file': DIRS['logs'] / 'privacy_studio.log',
    'max_size_mb': 10,  # Max log file size before rotation
    'backup_count': 3  # Number of backup log files to keep
}

# ============================================================================
# VALIDATION FUNCTIONS
# ============================================================================
def validate_config():
    """Validate configuration settings"""
    errors = []
    
    # Check blur range
    if BLUR_RANGE['min'] >= BLUR_RANGE['max']:
        errors.append("BLUR_RANGE: min must be less than max")
    
    if BLUR_RANGE['min'] % 2 == 0:
        errors.append("BLUR_RANGE: min must be odd number")
    
    # Check image size limits
    if MAX_IMAGE_WIDTH <= 0 or MAX_IMAGE_HEIGHT <= 0:
        errors.append("Image size limits must be positive")
    
    # Check history limit
    if MAX_HISTORY < 1:
        errors.append("MAX_HISTORY must be at least 1")
    
    # Check directories exist
    for name, path in DIRS.items():
        if not path.exists():
            errors.append(f"Directory does not exist: {name} ({path})")
    
    return errors


def get_cascade_path(mode):
    """Get full path to cascade file for detection mode"""
    import cv2
    
    if mode not in DETECTION_MODES:
        return None
    
    cascade_file = DETECTION_MODES[mode].get('cascade')
    if cascade_file is None:
        return None
    
    return cv2.data.haarcascades + cascade_file


# ============================================================================
# ENVIRONMENT-SPECIFIC SETTINGS
# ============================================================================
# Override settings based on environment variables
if os.getenv('PRIVACY_STUDIO_DEBUG'):
    LOGGING['level'] = 'DEBUG'

if os.getenv('PRIVACY_STUDIO_GPU'):
    ADVANCED['enable_gpu'] = True

# ============================================================================
# EXPORT CONFIGURATION
# ============================================================================
__all__ = [
    'APP_NAME', 'APP_VERSION', 'APP_AUTHOR',
    'COLORS', 'BLUR_RANGE', 'PIXEL_RANGE', 'OPACITY_RANGE', 'EDGE_BLUR_RANGE',
    'EFFECTS', 'DETECTION_MODES', 'SUPPORTED_FORMATS', 'SAVE_FORMATS',
    'MAX_HISTORY', 'BATCH_OUTPUT_FOLDER', 'EFFECT_PRESETS', 'SHORTCUTS',
    'WINDOW_SETTINGS', 'FONTS', 'ADVANCED', 'LOGGING', 'DIRS',
    'RADIO_BASE', 'RADIO_STYLE', 'UPDATE_CONFIG',
    'validate_config', 'get_cascade_path'
]

# Validate configuration on import
_config_errors = validate_config()
if _config_errors:
    import warnings
    for error in _config_errors:
        warnings.warn(f"Configuration error: {error}")
