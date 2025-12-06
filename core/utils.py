"""
Utility functions for the Privacy Studio
"""
import cv2
import numpy as np
import json
import os
from datetime import datetime
from PIL import Image, ImageTk
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from config import SUPPORTED_FORMATS, MAX_HISTORY, DIRS, PRESET_FILE

class HistoryManager:
    """Manage undo/redo history"""

    def __init__(self, max_history=MAX_HISTORY):
        self.history = []
        self.redo_stack = []
        self.max_history = max_history
    
    def save_state(self, image):
        """Save current state to history"""
        if image is not None:
            self.history.append(image.copy())
            if len(self.history) > self.max_history:
                self.history.pop(0)
            self.redo_stack = []
    
    def undo(self):
        """Undo last operation"""
        if len(self.history) > 0:
            return self.history.pop()
        return None
    
    def redo(self):
        """Redo last undone operation"""
        if len(self.redo_stack) > 0:
            return self.redo_stack.pop()
        return None
    
    def add_to_redo(self, image):
        """Add image to redo stack"""
        if image is not None:
            self.redo_stack.append(image.copy())
    
    def can_undo(self):
        """Check if undo is available"""
        return len(self.history) > 0
    
    def can_redo(self):
        """Check if redo is available"""
        return len(self.redo_stack) > 0
    
    def clear(self):
        """Clear all history"""
        self.history = []
        self.redo_stack = []


class PresetManager:
    """Manage effect presets"""

    def __init__(self, preset_file=PRESET_FILE):
        self.preset_file = preset_file
        self.presets = self.load_presets()
    
    def load_presets(self):
        """Load presets from file"""
        if os.path.exists(self.preset_file):
            try:
                with open(self.preset_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {}
    
    def save_presets(self):
        """Save presets to file"""
        try:
            with open(self.preset_file, 'w') as f:
                json.dump(self.presets, f, indent=4)
            return True
        except:
            return False
    
    def add_preset(self, name, settings):
        """Add a new preset"""
        self.presets[name] = settings
        self.save_presets()
    
    def delete_preset(self, name):
        """Delete a preset"""
        if name in self.presets:
            del self.presets[name]
            self.save_presets()
            return True
        return False
    
    def get_preset(self, name):
        """Get preset by name"""
        return self.presets.get(name, None)
    
    def get_all_presets(self):
        """Get all preset names"""
        return list(self.presets.keys())


class ImageUtils:
    """Image utility functions"""
    
    @staticmethod
    def resize_for_display(image, max_width, max_height, padding=0.95):
        """Resize image to fit display area"""
        h, w = image.shape[:2]
        scale = min(max_width/w, max_height/h) * padding
        new_w, new_h = int(w*scale), int(h*scale)
        resized = cv2.resize(image, (new_w, new_h))
        return resized, scale
    
    @staticmethod
    def cv2_to_pil(cv_image):
        """Convert OpenCV image to PIL Image"""
        rgb_image = cv2.cvtColor(cv_image, cv2.COLOR_BGR2RGB)
        return Image.fromarray(rgb_image)
    
    @staticmethod
    def pil_to_cv2(pil_image):
        """Convert PIL Image to OpenCV image"""
        rgb_image = np.array(pil_image)
        return cv2.cvtColor(rgb_image, cv2.COLOR_RGB2BGR)
    
    @staticmethod
    def create_thumbnail(image, size=(100, 100)):
        """Create thumbnail of image"""
        h, w = image.shape[:2]
        scale = min(size[0]/w, size[1]/h)
        new_w, new_h = int(w*scale), int(h*scale)
        thumbnail = cv2.resize(image, (new_w, new_h))
        return thumbnail
    
    @staticmethod
    def get_image_info(image):
        """Get image information"""
        h, w = image.shape[:2]
        channels = image.shape[2] if len(image.shape) > 2 else 1
        size_kb = image.nbytes / 1024
        
        return {
            'width': w,
            'height': h,
            'channels': channels,
            'size_kb': f"{size_kb:.2f}"
        }
    
    @staticmethod
    def compare_images(img1, img2):
        """Compare two images and return difference"""
        if img1.shape != img2.shape:
            return None
        
        diff = cv2.absdiff(img1, img2)
        return diff
    
    @staticmethod
    def add_watermark(image, text, position='bottom-right'):
        """Add watermark to image"""
        h, w = image.shape[:2]
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.7
        thickness = 2
        
        # Get text size
        text_size = cv2.getTextSize(text, font, font_scale, thickness)[0]
        
        # Calculate position
        if position == 'bottom-right':
            x = w - text_size[0] - 10
            y = h - 10
        elif position == 'bottom-left':
            x = 10
            y = h - 10
        elif position == 'top-right':
            x = w - text_size[0] - 10
            y = text_size[1] + 10
        else:  # top-left
            x = 10
            y = text_size[1] + 10
        
        # Draw text with outline
        cv2.putText(image, text, (x, y), font, font_scale, (0, 0, 0), thickness + 2)
        cv2.putText(image, text, (x, y), font, font_scale, (255, 255, 255), thickness)
        
        return image


class ExportManager:
    """Handle export operations"""
    
    @staticmethod
    def export_with_metadata(image, filepath, metadata=None):
        """Export image with metadata"""
        cv2.imwrite(filepath, image)
        
        if metadata:
            meta_path = filepath + '.meta'
            with open(meta_path, 'w') as f:
                json.dump(metadata, f, indent=4)
    
    @staticmethod
    def export_comparison(original, processed, filepath):
        """Export side-by-side comparison"""
        # Ensure same height
        h1, w1 = original.shape[:2]
        h2, w2 = processed.shape[:2]
        
        if h1 != h2:
            scale = h1 / h2
            w2_new = int(w2 * scale)
            processed = cv2.resize(processed, (w2_new, h1))
            w2 = w2_new
        
        # Create combined image
        combined = np.hstack((original, processed))
        
        # Add labels
        font = cv2.FONT_HERSHEY_SIMPLEX
        cv2.putText(combined, "Original", (10, 30), font, 1, (255, 255, 255), 2)
        cv2.putText(combined, "Processed", (w1 + 10, 30), font, 1, (255, 255, 255), 2)
        
        cv2.imwrite(filepath, combined)
    
    @staticmethod
    def export_with_settings(image, filepath, settings):
        """Export image and save settings used"""
        cv2.imwrite(filepath, image)
        
        settings_path = os.path.splitext(filepath)[0] + '_settings.json'
        with open(settings_path, 'w') as f:
            json.dump(settings, f, indent=4)


def format_timestamp():
    """Get formatted timestamp for filenames"""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def validate_image_path(path):
    """Validate if path is a valid image file"""
    # Extract extensions from SUPPORTED_FORMATS
    valid_extensions = set()
    for filter_tuple in SUPPORTED_FORMATS:
        # filter_tuple is like ("All Supported Images", "*.jpg *.jpeg *.png *.bmp *.gif *.tiff *.webp")
        if len(filter_tuple) >= 2 and filter_tuple[1]:
            patterns = filter_tuple[1].replace('*', '').split()
            valid_extensions.update(patterns)

    ext = os.path.splitext(path)[1].lower()
    return ext in valid_extensions and os.path.exists(path)


def create_backup(image, folder=str(DIRS['backups'])):
    """Create backup of image"""
    os.makedirs(folder, exist_ok=True)
    timestamp = format_timestamp()
    backup_path = os.path.join(folder, f'backup_{timestamp}.png')
    cv2.imwrite(backup_path, image)
    return backup_path
