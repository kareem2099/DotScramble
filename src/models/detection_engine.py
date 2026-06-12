"""
DotScramble — Detection Engine
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Two-tier detection system:
  FREE  → Haar Cascades (fast, offline, rectangles)
  PRO   → MediaPipe FaceLandmarker via Tasks API (AI, angled polygons, oval masking)

The Tasks API model file (~8MB) is downloaded once on first PRO use and cached at:
  ~/.local/share/DotScramble/models/face_landmarker.task

PRO functions return a list of dicts instead of plain (x,y,w,h) tuples:
  {"type": "polygon",      "points": [...]}      ← face oval
  {"type": "rotated_rect", "center": ...,
                           "size": ...,
                           "angle": ...}         ← angled eye bar
"""
from __future__ import annotations
import math
import os
import urllib.request
import cv2
import numpy as np
import pytesseract

# Suppress MediaPipe's verbose OpenGL/TFLite initialization logs
os.environ.setdefault("GLOG_minloglevel", "3")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")


# ── Model management & Cross-Platform Paths ───────────────────────────────────
import sys
from pathlib import Path

def _get_app_data_dir() -> Path:
    home = Path.home()
    if sys.platform.startswith("win"):
        # Windows: AppData/Local
        return home / "AppData" / "Local" / "DotScramble"
    elif sys.platform.startswith("darwin"):
        # macOS: Library/Application Support
        return home / "Library" / "Application Support" / "DotScramble"
    else:
        # Linux / Other OS Standard
        return home / ".local" / "share" / "DotScramble"


MODEL_DIR  = _get_app_data_dir() / "models"
MODEL_PATH = str(MODEL_DIR / "face_landmarker.task")
MODEL_URL  = ("https://storage.googleapis.com/mediapipe-models/"
              "face_landmarker/face_landmarker/float16/latest/face_landmarker.task")


def _ensure_model() -> str | None:
    """Return model path if file exists and is complete, otherwise None (no automatic blocking download)."""
    if os.path.isfile(MODEL_PATH) and os.path.getsize(MODEL_PATH) > 1024 * 1024:
        return MODEL_PATH
    return None


def is_model_downloaded() -> bool:
    """Check if the FaceLandmarker model is downloaded and exists on disk and is complete."""
    return os.path.isfile(MODEL_PATH) and os.path.getsize(MODEL_PATH) > 1024 * 1024


def download_model_file(progress_callback=None) -> bool:
    """Download the FaceLandmarker model in chunks to a temporary file, then rename it atomically."""
    temp_path = MODEL_PATH + ".tmp"
    try:
        import requests
        os.makedirs(str(MODEL_DIR), exist_ok=True)
        response = requests.get(MODEL_URL, stream=True, timeout=15)
        response.raise_for_status()
        total = int(response.headers.get('content-length', 0))
        dl = 0
        with open(temp_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=4096):
                if not chunk:
                    continue
                f.write(chunk)
                dl += len(chunk)
                if total and progress_callback:
                    progress_callback((dl / total) * 100)
        # Atomically replace to avoid partial/corrupt files on disk
        os.replace(temp_path, MODEL_PATH)
        return True
    except Exception as e:
        print(f"[DotScramble PRO] Model download failed: {e}")
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass
        return False


# ── MediaPipe lazy loader & Instance Cache ────────────────────────────────────
def _get_mediapipe():
    """Lazily import mediapipe. Returns the module or None if not installed."""
    try:
        import mediapipe as mp
        return mp
    except ImportError:
        return None


_landmarker_instance = None


def _get_landmarker_runner(model_path: str):
    """Keep the landmarker instance in memory to avoid rebuilding graph on each call."""
    global _landmarker_instance
    if _landmarker_instance is None:
        try:
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision as mp_vision

            base_opts = mp_python.BaseOptions(model_asset_path=model_path)
            opts = mp_vision.FaceLandmarkerOptions(
                base_options=base_opts,
                running_mode=mp_vision.RunningMode.IMAGE,
                num_faces=10,
                min_face_detection_confidence=0.5,
            )
            _landmarker_instance = mp_vision.FaceLandmarker.create_from_options(opts)
        except Exception as e:
            print(f"[DotScramble PRO] Failed to initialize Landmarker Graph: {e}")
            return None
    return _landmarker_instance


# ── Landmark index sets (FaceMesh 468-point model) ───────────────────────────
# We only use the subset we need — no need to process all 468 points.

# 36 points around the face oval boundary
FACE_OVAL_IDX = [
    10, 338, 297, 332, 284, 251, 389, 356, 454, 323,
    361, 288, 397, 365, 379, 378, 400, 377, 152, 148,
    176, 149, 150, 136, 172, 58,  132, 93,  234, 127,
    162, 21,  54,  103, 67,  109,
]

# Eye corner landmarks (inner, outer) — used for angle calculation
RIGHT_EYE_CORNERS = [33, 133]   # [inner, outer]
LEFT_EYE_CORNERS  = [362, 263]  # [inner, outer]

# Extra points spanning the full eye width/height for the eye polygon
RIGHT_EYE_CONTOUR = [33, 7, 163, 144, 145, 153, 154, 155, 133,
                      173, 157, 158, 159, 160, 161, 246]
LEFT_EYE_CONTOUR  = [362, 382, 381, 380, 374, 373, 390, 249, 263,
                      466, 388, 387, 386, 385, 384, 398]


# ── Helper ───────────────────────────────────────────────────────────────────

def _landmark_to_px(lm, img_w: int, img_h: int) -> tuple[int, int]:
    """Convert a normalised MediaPipe landmark to pixel coordinates."""
    return int(lm.x * img_w), int(lm.y * img_h)


# ── Haar Cascade lazy loader & cache ──────────────────────────────────────────
_cascade_cache: dict[str, cv2.CascadeClassifier] = {}


def _get_cascade(filename: str) -> cv2.CascadeClassifier | None:
    """Lazily load and cache Haar Cascade Classifiers to avoid disk I/O bottlenecks."""
    if filename not in _cascade_cache:
        try:
            path = cv2.data.haarcascades + filename
            cascade = cv2.CascadeClassifier(path)
            if not cascade.empty():
                _cascade_cache[filename] = cascade
            else:
                return None
        except Exception:
            return None
    return _cascade_cache.get(filename)


def _eye_rotated_rect(landmarks, eye_corner_idx: list[int],
                      eye_contour_idx: list[int],
                      img_w: int, img_h: int,
                      bar_height_factor: float = 1.6) -> dict:
    """
    Compute a rotated rectangle that covers one eye perfectly,
    tilted at the exact angle of the eye in the image.
    Returns a dict suitable for `apply_effect_rotated()`.
    """
    inner = landmarks[eye_corner_idx[0]]
    outer = landmarks[eye_corner_idx[1]]
    ix, iy = _landmark_to_px(inner, img_w, img_h)
    ox, oy = _landmark_to_px(outer, img_w, img_h)

    # Eye tilt angle (degrees)
    angle = math.degrees(math.atan2(oy - iy, ox - ix))

    # Eye width from corner to corner
    eye_w = math.hypot(ox - ix, oy - iy)

    # Eye height from the full contour bounding box
    contour_pts = [_landmark_to_px(landmarks[i], img_w, img_h)
                   for i in eye_contour_idx]
    ys = [p[1] for p in contour_pts]
    eye_h = max(ys) - min(ys)

    # Centre of the rotated rect = midpoint of the two corners
    cx = (ix + ox) // 2
    cy = (iy + oy) // 2

    return {
        "type": "rotated_rect",
        "center": (cx, cy),
        "size":   (int(eye_w * 1.15), max(int(eye_h * bar_height_factor), 14)),
        "angle":  angle,
    }


# ════════════════════════════════════════════════════════════════════════════ #
#                              DETECTION ENGINE                               #
# ════════════════════════════════════════════════════════════════════════════ #

class DetectionEngine:
    """
    Two-tier detection:
      • FREE  methods return  List[ (x, y, w, h) ]
      • PRO   methods return  List[ dict ]          (polygon / rotated_rect)
    """

    # ── FREE tier — Haar Cascades ─────────────────────────────────────────────

    @staticmethod
    def detect_faces(image) -> list:
        """FREE: Detect frontal faces using Haar Cascade → rectangles."""
        if image is None:
            return []
        try:
            cascade = _get_cascade("haarcascade_frontalface_default.xml")
            if cascade is None:
                return []
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            return cascade.detectMultiScale(gray, 1.1, 5, minSize=(30, 30))
        except Exception:
            return []

    @staticmethod
    def detect_eyes(image) -> list:
        """FREE: Detect eyes using Haar Cascade → rectangles."""
        if image is None:
            return []
        try:
            face_cascade = _get_cascade("haarcascade_frontalface_default.xml")
            eye_cascade  = _get_cascade("haarcascade_eye.xml")
            if face_cascade is None or eye_cascade is None:
                return []
            gray   = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            faces  = face_cascade.detectMultiScale(gray, 1.1, 5, minSize=(30, 30))
            eyes   = []
            if len(faces) == 0:
                # fallback: search whole image (more false positives)
                return eye_cascade.detectMultiScale(gray, 1.1, 5, minSize=(20, 20))
            # Search inside face ROI top-half only → far fewer false positives
            for (fx, fy, fw, fh) in faces:
                roi = gray[fy: fy + fh // 2, fx: fx + fw]
                for (ex, ey, ew, eh) in eye_cascade.detectMultiScale(
                    roi, 1.1, 5, minSize=(15, 15)
                ):
                    eyes.append((fx + ex, fy + ey, ew, eh))
            return eyes
        except Exception:
            return []

    @staticmethod
    def detect_full_body(image) -> list:
        """FREE: Detect full body → rectangles."""
        if image is None:
            return []
        try:
            cascade = _get_cascade("haarcascade_fullbody.xml")
            if cascade is None:
                return []
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            return cascade.detectMultiScale(gray, 1.1, 3, minSize=(50, 100))
        except Exception:
            return []

    @staticmethod
    def detect_license_plates(image) -> list:
        """FREE: Detect license plates using contour aspect ratio → rectangles."""
        if image is None:
            return []
        try:
            gray    = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            edged   = cv2.Canny(blurred, 50, 150)
            contours, _ = cv2.findContours(edged, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
            plates = []
            for c in contours:
                x, y, w, h = cv2.boundingRect(c)
                ar = w / float(h)
                if 2.0 <= ar <= 5.0 and w > 80 and h > 20:
                    plates.append((x, y, w, h))
            return np.array(plates)
        except Exception:
            return []

    @staticmethod
    def detect_text(image) -> list:
        """FREE: Detect text areas using Tesseract OCR → rectangles."""
        if image is None:
            return []
        try:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            data = pytesseract.image_to_data(gray, output_type=pytesseract.Output.DICT)
            regions = []
            for i in range(len(data["text"])):
                if int(data["conf"][i]) > 30:
                    x, y, w, h = (data["left"][i], data["top"][i],
                                  data["width"][i], data["height"][i])
                    if w > 10 and h > 10:
                        regions.append((x, y, w, h))
            return np.array(regions)
        except Exception as e:
            print(f"OCR Warning: {e}")
            return []

    # ── PRO tier — MediaPipe AI ───────────────────────────────────────────────

    @staticmethod
    def detect_faces_pro(image) -> list[dict]:
        """
        PRO: Detect face ovals using MediaPipe FaceLandmarker (Tasks API).
        Returns list of {"type": "polygon", "points": [(x,y), ...]}
        """
        mp = _get_mediapipe()
        if mp is None or image is None:
            return []

        model_path = _ensure_model()
        landmarker = _get_landmarker_runner(model_path) if model_path else None
        if landmarker is None:
            return []

        img_h, img_w = image.shape[:2]
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        results_list = []

        try:
            import mediapipe as mp_core
            mp_image = mp_core.Image(
                image_format=mp_core.ImageFormat.SRGB, data=rgb
            )
            result = landmarker.detect(mp_image)

            if not result.face_landmarks:
                return []

            for face_lm in result.face_landmarks:
                oval_pts = [
                    (int(face_lm[i].x * img_w), int(face_lm[i].y * img_h))
                    for i in FACE_OVAL_IDX
                ]
                results_list.append({"type": "polygon", "points": oval_pts})

        except Exception as e:
            print(f"[DotScramble PRO] FaceLandmarker error: {e}")
            return []

        return results_list

    @staticmethod
    def detect_eyes_pro(image) -> list[dict]:
        """
        PRO: Detect a single combined angled eye bar per face.
        Returns one rotated_rect per face that spans BOTH eyes together,
        tilted at the angle of the eye line — exactly like a news censor bar.
        Returns list of:
          {"type": "rotated_rect", "center": (cx,cy), "size": (w,h), "angle": deg}
        """
        mp = _get_mediapipe()
        if mp is None or image is None:
            return []

        model_path = _ensure_model()
        landmarker = _get_landmarker_runner(model_path) if model_path else None
        if landmarker is None:
            return []

        img_h, img_w = image.shape[:2]
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        results_list = []

        try:
            import mediapipe as mp_core
            mp_image = mp_core.Image(
                image_format=mp_core.ImageFormat.SRGB, data=rgb
            )
            result = landmarker.detect(mp_image)

            if not result.face_landmarks:
                return []

            for face_lm in result.face_landmarks:
                # ── Gather key points in pixels ──────────────────────────────
                def px(idx):
                    return (int(face_lm[idx].x * img_w),
                            int(face_lm[idx].y * img_h))

                # All 4 eye corner landmarks
                # 33 = right-eye temporal (outer), 133 = right-eye nasal (inner)
                # 362 = left-eye nasal (inner), 263 = left-eye temporal (outer)
                all_corners = [px(33), px(133), px(362), px(263)]
                xs = [p[0] for p in all_corners]
                ys = [p[1] for p in all_corners]

                # Full bounding box of both eyes
                min_x, max_x = min(xs), max(xs)
                min_y, max_y = min(ys), max(ys)

                # ── Angle from line joining the two OUTER temple corners ─────
                p_right_outer = px(33)   # right eye temple (viewer's left)
                p_left_outer  = px(263)  # left  eye temple (viewer's right)
                dx = p_left_outer[0] - p_right_outer[0]
                dy = p_left_outer[1] - p_right_outer[1]
                angle = math.degrees(math.atan2(dy, dx))

                # ── Bar dimensions ────────────────────────────────────────────
                bar_w = int((max_x - min_x) * 1.15)   # full span + 15% padding
                # Height: from contour points of both eyes
                all_contour = RIGHT_EYE_CONTOUR + LEFT_EYE_CONTOUR
                contour_pts = [px(i) for i in all_contour]
                cy_list = [p[1] for p in contour_pts]
                eye_h   = max(cy_list) - min(cy_list)
                bar_h   = max(int(eye_h * 2.2), 14)

                # ── Centre: midpoint of the full horizontal span ──────────────
                cx = (min_x + max_x) // 2
                cy = (min_y + max_y) // 2

                results_list.append({
                    "type": "rotated_rect",
                    "center": (cx, cy),
                    "size":   (bar_w, bar_h),
                    "angle":  angle,
                })

        except Exception as e:
            print(f"[DotScramble PRO] Eye detection error: {e}")
            return []

        return results_list