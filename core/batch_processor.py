"""
Batch Image Processor Module
Handles processing multiple images in batch mode.
"""

import os
import cv2
from pathlib import Path
from typing import List, Tuple, Dict, Callable, Optional
import threading
import queue
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from config import SUPPORTED_FORMATS, BLUR_RANGE, PIXEL_RANGE, OPACITY_RANGE

class BatchProcessor:
    """Handles batch processing of multiple images"""

    def __init__(self, image_processor, detection_engine):
        self.image_processor = image_processor
        self.detection_engine = detection_engine
        self.results = []
        self.progress_callback = None
        self.error_callback = None

    def process_batch(self, input_paths: List[str], output_dir: str,
                     settings: Dict, progress_callback: Callable = None,
                     error_callback: Callable = None) -> List[Dict]:
        """
        Process multiple images with the given settings.

        Args:
            input_paths: List of paths to input images
            output_dir: Directory to save processed images
            settings: Dictionary containing processing settings
            progress_callback: Function to call for progress updates
            error_callback: Function to call on errors

        Returns:
            List of dictionaries containing processing results
        """
        self.results = []
        self.progress_callback = progress_callback
        self.error_callback = error_callback

        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)

        total_files = len(input_paths)

        for i, input_path in enumerate(input_paths):
            try:
                result = self._process_single_image(input_path, output_dir, settings)
                self.results.append(result)

                if progress_callback:
                    progress_callback(i + 1, total_files, result)

            except Exception as e:
                error_info = {
                    'input_path': input_path,
                    'success': False,
                    'error': str(e),
                    'output_path': None
                }
                self.results.append(error_info)

                if error_callback:
                    error_callback(input_path, str(e))

        return self.results

    def _process_single_image(self, input_path: str, output_dir: str, settings: Dict) -> Dict:
        """Process a single image with the given settings"""
        # Load image
        image = cv2.imread(input_path)
        if image is None:
            raise ValueError(f"Could not load image: {input_path}")

        # Get settings
        detection_mode = settings.get('detection_mode', 'face')
        effect_type = settings.get('effect_type', 'blur')
        effect_params = settings.get('effect_params', {})

        # Detect regions
        regions = self._detect_regions(image, detection_mode)

        if not regions:
            # If no regions detected, return original
            output_filename = f"processed_{Path(input_path).stem}.jpg"
            output_path = os.path.join(output_dir, output_filename)
            cv2.imwrite(output_path, image)
            return {
                'input_path': input_path,
                'output_path': output_path,
                'success': True,
                'regions_processed': 0,
                'error': None
            }

        # Apply effects to detected regions
        processed_image = image.copy()

        for (x, y, w, h) in regions:
            processed_image = self._apply_effect_to_region(
                processed_image, x, y, w, h, effect_type, effect_params
            )

        # Save processed image
        output_filename = f"processed_{Path(input_path).stem}.jpg"
        output_path = os.path.join(output_dir, output_filename)
        cv2.imwrite(output_path, processed_image)

        return {
            'input_path': input_path,
            'output_path': output_path,
            'success': True,
            'regions_processed': len(regions),
            'error': None
        }

    def _detect_regions(self, image, detection_mode: str) -> List[Tuple]:
        """Detect regions based on the specified mode"""
        if detection_mode == 'face':
            return self.detection_engine.detect_faces(image)
        elif detection_mode == 'eye':
            return self.detection_engine.detect_eyes(image)
        elif detection_mode == 'body':
            return self.detection_engine.detect_full_body(image)
        elif detection_mode == 'license_plate':
            return self.detection_engine.detect_license_plates(image)
        elif detection_mode == 'text':
            return self.detection_engine.detect_text(image)
        elif detection_mode == 'full':
            h, w = image.shape[:2]
            return [(0, 0, w, h)]
        else:
            return []

    def _apply_effect_to_region(self, image, x: int, y: int, w: int, h: int,
                               effect_type: str, effect_params: Dict):
        """Apply the specified effect to a region"""
        if effect_type == 'blur':
            strength = effect_params.get('blur_strength', BLUR_RANGE['default'])
            return self.image_processor.gaussian_blur(image, x, y, w, h, strength)
        elif effect_type == 'pixelation':
            pixel_size = effect_params.get('pixel_size', PIXEL_RANGE['default'])
            return self.image_processor.pixelate(image, x, y, w, h, pixel_size)
        elif effect_type == 'black_bar':
            return self.image_processor.black_bar(image, x, y, w, h)
        elif effect_type == 'gradient':
            return self.image_processor.gradient_fade(image, x, y, w, h)
        elif effect_type == 'mosaic':
            return self.image_processor.mosaic_effect(image, x, y, w, h)
        elif effect_type == 'glass':
            strength = effect_params.get('blur_strength', BLUR_RANGE['min'])
            return self.image_processor.frosted_glass(image, x, y, w, h)
        elif effect_type == 'oil_paint':
            return self.image_processor.oil_paint(image, x, y, w, h)
        else:
            return image

    def process_batch_async(self, input_paths: List[str], output_dir: str,
                           settings: Dict, progress_callback: Callable = None,
                           error_callback: Callable = None):
        """Process batch in a separate thread"""
        def worker():
            self.process_batch(input_paths, output_dir, settings,
                             progress_callback, error_callback)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        return thread

    def get_supported_formats(self) -> List[str]:
        """Get list of supported image formats"""
        # Extract extensions from SUPPORTED_FORMATS
        valid_extensions = set()
        for filter_tuple in SUPPORTED_FORMATS:
            # filter_tuple is like ("All Supported Images", "*.jpg *.jpeg *.png *.bmp *.gif *.tiff *.webp")
            if len(filter_tuple) >= 2 and filter_tuple[1]:
                patterns = filter_tuple[1].replace('*', '').split()
                valid_extensions.update(patterns)

        return list(valid_extensions)

    def validate_input_files(self, file_paths: List[str]) -> Tuple[List[str], List[str]]:
        """Validate input files and return valid/invalid lists"""
        valid_files = []
        invalid_files = []
        supported_exts = self.get_supported_formats()

        for path in file_paths:
            if not os.path.exists(path):
                invalid_files.append(f"File not found: {path}")
                continue

            ext = Path(path).suffix.lower()
            if ext not in supported_exts:
                invalid_files.append(f"Unsupported format {ext}: {path}")
                continue

            # Try to load image to verify it's valid
            try:
                img = cv2.imread(path)
                if img is None:
                    invalid_files.append(f"Could not load image: {path}")
                else:
                    valid_files.append(path)
            except Exception as e:
                invalid_files.append(f"Error loading {path}: {str(e)}")

        return valid_files, invalid_files
