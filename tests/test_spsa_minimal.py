"""
test_spsa_minimal.py — Masked Block-Tiled SPSA attack test with n_aug=50 verification
"""
import sys, time
import cv2
import numpy as np

sys.path.insert(0, "src")
from models.detection_engine import DetectionEngine, _ensure_model, _get_landmarker_runner

def eot_score(region_bgr, delta=None, n_aug=6, jitter_px=3):
    if delta is not None:
        img_input = np.clip(region_bgr.astype(np.float32) + delta, 0, 255).astype(np.uint8)
    else:
        img_input = region_bgr
        
    h, w = img_input.shape[:2]
    hits = 0
    for _ in range(n_aug):
        dx = np.random.randint(-jitter_px, jitter_px + 1)
        dy = np.random.randint(-jitter_px, jitter_px + 1)
        M = np.float32([[1, 0, dx], [0, 1, dy]])
        j = cv2.warpAffine(img_input, M, (w, h), borderMode=cv2.BORDER_REFLECT)
        if DetectionEngine.detect_faces_pro(j):
            hits += 1
    return hits / n_aug

def make_low_dim_delta(region_shape, block_size=16):
    h, w, ch = region_shape
    bh = max(1, h // block_size)
    bw = max(1, w // block_size)
    return (bh, bw, ch)

def upsample_delta(delta_small, target_shape):
    h, w, ch = target_shape
    out = np.zeros(target_shape, dtype=np.float32)
    for c in range(ch):
        out[:, :, c] = cv2.resize(
            delta_small[:, :, c], (w, h), interpolation=cv2.INTER_NEAREST
        )
    return out

def check_perceptibility(original_region, delta, mask_3d=None):
    if mask_3d is not None:
        effective_delta = delta * mask_3d
    else:
        effective_delta = delta
        
    perturbed = np.clip(original_region.astype(np.float32) + effective_delta, 0, 255).astype(np.uint8)
    psnr = cv2.PSNR(original_region, perturbed)
    max_diff = np.max(np.abs(effective_delta))
    print(f"\n--- Perceptibility Analysis ---")
    print(f"Max Perturbation (Max |delta| inside mask): {max_diff:.1f}")
    print(f"PSNR (Full Region): {psnr:.2f} dB  (>40 dB = practically invisible, <30 dB = noticeable artifacts)")
    
    cv2.imwrite("/tmp/perturbed_preview.png", perturbed)
    diff_vis = cv2.convertScaleAbs(cv2.absdiff(original_region, perturbed), alpha=5)
    cv2.imwrite("/tmp/diff_amplified.png", diff_vis)
    print(f"Saved previews to /tmp/perturbed_preview.png and /tmp/diff_amplified.png")
    return psnr

def spsa_attack_masked(region, mask_3d, max_eps=255, iters=40, k=8, n_aug=8,
                        alpha_start=10.0, c_start=55.0, c_floor=35.0,
                        c_decay=0.97, block_size=32):
    h, w, ch = region.shape
    small_shape = make_low_dim_delta(region.shape, block_size)
    delta_small = np.zeros(small_shape, dtype=np.float32)
    c_i = c_start

    initial_score = eot_score(region, np.zeros(region.shape, dtype=np.float32), n_aug=12)
    print(f"Initial score: {initial_score:.2f}  | low-dim shape: {small_shape} "
          f"({np.prod(small_shape)} dims vs {h*w*ch} full-pixel dims)")
    print(f"Face Oval Mask Active: {np.sum(mask_3d > 0)/mask_3d.size*100:.1f}% of crop area")

    for i in range(iters):
        a_i = alpha_start / ((i + 1) ** 0.2)
        ghat_small = np.zeros_like(delta_small)

        for _ in range(k):
            v_small = np.random.choice([-1.0, 1.0], size=delta_small.shape).astype(np.float32)
            
            # Apply upsampled delta restricted to face mask
            full_pos = upsample_delta(delta_small + c_i * v_small, region.shape) * mask_3d
            full_neg = upsample_delta(delta_small - c_i * v_small, region.shape) * mask_3d
            
            score_pos = eot_score(region, full_pos, n_aug=n_aug)
            score_neg = eot_score(region, full_neg, n_aug=n_aug)
            ghat_small += ((score_pos - score_neg) / (2.0 * c_i)) * v_small
        ghat_small /= k

        if np.any(ghat_small != 0):
            delta_small = delta_small - a_i * np.sign(ghat_small)
            delta_small = np.clip(delta_small, -max_eps, max_eps)

        c_i = max(c_floor, c_i * c_decay)

        full_delta = upsample_delta(delta_small, region.shape) * mask_3d
        cur_score = eot_score(region, full_delta, n_aug=12)
        print(f"Iter {i+1:2d}/{iters} | score={cur_score:.2f} | c_i={c_i:.1f} | "
              f"max|delta_small|={np.max(np.abs(delta_small)):.1f}")

        if cur_score == 0.0:
            print(f"\n✅ Success! Broke detection completely at iter {i+1}!")
            
            # Robust Verification with n_aug=50
            verify_score = eot_score(region, full_delta, n_aug=50, jitter_px=3)
            print(f"🔍 Robust verification (n_aug=50): {verify_score:.3f}")
            
            check_perceptibility(region, full_delta, mask_3d)
            return full_delta, verify_score

    final_delta = upsample_delta(delta_small, region.shape) * mask_3d
    final = eot_score(region, final_delta, n_aug=20)
    print(f"\nFinal score after {iters} iters (n_aug=20): {final:.2f}")
    
    verify_score = eot_score(region, final_delta, n_aug=50, jitter_px=3)
    print(f"🔍 Robust verification (n_aug=50): {verify_score:.3f}")
    
    check_perceptibility(region, final_delta, mask_3d)
    return final_delta, verify_score

def main():
    _get_landmarker_runner(_ensure_model())
    if len(sys.argv) < 2:
        print("Usage: python test_spsa_minimal.py <path_to_face_image> [block_size]")
        sys.exit(1)
        
    image = cv2.imread(sys.argv[1])
    if image is None:
        print(f"Could not read image: {sys.argv[1]}")
        sys.exit(1)
        
    faces = DetectionEngine.detect_faces_pro(image)
    if not faces:
        print("No face detected in original image.")
        return

    pts = np.array(faces[0]["points"])
    x, y, w, h = cv2.boundingRect(pts)
    pad = int(0.2 * max(w, h))
    x0, y0 = max(0, x - pad), max(0, y - pad)
    region = image[y0:y0 + h + 2*pad, x0:x0 + w + 2*pad].copy()

    # Build 3D Face Oval Mask in region coordinates
    local_pts = [(px - x0, py - y0) for (px, py) in faces[0]["points"]]
    mask_2d = np.zeros(region.shape[:2], dtype=np.float32)
    cv2.fillPoly(mask_2d, [np.array(local_pts, dtype=np.int32)], 1.0)
    mask_3d = mask_2d[:, :, np.newaxis]

    block_size = int(sys.argv[2]) if len(sys.argv) > 2 else 32
    print(f"--- Running Masked Block-Tiled SPSA (max_eps=255, block_size={block_size}) ---")
    spsa_attack_masked(region, mask_3d, max_eps=255, iters=40, k=8, n_aug=8, block_size=block_size)

if __name__ == "__main__":
    main()
