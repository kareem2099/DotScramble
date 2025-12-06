"""
Core image processing functions for privacy effects
"""
import cv2
import numpy as np
from PIL import Image, ImageFilter, ImageDraw, ImageFont, ImageEnhance
import pytesseract

class ImageProcessor:
    @staticmethod
    def gaussian_blur(image, x, y, w, h, strength):
        """Apply Gaussian blur to region"""
        if strength % 2 == 0:
            strength += 1
        region = image[y:y+h, x:x+w]
        blurred = cv2.GaussianBlur(region, (strength, strength), 0)
        return blurred
    
    @staticmethod
    def pixelate(image, x, y, w, h, pixel_size):
        """Apply pixelation effect"""
        region = image[y:y+h, x:x+w]
        region_h, region_w = region.shape[:2]
        pixel_size = max(1, pixel_size)
        
        temp_h = max(1, region_h // pixel_size)
        temp_w = max(1, region_w // pixel_size)
        
        temp = cv2.resize(region, (temp_w, temp_h), interpolation=cv2.INTER_LINEAR)
        pixelated = cv2.resize(temp, (region_w, region_h), interpolation=cv2.INTER_NEAREST)
        return pixelated
    
    @staticmethod
    def black_bar(image, x, y, w, h):
        """Apply solid black bar"""
        result = image.copy()
        cv2.rectangle(result, (x, y), (x+w, y+h), (0, 0, 0), -1)
        return result[y:y+h, x:x+w]
    
    @staticmethod
    def gradient_fade(image, x, y, w, h):
        """Apply gradient fade effect"""
        region = image[y:y+h, x:x+w].copy()
        h_reg, w_reg = region.shape[:2]
        
        # Create gradient mask
        gradient = np.linspace(0, 1, h_reg).reshape(-1, 1)
        gradient = np.tile(gradient, (1, w_reg))
        gradient = (gradient * 255).astype(np.uint8)
        
        # Apply gradient
        blurred = cv2.GaussianBlur(region, (99, 99), 0)
        for c in range(3):
            region[:, :, c] = cv2.addWeighted(
                region[:, :, c], 1, blurred[:, :, c], 0, 0
            )
        
        return region
    
    @staticmethod
    def mosaic_effect(image, x, y, w, h, tile_size=10):
        """Apply mosaic effect"""
        region = image[y:y+h, x:x+w]
        h_reg, w_reg = region.shape[:2]
        
        result = region.copy()
        for i in range(0, h_reg, tile_size):
            for j in range(0, w_reg, tile_size):
                tile = region[i:i+tile_size, j:j+tile_size]
                if tile.size > 0:
                    color = tile.mean(axis=(0, 1)).astype(np.uint8)
                    result[i:i+tile_size, j:j+tile_size] = color
        
        return result
    
    @staticmethod
    def frosted_glass(image, x, y, w, h, strength=15):
        """Apply frosted glass effect"""
        region = image[y:y+h, x:x+w]
        
        # Convert to PIL for advanced filtering
        pil_region = Image.fromarray(cv2.cvtColor(region, cv2.COLOR_BGR2RGB))
        
        # Apply multiple filters for glass effect
        blurred = pil_region.filter(ImageFilter.GaussianBlur(strength))
        enhanced = ImageEnhance.Brightness(blurred).enhance(1.1)
        final = enhanced.filter(ImageFilter.EDGE_ENHANCE)
        
        # Convert back to OpenCV format
        result = cv2.cvtColor(np.array(final), cv2.COLOR_RGB2BGR)
        return result
    
    @staticmethod
    def oil_paint(image, x, y, w, h, size=7, dynRatio=1):
        """Apply oil painting effect"""
        region = image[y:y+h, x:x+w]
        try:
            # OpenCV oil painting (if available)
            result = cv2.xphoto.oilPainting(region, size, dynRatio)
        except:
            # Fallback: bilateral filter for painting-like effect
            result = cv2.bilateralFilter(region, 9, 75, 75)
            result = cv2.bilateralFilter(result, 9, 75, 75)
        
        return result
    
    @staticmethod
    def emoji_cover(image, x, y, w, h, emoji_char='😎'):
        """Place emoji over region"""
        result = image.copy()
        
        # Convert to PIL
        pil_img = Image.fromarray(cv2.cvtColor(result, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(pil_img)
        
        # Calculate emoji size
        emoji_size = min(w, h)
        
        try:
            # Try to use a font with emoji support
            font = ImageFont.truetype("seguiemj.ttf", emoji_size)
        except:
            font = ImageFont.load_default()
        
        # Draw emoji
        text_x = x + (w - emoji_size) // 2
        text_y = y + (h - emoji_size) // 2
        draw.text((text_x, text_y), emoji_char, font=font, fill=(255, 255, 0))
        
        # Convert back
        result = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        return result[y:y+h, x:x+w]
    
    @staticmethod
    def apply_opacity(original, processed, opacity):
        """Blend processed region with original based on opacity"""
        alpha = opacity / 100.0
        return cv2.addWeighted(processed, alpha, original, 1 - alpha, 0)


class DetectionEngine:
    """Advanced detection algorithms"""
    
    @staticmethod
    def detect_faces(image):
        """Detect faces using Haar Cascade"""
        face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        )
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, 1.1, 5, minSize=(30, 30))
        return faces
    
    @staticmethod
    def detect_eyes(image):
        """Detect eyes using Haar Cascade"""
        eye_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_eye.xml'
        )
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        eyes = eye_cascade.detectMultiScale(gray, 1.1, 5, minSize=(20, 20))
        return eyes
    
    @staticmethod
    def detect_full_body(image):
        """Detect full body using Haar Cascade"""
        body_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_fullbody.xml'
        )
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        bodies = body_cascade.detectMultiScale(gray, 1.1, 3, minSize=(50, 100))
        return bodies
    
    @staticmethod
    def detect_license_plates(image):
        """Detect license plates (simplified with contours)"""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edged = cv2.Canny(blurred, 50, 150)
        
        contours, _ = cv2.findContours(edged, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        
        plates = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            aspect_ratio = w / float(h)
            
            # License plates typically have aspect ratio between 2-5
            if 2.0 <= aspect_ratio <= 5.0 and w > 80 and h > 20:
                plates.append((x, y, w, h))
        
        return np.array(plates)
    
    @staticmethod
    def detect_text(image):
        """Detect text regions using Tesseract OCR"""
        try:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            
            # Use Tesseract to detect text regions
            data = pytesseract.image_to_data(gray, output_type=pytesseract.Output.DICT)
            
            text_regions = []
            n_boxes = len(data['text'])
            
            for i in range(n_boxes):
                if int(data['conf'][i]) > 30:  # Confidence threshold
                    x, y, w, h = data['left'][i], data['top'][i], data['width'][i], data['height'][i]
                    if w > 10 and h > 10:
                        text_regions.append((x, y, w, h))
            
            return np.array(text_regions)
        except:
            # Fallback: simple edge detection
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            _, binary = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY_INV)
            contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            text_regions = []
            for contour in contours:
                x, y, w, h = cv2.boundingRect(contour)
                if 10 < w < 200 and 10 < h < 100:
                    text_regions.append((x, y, w, h))
            
            return np.array(text_regions)
