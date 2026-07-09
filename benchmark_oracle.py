"""
benchmark_oracle.py — Benchmark script for MediaPipe detection oracle
"""
import sys, time
import cv2

sys.path.insert(0, "src")
from models.detection_engine import _ensure_model, _get_landmarker_runner, is_model_downloaded


def main():
    if len(sys.argv) < 2:
        print("Usage: python benchmark_oracle.py <path_to_face_image>")
        sys.exit(1)

    image = cv2.imread(sys.argv[1])
    if image is None:
        print(f"Could not read image: {sys.argv[1]}")
        sys.exit(1)

    if not is_model_downloaded():
        print("Model مش متحمل — افتح التطبيق وفعّل PRO الأول عشان يتحمل.")
        sys.exit(1)

    landmarker = _get_landmarker_runner(_ensure_model())
    if landmarker is None:
        print("Failed to init FaceLandmarker.")
        sys.exit(1)

    import mediapipe as mp_core

    def detect_once(img_bgr):
        rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        mp_image = mp_core.Image(image_format=mp_core.ImageFormat.SRGB, data=rgb)
        return landmarker.detect(mp_image)

    # 1) هل فيه أي حقل score مخفي ماشفناه؟
    result = detect_once(image)
    print("face_landmarks found:", len(result.face_landmarks))
    print("Result attrs:", [a for a in dir(result) if not a.startswith('_')])
    if result.face_landmarks:
        sample_lm = result.face_landmarks[0][0]
        print("Landmark attrs:", [a for a in dir(sample_lm) if not a.startswith('_')])

    # 2) سرعة الكويري — الرقم اللي هيحدد كل حاجة بعد كده
    N = 30
    t0 = time.time()
    for _ in range(N):
        detect_once(image)
    elapsed = time.time() - t0
    print(f"\n{N} calls in {elapsed:.2f}s → {elapsed/N*1000:.1f} ms/query "
          f"(~{N/elapsed:.1f} q/sec)")

    # 3) هل الـ legacy continuous-score API لسه شغالة في نسختك؟
    try:
        import mediapipe as mp
        fd = mp.solutions.face_detection.FaceDetection(min_detection_confidence=0.3)
        legacy = fd.process(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
        if legacy.detections:
            print(f"\n✅ legacy API works — score: {legacy.detections[0].score[0]:.4f}")
        else:
            print("\n⚠️ legacy API loaded, no face detected on this image.")
    except Exception as e:
        print(f"\n❌ legacy API not available: {e}")


if __name__ == "__main__":
    main()
