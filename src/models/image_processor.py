import cv2
import numpy as np
from PIL import Image, ImageFilter, ImageEnhance

class ImageProcessor:
    """
    Model Class: Handles all low-level image manipulations.
    Stand-alone: No dependencies on GUI or external utils.
    """
    
    @staticmethod
    def validate_region(image, x, y, w, h):
        """Helper: Ensure coordinates are within image bounds to prevent crashes."""
        if image is None or image.size == 0:
            return None
            
        img_h, img_w = image.shape[:2]
        
        # Clamping logic (Safe cropping)
        nx = max(0, min(x, img_w - 1))
        ny = max(0, min(y, img_h - 1))
        nw = min(w, img_w - nx)
        nh = min(h, img_h - ny)
        
        # Minimum size check
        if nw < 3 or nh < 3:
            return None
            
        return image[ny:ny+nh, nx:nx+nw], (nx, ny, nw, nh)

    @staticmethod
    def apply_effect_to_region(image, x, y, w, h, effect_type, **kwargs):
        """
        Master function to apply any effect to a region.
        Args:
            image: Source image
            x, y, w, h: Region coordinates
            effect_type: 'blur', 'pixelation', 'black_bar', etc.
            kwargs: Parameters like 'strength', 'pixel_size', 'opacity'
        """
        # 1. Validate Region
        validated = ImageProcessor.validate_region(image, x, y, w, h)
        if not validated: return image
        
        region, (nx, ny, nw, nh) = validated
        result_region = region.copy()

        # 2. Apply Effect Logic
        try:
            if effect_type == "blur":
                strength = kwargs.get('strength', 15)
                # Ensure odd number for GaussianBlur
                if strength % 2 == 0: strength += 1
                strength = max(3, strength)
                result_region = cv2.GaussianBlur(region, (strength, strength), 0)
                
            elif effect_type == "pixelation":
                pixel_size = max(1, kwargs.get('pixel_size', 10))
                h_reg, w_reg = region.shape[:2]
                # Downscale then Upscale
                small = cv2.resize(region, (max(1, w_reg//pixel_size), max(1, h_reg//pixel_size)), interpolation=cv2.INTER_LINEAR)
                result_region = cv2.resize(small, (w_reg, h_reg), interpolation=cv2.INTER_NEAREST)
                
            elif effect_type == "black_bar":
                result_region[:] = (0, 0, 0)
                
            elif effect_type == "gradient":
                h_reg, w_reg = region.shape[:2]
                gradient = np.linspace(0, 1, h_reg).reshape(-1, 1, 1)  # shape (H, 1, 1) for broadcasting
                # Apply blur first for smoother transition
                blurred = cv2.GaussianBlur(region, (99, 99), 0)
                result_region = (region.astype(np.float32) * (1.0 - gradient) + blurred.astype(np.float32) * gradient).astype(np.uint8)

            elif effect_type == "mosaic":
                tile_size = max(1, kwargs.get('pixel_size', 10))
                h_reg, w_reg = region.shape[:2]
                small = cv2.resize(region, (max(1, w_reg // tile_size), max(1, h_reg // tile_size)), interpolation=cv2.INTER_AREA)
                result_region = cv2.resize(small, (w_reg, h_reg), interpolation=cv2.INTER_NEAREST)

            elif effect_type == "glass":
                strength = kwargs.get('strength', 15)
                # Convert to PIL for filters
                pil_region = Image.fromarray(cv2.cvtColor(region, cv2.COLOR_BGR2RGB))
                blurred = pil_region.filter(ImageFilter.GaussianBlur(strength))
                enhanced = ImageEnhance.Brightness(blurred).enhance(1.1)
                final = enhanced.filter(ImageFilter.EDGE_ENHANCE)
                result_region = cv2.cvtColor(np.array(final), cv2.COLOR_RGB2BGR)

            elif effect_type == "oil_paint":
                try:
                    result_region = cv2.xphoto.oilPainting(region, 7, 1)
                except:
                    # Fallback if opencv-contrib not installed
                    result_region = cv2.bilateralFilter(region, 9, 75, 75)
                    result_region = cv2.bilateralFilter(result_region, 9, 75, 75)

            # 3. Apply Opacity (Blending)
            opacity = kwargs.get('opacity', 100)
            if opacity < 100:
                alpha = opacity / 100.0
                result_region = cv2.addWeighted(result_region, alpha, region, 1 - alpha, 0)

            # 4. Merge result back into original image copy
            final_image = image.copy()
            final_image[ny:ny+nh, nx:nx+nw] = result_region
            return final_image

        except Exception as e:
            print(f"Effect Error ({effect_type}): {e}")
            return image

    # ── PRO helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _make_effect_layer(region: np.ndarray, effect_type: str, **kwargs) -> np.ndarray:
        """
        Shared helper: produce a fully-processed copy of a region.
        Used by both polygon and rotated-rect methods.
        """
        result = region.copy()
        try:
            if effect_type == "blur":
                strength = kwargs.get("strength", 21)
                if strength % 2 == 0: strength += 1
                strength = max(3, strength)
                result = cv2.GaussianBlur(region, (strength, strength), 0)

            elif effect_type == "pixelation":
                pixel_size = max(1, kwargs.get("pixel_size", 10))
                h, w = region.shape[:2]
                small  = cv2.resize(region,
                                    (max(1, w // pixel_size), max(1, h // pixel_size)),
                                    interpolation=cv2.INTER_LINEAR)
                result = cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)

            elif effect_type == "black_bar":
                result[:] = (0, 0, 0)

            elif effect_type == "mosaic":
                tile = max(1, kwargs.get("pixel_size", 10))
                h, w = region.shape[:2]
                small = cv2.resize(region, (max(1, w // tile), max(1, h // tile)), interpolation=cv2.INTER_AREA)
                result = cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)
        except Exception as e:
            print(f"Effect Layer Error ({effect_type}): {e}")

        # Opacity blend
        opacity = kwargs.get("opacity", 100)
        if opacity < 100:
            alpha  = opacity / 100.0
            result = cv2.addWeighted(result, alpha, region, 1 - alpha, 0)

        return result

    @staticmethod
    def apply_effect_to_polygon(image: np.ndarray, points: list,
                                effect_type: str, **kwargs) -> np.ndarray:
        """
        PRO: Apply any effect inside an arbitrary polygon (e.g. face oval).

        Args:
            image:       Full source image (BGR numpy array).
            points:      List of (x, y) pixel coordinates forming the polygon.
            effect_type: Same tags as apply_effect_to_region.
            **kwargs:    strength, pixel_size, opacity …
        Returns:
            Modified copy of image with effect applied inside the polygon only.
        """
        if image is None or len(points) < 3:
            return image
        try:
            pts = np.array(points, dtype=np.int32)

            # Bounding-box of the polygon → work on a small crop for speed
            x, y, w, h = cv2.boundingRect(pts)
            img_h, img_w = image.shape[:2]
            x  = max(0, x);  y = max(0, y)
            w  = min(w, img_w - x);  h = min(h, img_h - y)
            if w < 3 or h < 3:
                return image

            # black_bar: skip blending entirely — fill polygon directly for crisp solid result (if fully opaque)
            if effect_type == "black_bar" and kwargs.get("opacity", 100) == 100:
                final = image.copy()
                cv2.fillPoly(final, [pts], (0, 0, 0))
                return final

            region = image[y:y+h, x:x+w].copy()
            processed = ImageProcessor._make_effect_layer(region, effect_type, **kwargs)

            # Build mask in crop coordinates
            mask_crop = np.zeros((h, w), dtype=np.uint8)
            shifted = pts - np.array([x, y])
            cv2.fillPoly(mask_crop, [shifted], 255)

            # Feather mask edges (softer blend at polygon boundary)
            feather = kwargs.get("feather", 3)
            if feather > 0:
                mask_crop = cv2.GaussianBlur(mask_crop,
                                             (feather*2+1, feather*2+1), 0)

            # Composite: blend using NumPy broadcasting (H, W, 1) mask over (H, W, 3) image
            mask_norm = mask_crop.astype(np.float32)[:, :, np.newaxis] / 255.0
            blended = (processed.astype(np.float32) * mask_norm
                       + region.astype(np.float32) * (1.0 - mask_norm)).astype(np.uint8)

            final = image.copy()
            final[y:y+h, x:x+w] = blended
            return final

        except Exception as e:
            print(f"Polygon Effect Error ({effect_type}): {e}")
            return image

    @staticmethod
    def apply_effect_rotated(image: np.ndarray, center: tuple, size: tuple,
                             angle: float, effect_type: str, **kwargs) -> np.ndarray:
        """
        PRO: Apply any effect inside a rotated rectangle (e.g. angled eye bar).

        Args:
            image:       Full source image (BGR numpy array).
            center:      (cx, cy) — centre of the rotated rectangle.
            size:        (width, height) of the rectangle.
            angle:       Rotation angle in degrees.
            effect_type: Same tags as apply_effect_to_region.
            **kwargs:    strength, pixel_size, opacity …
        Returns:
            Modified copy of image with effect applied inside the rotated rect only.
        """
        if image is None:
            return image
        try:
            # 4 corner points of the rotated rect
            rect = (center, size, angle)
            box  = cv2.boxPoints(rect).astype(np.int32)

            # black_bar: skip blending entirely — fillPoly directly for a crisp solid bar (if fully opaque)
            if effect_type == "black_bar" and kwargs.get("opacity", 100) == 100:
                final = image.copy()
                cv2.fillPoly(final, [box], (0, 0, 0))
                return final

            # Full-image mask
            mask = np.zeros(image.shape[:2], dtype=np.uint8)
            cv2.fillPoly(mask, [box], 255)

            # Bounding box of the rotated rect → crop for processing
            x, y, w, h = cv2.boundingRect(box)
            img_h, img_w = image.shape[:2]
            x = max(0, x);  y = max(0, y)
            w = min(w, img_w - x);  h = min(h, img_h - y)
            if w < 3 or h < 3:
                return image

            region    = image[y:y+h, x:x+w].copy()
            processed = ImageProcessor._make_effect_layer(region, effect_type, **kwargs)

            # Crop the mask to the same bounding box
            mask_crop = mask[y:y+h, x:x+w]

            # Optional feathering (only for non-black_bar effects)
            feather = kwargs.get("feather", 2)
            if feather > 0:
                mask_crop = cv2.GaussianBlur(mask_crop,
                                             (feather*2+1, feather*2+1), 0)

            # Composite using NumPy broadcasting (H, W, 1) mask over (H, W, 3) image
            mask_norm = mask_crop.astype(np.float32)[:, :, np.newaxis] / 255.0
            blended = (processed.astype(np.float32) * mask_norm
                       + region.astype(np.float32) * (1.0 - mask_norm)).astype(np.uint8)

            final = image.copy()
            final[y:y+h, x:x+w] = blended
            return final

        except Exception as e:
            print(f"Rotated Effect Error ({effect_type}): {e}")
            return image