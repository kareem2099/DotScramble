"""
DotScramble — Adversarial Perturbation Engine
══════════════════════════════════════════════════════════════════════════════
Implements a black-box adversarial perturbation engine that forces AI face
detectors (specifically MediaPipe FaceLandmarker) to fail detection.

Architecture: Block-Tiled Sign-SPSA with EOT Proxy Score + Face Oval Masking

Key Design Decisions (empirically validated):
  1. EOT Score   — converts binary oracle to continuous [0,1] via n_aug
                   jittered queries (jitter_px translation variance).
  2. Block Tiling — reduces search space from ~966K dims to ~864 dims
                   (block_size=32), enabling SPSA gradient estimation.
  3. Face Masking — restricts perturbation to face oval polygon only.
                   Empirically measured +3.53 dB PSNR improvement over
                   full-region attack (18.95 dB → 22.48 dB, same image,
                   same hyperparameters, iters=30, max_eps=110).
  4. Hybrid Mode  — compute the adversarial delta AGAINST the already-effected
                   (blurred/pixelated) image, then add the delta onto that same
                   image. This eliminates transferability gap: the oracle sees
                   exactly the image that will be saved. Empirically verified:
                   score=0.000 (n_aug=30) after attacking blurred image directly.
                   See apply_adversarial_hybrid in image_processor.py for the
                   canonical implementation.

Empirical Benchmarks (on Intel UHD 620, single face portrait, iters=30-40):
  • Oracle speed: ~49 q/sec on face crop
  • EOT score drops to 0 at ε ≈ 90-108 on clean image (Gaussian noise needs ε ≈ 70-100)
  • PSNR at success — full-region, clean image:  ~18-20 dB (visually noticeable)
  • PSNR at success — masked oval, clean image:  ~22.5 dB (+3.5 dB vs full-region)
  • PSNR at success — hybrid (delta on blurred):  ~22.75 dB, max_delta≈79 (better!)
  • Robust verification (n_aug=50): consistently 0.000 at success

Intended Usage:
  • NOT as a standalone invisible effect on clean images.
  • AS an "AI-evasion booster" applied on top of blur/pixelation effects.
  • This file is self-contained and can be imported without the GUI/PySide6.
"""
from __future__ import annotations

import threading
import numpy as np
import cv2

# ── Thread safety: the FaceLandmarker singleton is NOT thread-safe ─────────────
_landmarker_lock = threading.Lock()


# ═══════════════════════════════════════════════════════════════════════════════
# Section 1: Oracle — EOT Proxy Score
# ═══════════════════════════════════════════════════════════════════════════════

def eot_face_score(
    image_bgr: np.ndarray,
    delta: np.ndarray | None = None,
    n_aug: int = 8,
    jitter_px: int = 3,
) -> float:
    """
    Continuous proxy score in [0, 1]: fraction of jitter-augmented views
    where the FaceLandmarker still detects a face.

    0.0 = no detection in any jittered view (attack successful)
    1.0 = face detected in all jittered views (unperturbed / weak perturbation)

    Args:
        image_bgr: Source image or face crop (BGR numpy uint8).
        delta:     Float32 perturbation to add before scoring. None = no perturbation.
        n_aug:     Number of jitter augmentations. Higher = less noise, more queries.
        jitter_px: Max translation jitter in pixels (±jitter_px in x and y).

    Returns:
        float in [0, 1]
    """
    try:
        from src.models.detection_engine import DetectionEngine
    except ImportError:
        from models.detection_engine import DetectionEngine  # fallback for standalone script execution

    if delta is not None:
        query_img = np.clip(image_bgr.astype(np.float32) + delta, 0, 255).astype(np.uint8)
    else:
        query_img = image_bgr

    h, w = query_img.shape[:2]
    hits = 0
    for _ in range(n_aug):
        dx = np.random.randint(-jitter_px, jitter_px + 1)
        dy = np.random.randint(-jitter_px, jitter_px + 1)
        M = np.float32([[1, 0, dx], [0, 1, dy]])
        jittered = cv2.warpAffine(query_img, M, (w, h), borderMode=cv2.BORDER_REFLECT)
        with _landmarker_lock:
            detected = bool(DetectionEngine.detect_faces_pro(jittered))
        if detected:
            hits += 1
    return hits / n_aug


# ═══════════════════════════════════════════════════════════════════════════════
# Section 2: Block-Tiled Delta Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _low_dim_shape(region_shape: tuple, block_size: int) -> tuple:
    """Return the low-dimensional grid shape for a given block size."""
    h, w, ch = region_shape
    return (max(1, h // block_size), max(1, w // block_size), ch)


def _upsample_delta(delta_small: np.ndarray, target_shape: tuple) -> np.ndarray:
    """
    Upsample a low-dimensional block delta to full image shape using
    nearest-neighbour interpolation (block semantics: all pixels in a block
    receive the same perturbation value).
    """
    h, w, ch = target_shape
    out = np.empty(target_shape, dtype=np.float32)
    for c in range(ch):
        out[:, :, c] = cv2.resize(
            delta_small[:, :, c], (w, h), interpolation=cv2.INTER_NEAREST
        )
    return out


def build_face_oval_mask(region_shape: tuple, oval_points_local: list) -> np.ndarray:
    """
    Build a float32 mask (H, W, 1) that is 1.0 inside the face oval polygon
    and 0.0 outside. Restricts perturbation to biologically relevant pixels.

    Args:
        region_shape:       Shape of the crop region (H, W, C).
        oval_points_local:  List of (x, y) pixel coordinates of the face oval
                            polygon, expressed in crop-relative coordinates.

    Returns:
        Float32 array of shape (H, W, 1), values in {0.0, 1.0}.
    """
    mask_2d = np.zeros(region_shape[:2], dtype=np.float32)
    pts = np.array(oval_points_local, dtype=np.int32)
    cv2.fillPoly(mask_2d, [pts], 1.0)
    return mask_2d[:, :, np.newaxis]


# ═══════════════════════════════════════════════════════════════════════════════
# Section 3: Attack Engine
# ═══════════════════════════════════════════════════════════════════════════════

def adversarial_perturb(
    region_bgr: np.ndarray,
    face_oval_points_local: list | None = None,
    *,
    # Budget & stopping criteria
    max_eps: int = 110,
    iters: int = 40,
    # SPSA hyper-parameters
    k: int = 8,
    n_aug: int = 8,
    alpha_start: float = 10.0,
    c_start: float = 55.0,
    c_floor: float = 35.0,
    c_decay: float = 0.97,
    block_size: int = 32,
    # Verification
    verify_n_aug: int = 50,
    # Progress callback
    progress_callback=None,
    # Cooperative cancellation: callable returning True means "stop now"
    should_cancel=None,
) -> tuple[np.ndarray, float]:
    """
    Apply an adversarial perturbation to a face crop that causes
    MediaPipe FaceLandmarker to fail detection.

    This function is designed to be called from a background thread
    (e.g., QThread) and is thread-safe w.r.t. the FaceLandmarker singleton
    via an internal Lock.

    Args:
        region_bgr:              BGR numpy uint8 crop of the face area.
        face_oval_points_local:  Optional list of (x, y) polygon points of
                                 the face oval in crop coordinates. If None,
                                 perturbation is applied to the entire region.
        max_eps:                 Max per-channel perturbation amplitude (L∞ bound).
        iters:                   Max SPSA iterations.
        k:                       Number of random direction samples per iteration
                                 for gradient estimation.
        n_aug:                   EOT augmentations per score query.
        alpha_start:             SPSA step-size at iter 0.
        c_start:                 Initial exploration radius (should be within
                                 the signal region of the EOT curve, ~55).
        c_floor:                 Minimum exploration radius (prevents
                                 exploration from decaying to zero).
        c_decay:                 Multiplicative decay of c per iteration.
        block_size:              Spatial block size in pixels. Larger = fewer
                                 dimensions = faster but coarser perturbation.
        verify_n_aug:            n_aug used for final robust verification score.
        progress_callback:       Optional callable(iter: int, total: int,
                                 score: float) called after each iteration.
                                 Useful for progress dialogs.

    Returns:
        (delta, final_score):
          delta        — float32 array of same shape as region_bgr, ready to
                         add to the image (clip before display/save).
          final_score  — EOT score after all iterations (0.0 = fully evades
                         detection; >0.0 = partial or no evasion).
    """
    h, w, ch = region_bgr.shape
    small_shape = _low_dim_shape(region_bgr.shape, block_size)
    delta_small = np.zeros(small_shape, dtype=np.float32)
    c_i = c_start

    # Build face mask
    if face_oval_points_local is not None:
        mask_3d = build_face_oval_mask(region_bgr.shape, face_oval_points_local)
        if mask_3d.sum() == 0:
            raise ValueError(
                "Face oval mask is entirely empty. "
                "face_oval_points_local must be in crop-local coordinates "
                "(subtract the crop top-left offset from full-image coordinates). "
                f"Got points bounding box: {np.array(face_oval_points_local).min(axis=0).tolist()} "
                f"to {np.array(face_oval_points_local).max(axis=0).tolist()}, "
                f"crop shape: {region_bgr.shape[:2]}."
            )
    else:
        mask_3d = np.ones((h, w, 1), dtype=np.float32)

    # Initial score sanity check
    initial_score = eot_face_score(region_bgr, None, n_aug=n_aug)
    if initial_score == 0.0:
        # Already not detected — no perturbation needed
        return np.zeros_like(region_bgr, dtype=np.float32), 0.0

    final_score = initial_score

    for i in range(iters):
        a_i = alpha_start / ((i + 1) ** 0.2)
        ghat_small = np.zeros_like(delta_small)

        for _ in range(k):
            v_small = np.random.choice([-1.0, 1.0], size=delta_small.shape).astype(np.float32)

            d_pos = _upsample_delta(delta_small + c_i * v_small, region_bgr.shape) * mask_3d
            d_neg = _upsample_delta(delta_small - c_i * v_small, region_bgr.shape) * mask_3d

            score_pos = eot_face_score(region_bgr, d_pos, n_aug=n_aug)
            score_neg = eot_face_score(region_bgr, d_neg, n_aug=n_aug)

            ghat_small += ((score_pos - score_neg) / (2.0 * c_i)) * v_small

        ghat_small /= k

        if np.any(ghat_small != 0):
            delta_small = delta_small - a_i * np.sign(ghat_small)
            delta_small = np.clip(delta_small, -max_eps, max_eps)

        c_i = max(c_floor, c_i * c_decay)

        full_delta = _upsample_delta(delta_small, region_bgr.shape) * mask_3d
        cur_score = eot_face_score(region_bgr, full_delta, n_aug=n_aug)
        final_score = cur_score

        if progress_callback is not None:
            progress_callback(i + 1, iters, cur_score)

        if should_cancel is not None and should_cancel():
            break  # cooperative cancel — returns delta as-is (base effect preserved)

        if cur_score == 0.0:
            break

    # Robust final verification
    full_delta = _upsample_delta(delta_small, region_bgr.shape) * mask_3d
    final_score = eot_face_score(region_bgr, full_delta, n_aug=verify_n_aug)

    return full_delta, final_score


# ═══════════════════════════════════════════════════════════════════════════════
# Section 4: Hybrid Composer (the recommended integration path)
# ═══════════════════════════════════════════════════════════════════════════════

def compose_hybrid_effect(
    already_effected_region: np.ndarray,
    adversarial_delta: np.ndarray,
) -> np.ndarray:
    """
    Compose an adversarial delta on top of an already-effected region
    (e.g., a region that has already had blur or pixelation applied).

    In Hybrid Mode, the adversarial noise is added on top of blur/pixelation
    artifacts, making the noise visually indistinguishable from existing
    compression/blur artifacts to the human eye.

    Args:
        already_effected_region: BGR uint8 region AFTER the primary effect
                                 (blur, pixelation, etc.) has been applied.
        adversarial_delta:       Float32 delta from adversarial_perturb().

    Returns:
        BGR uint8 region with adversarial perturbation blended in.
    """
    result = already_effected_region.astype(np.float32) + adversarial_delta
    return np.clip(result, 0, 255).astype(np.uint8)


# ═══════════════════════════════════════════════════════════════════════════════
# Section 5: Perceptibility Diagnostics (for research / testing only)
# ═══════════════════════════════════════════════════════════════════════════════

def measure_perceptibility(original: np.ndarray, delta: np.ndarray) -> dict:
    """
    Measure the perceptual impact of an adversarial delta.

    Returns a dict with:
      psnr       — Peak Signal-to-Noise Ratio in dB (>40 = invisible, <30 = noticeable)
      max_delta  — Max absolute perturbation value (L∞ norm)
      mean_delta — Mean absolute perturbation value
    """
    perturbed = np.clip(original.astype(np.float32) + delta, 0, 255).astype(np.uint8)
    psnr = cv2.PSNR(original, perturbed)
    return {
        "psnr": psnr,
        "max_delta": float(np.max(np.abs(delta))),
        "mean_delta": float(np.mean(np.abs(delta))),
    }
