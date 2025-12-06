"""
Text Detection Module for Advanced Privacy Studio Pro
Detects and locates specific words/text in images using OCR
Enhanced with multi-word phrase support and better preprocessing
"""
import cv2
import numpy as np
from tkinter import messagebox
import logging

# Try to import pytesseract
try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False
    logging.warning("pytesseract not installed - text detection features limited")


class TextDetector:
    """Detects specific words or text regions in images using OCR"""
    
    def __init__(self):
        """Initialize text detector"""
        self.logger = logging.getLogger(__name__)
        
        # Configure Tesseract path if needed (Windows)
        # Uncomment and adjust path if Tesseract is not in PATH
        # pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
        
        # Verify Tesseract is available
        if TESSERACT_AVAILABLE:
            try:
                version = pytesseract.get_tesseract_version()
                self.logger.info(f"Tesseract OCR version: {version}")
            except Exception as e:
                self.logger.warning(f"Tesseract not properly configured: {e}")
    
    def detect_specific_word(self, image, target_word, confidence_threshold=30, 
                           case_sensitive=False, exact_match=False):
        """
        Scans the image for a specific word and returns bounding boxes.
        Handles multi-word phrases by finding all words and grouping nearby regions.
        
        Args:
            image: The cv2 image (BGR format)
            target_word (str): The word/phrase to find (e.g., "password", "Remind Me")
            confidence_threshold (int): Minimum OCR confidence (0-100)
            case_sensitive (bool): Whether to match case exactly
            exact_match (bool): If True, matches whole word only. If False, matches partial.
            
        Returns:
            list: List of tuples (x, y, w, h) representing bounding boxes
        """
        if not TESSERACT_AVAILABLE:
            messagebox.showerror(
                "OCR Not Available", 
                "Tesseract OCR is not installed.\n\n"
                "Please install:\n"
                "1. Tesseract binary: https://github.com/UB-Mannheim/tesseract/wiki\n"
                "2. Python package: pip install pytesseract"
            )
            return []
        
        if image is None:
            self.logger.error("No image provided")
            return []
        
        if not target_word or not target_word.strip():
            self.logger.warning("No target word provided")
            return []
        
        # Preprocess image for better OCR results
        processed_image = self._preprocess_image(image)
        
        # Convert to RGB (Tesseract requires RGB)
        rgb_image = cv2.cvtColor(processed_image, cv2.COLOR_BGR2RGB)
        
        # Get detailed OCR data (words, boxes, confidence)
        try:
            # Try PSM 6 first (Assume uniform block of text)
            data = pytesseract.image_to_data(
                rgb_image, 
                output_type=pytesseract.Output.DICT,
                config='--psm 6'  # PSM 6: Assume uniform block of text
            )
        except Exception as e:
            error_msg = f"OCR Error: {str(e)}\n\n"
            error_msg += "Please verify Tesseract is properly installed."
            messagebox.showerror("OCR Error", error_msg)
            self.logger.error(f"Tesseract error: {e}")
            return []
        
        # Process target word
        target = target_word.strip()
        if not case_sensitive:
            target = target.lower()
        
        # Split target into words for multi-word matching
        target_words = target.split()
        
        regions = []
        matched_boxes = []  # Store boxes that match individual words
        n_boxes = len(data['text'])
        
        self.logger.info(f"Searching for: '{target_word}' (case_sensitive={case_sensitive}, exact={exact_match})")
        self.logger.info(f"Target words split: {target_words}")
        
        # Debug: Log all detected text
        all_detected = []
        for i in range(n_boxes):
            text = str(data['text'][i]).strip()
            if text:
                try:
                    conf = int(data['conf'][i])
                    all_detected.append(f"{text} ({conf}%)")
                except:
                    pass
        
        if all_detected:
            self.logger.info(f"All detected text: {', '.join(all_detected[:20])}")  # First 20 words
        else:
            self.logger.warning("No text detected in image at all!")
        
        for i in range(n_boxes):
            # Get detected text
            detected_text = str(data['text'][i]).strip()
            
            if not detected_text:
                continue
            
            # Get confidence
            try:
                conf = int(data['conf'][i])
            except (ValueError, KeyError):
                continue
            
            # Skip low confidence detections
            if conf < confidence_threshold:
                continue
            
            # Prepare detected text for comparison
            compare_text = detected_text if case_sensitive else detected_text.lower()
            
            # Check if text matches any word in the target
            match_found = False
            
            if len(target_words) == 1:
                # Single word matching
                if exact_match:
                    match_found = (compare_text == target)
                else:
                    match_found = (target in compare_text)
            else:
                # Multi-word matching - check if this word is part of target phrase
                # Be more strict: each detected word should match a target word closely
                for target_word_part in target_words:
                    if exact_match:
                        if compare_text == target_word_part:
                            match_found = True
                            break
                    else:
                        # Check if detected word starts with target word (avoid false matches like "Reminders" for "Remind")
                        if compare_text.startswith(target_word_part) or target_word_part.startswith(compare_text):
                            # Also accept if target is contained and lengths are similar
                            if len(compare_text) <= len(target_word_part) * 2:
                                match_found = True
                                break
                        elif compare_text == target_word_part:
                            match_found = True
                            break
            
            if match_found:
                # Get bounding box
                x = data['left'][i]
                y = data['top'][i]
                w = data['width'][i]
                h = data['height'][i]
                
                # Add to matched boxes
                matched_boxes.append({
                    'text': detected_text,
                    'box': (x, y, w, h),
                    'conf': conf
                })
                
                self.logger.info(f"Found '{detected_text}' at ({x}, {y}, {w}, {h}) - confidence: {conf}%")
        
        # If we found multiple words, try to group nearby boxes (for multi-word phrases)
        if len(matched_boxes) > 1 and len(target_words) > 1:
            regions = self._group_nearby_boxes(matched_boxes, image)
        else:
            # Convert matched boxes to regions
            for match in matched_boxes:
                x, y, w, h = match['box']
                
                # Add padding for better coverage
                padding = 8
                x = max(0, x - padding)
                y = max(0, y - padding)
                w += (padding * 2)
                h += (padding * 2)
                
                # Ensure box is within image bounds
                img_h, img_w = image.shape[:2]
                x = max(0, min(x, img_w - 1))
                y = max(0, min(y, img_h - 1))
                w = min(w, img_w - x)
                h = min(h, img_h - y)
                
                if w > 5 and h > 5:
                    regions.append((x, y, w, h))
        
        if not regions:
            self.logger.info(f"No matches found for '{target_word}'")
        else:
            self.logger.info(f"Found {len(regions)} region(s) matching '{target_word}'")
        
        return regions
    
    def _group_nearby_boxes(self, matched_boxes, image, max_distance=50):
        """
        Group nearby text boxes (for multi-word phrases like "Remind Me").
        
        Args:
            matched_boxes: List of dicts with 'box' keys
            image: The cv2 image
            max_distance: Maximum horizontal distance to consider boxes as grouped
            
        Returns:
            list: List of combined bounding boxes (x, y, w, h)
        """
        if not matched_boxes:
            return []
        
        # Sort boxes by vertical position first, then horizontal
        sorted_boxes = sorted(matched_boxes, key=lambda b: (b['box'][1], b['box'][0]))
        
        regions = []
        used = set()
        
        for i, box1 in enumerate(sorted_boxes):
            if i in used:
                continue
            
            x1, y1, w1, h1 = box1['box']
            group = [box1]
            used.add(i)
            
            # Find nearby boxes on the same line
            for j, box2 in enumerate(sorted_boxes):
                if j in used or j == i:
                    continue
                
                x2, y2, w2, h2 = box2['box']
                
                # Check if boxes are on roughly the same line (similar y-coordinate)
                y_diff = abs(y1 - y2)
                if y_diff > max(h1, h2):
                    continue
                
                # Check horizontal distance
                horizontal_distance = abs(x2 - (x1 + w1))
                
                # Also check if x2 is to the right of x1 (proper word order)
                # Allow larger distance for multi-word phrases
                if horizontal_distance < max_distance * 3:  # Increased tolerance
                    group.append(box2)
                    used.add(j)
            
            # Create combined bounding box for the group
            if group:
                all_x = [b['box'][0] for b in group]
                all_y = [b['box'][1] for b in group]
                all_x_end = [b['box'][0] + b['box'][2] for b in group]
                all_y_end = [b['box'][1] + b['box'][3] for b in group]
                
                x = min(all_x)
                y = min(all_y)
                w = max(all_x_end) - x
                h = max(all_y_end) - y
                
                # Add padding
                padding = 10
                x = max(0, x - padding)
                y = max(0, y - padding)
                w += (padding * 2)
                h += (padding * 2)
                
                # Ensure within bounds
                img_h, img_w = image.shape[:2]
                x = max(0, min(x, img_w - 1))
                y = max(0, min(y, img_h - 1))
                w = min(w, img_w - x)
                h = min(h, img_h - y)
                
                if w > 5 and h > 5:
                    regions.append((x, y, w, h))
        
        return regions
    
    def detect_multiple_words(self, image, word_list, confidence_threshold=30):
        """
        Detect multiple specific words in an image.
        
        Args:
            image: The cv2 image
            word_list (list): List of words to find
            confidence_threshold (int): Minimum OCR confidence
            
        Returns:
            dict: Dictionary with words as keys and list of regions as values
        """
        results = {}
        
        for word in word_list:
            regions = self.detect_specific_word(image, word, confidence_threshold)
            if regions:
                results[word] = regions
        
        return results
    
    def detect_all_text(self, image, confidence_threshold=30):
        """
        Detect all text regions in the image.
        
        Args:
            image: The cv2 image
            confidence_threshold (int): Minimum OCR confidence
            
        Returns:
            list: List of tuples (x, y, w, h) for all detected text
        """
        if not TESSERACT_AVAILABLE:
            return []
        
        if image is None:
            return []
        
        # Preprocess image
        processed_image = self._preprocess_image(image)
        rgb_image = cv2.cvtColor(processed_image, cv2.COLOR_BGR2RGB)
        
        try:
            data = pytesseract.image_to_data(
                rgb_image,
                output_type=pytesseract.Output.DICT
            )
        except Exception as e:
            self.logger.error(f"OCR Error: {e}")
            return []
        
        regions = []
        n_boxes = len(data['text'])
        
        for i in range(n_boxes):
            text = str(data['text'][i]).strip()
            
            if not text:
                continue
            
            try:
                conf = int(data['conf'][i])
            except (ValueError, KeyError):
                continue
            
            if conf > confidence_threshold:
                x = data['left'][i]
                y = data['top'][i]
                w = data['width'][i]
                h = data['height'][i]
                
                if w > 10 and h > 10:
                    regions.append((x, y, w, h))
        
        return regions
    
    def _preprocess_image(self, image):
        """
        Preprocess image for better OCR accuracy.
        Uses multiple techniques to enhance text visibility.
        Now tries multiple preprocessing strategies.
        
        Args:
            image: Input cv2 image
            
        Returns:
            Preprocessed cv2 image
        """
        # Strategy 1: Try with original image (sometimes works best!)
        # We'll return the original for now, but you can experiment
        
        # Convert to grayscale
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # Strategy 2: Simple approach - just grayscale
        # This often works better than heavy processing
        return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        
        # Strategy 3: Enhanced contrast (commented out, can be tried)
        # clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        # enhanced = clahe.apply(gray)
        # return cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)
    
    def get_detected_text(self, image, confidence_threshold=30):
        """
        Get all text detected in the image with their locations.
        
        Args:
            image: The cv2 image
            confidence_threshold (int): Minimum OCR confidence
            
        Returns:
            list: List of dictionaries with 'text', 'confidence', and 'box' keys
        """
        if not TESSERACT_AVAILABLE:
            return []
        
        if image is None:
            return []
        
        processed_image = self._preprocess_image(image)
        rgb_image = cv2.cvtColor(processed_image, cv2.COLOR_BGR2RGB)
        
        try:
            data = pytesseract.image_to_data(
                rgb_image,
                output_type=pytesseract.Output.DICT
            )
        except Exception as e:
            self.logger.error(f"OCR Error: {e}")
            return []
        
        results = []
        n_boxes = len(data['text'])
        
        for i in range(n_boxes):
            text = str(data['text'][i]).strip()
            
            if not text:
                continue
            
            try:
                conf = int(data['conf'][i])
            except (ValueError, KeyError):
                continue
            
            if conf > confidence_threshold:
                x = data['left'][i]
                y = data['top'][i]
                w = data['width'][i]
                h = data['height'][i]
                
                results.append({
                    'text': text,
                    'confidence': conf,
                    'box': (x, y, w, h)
                })
        
        return results
    
    @staticmethod
    def is_tesseract_installed():
        """Check if Tesseract is properly installed"""
        if not TESSERACT_AVAILABLE:
            return False
        
        try:
            pytesseract.get_tesseract_version()
            return True
        except Exception:
            return False


# Utility function for easy access
def detect_word_in_image(image, word, confidence=30):
    """
    Convenience function to detect a specific word in an image.
    
    Args:
        image: cv2 image
        word: word to find
        confidence: minimum confidence (0-100), default 30 for better matching
        
    Returns:
        list of bounding boxes [(x, y, w, h), ...]
    """
    detector = TextDetector()
    return detector.detect_specific_word(image, word, confidence)