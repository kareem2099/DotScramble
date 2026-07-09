"""
calibrate_eot.py — Calibration script for EOT proxy smoothing check
"""
import sys, time
import cv2
import numpy as np

sys.path.insert(0, "src")
from models.detection_engine import DetectionEngine, _ensure_model, _get_landmarker_runner

def eot_score(region_bgr, n_aug=8, jitter_px=3):
    h, w = region_bgr.shape[:2]
    hits = 0
    for _ in range(n_aug):
        dx = np.random.randint(-jitter_px, jitter_px + 1)
        dy = np.random.randint(-jitter_px, jitter_px + 1)
        M = np.float32([[1, 0, dx], [0, 1, dy]])
        j = cv2.warpAffine(region_bgr, M, (w, h), borderMode=cv2.BORDER_REFLECT)
        if DetectionEngine.detect_faces_pro(j):
            hits += 1
    return hits / n_aug

def main():
    _get_landmarker_runner(_ensure_model())  # warm-up
    if len(sys.argv) < 2:
        print("Usage: python calibrate_eot.py <path_to_face_image>")
        sys.exit(1)
        
    image = cv2.imread(sys.argv[1])
    if image is None:
        print(f"Could not read image: {sys.argv[1]}")
        sys.exit(1)
        
    faces = DetectionEngine.detect_faces_pro(image)
    if not faces:
        print("مفيش وش متكشف في الصورة الأصلية — جرب صورة تانية.")
        return

    # crop تقريبي حوالين الـ polygon points
    pts = np.array(faces[0]["points"])
    x, y, w, h = cv2.boundingRect(pts)
    pad = int(0.2 * max(w, h))
    x0, y0 = max(0, x - pad), max(0, y - pad)
    region = image[y0:y0 + h + 2*pad, x0:x0 + w + 2*pad].copy()

    print(f"Region size: {region.shape[1]}x{region.shape[0]}")

    # benchmark سرعة الكويري على الـ crop بالذات
    t0 = time.time()
    for _ in range(30):
        DetectionEngine.detect_faces_pro(region)
    print(f"Speed on crop: {30/(time.time()-t0):.1f} q/sec")

    # المهم: هل الـ score بيتحرك بسلاسة مع زيادة epsilon؟
    print("\nepsilon → eot_score (لازم ينزل تدريجيًا، مش يقفز 1.0→0.0 فجأة)")
    for eps in [0, 5, 10, 15, 20, 25, 30, 40, 50]:
        noise = np.random.normal(0, eps, region.shape).astype(np.int16)
        noisy = np.clip(region.astype(np.int16) + noise, 0, 255).astype(np.uint8)
        score = eot_score(noisy, n_aug=10)
        print(f"  ε={eps:3d} → score={score:.2f}")

if __name__ == "__main__":
    main()
