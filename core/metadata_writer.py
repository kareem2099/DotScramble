"""
DotScramble — saving a photo together with its metadata.

One place decides what happens to every metadata field, writes the image once with
that metadata, and then reads the saved file back to check it.

    original = load_exif(source_path)                    # when the photo is opened
    plan = make_plan(original, "location", ext=".jpg")   # what each field becomes
    write_image(processed_bgr, out_path, plan)           # one encode, metadata included
    problems = verify(out_path, plan, original)          # [] when the file is as planned

Modes:
    keep      the original metadata, minus what is never safe to keep (see below)
    location  the original metadata without GPS
    strip     no metadata at all
    spoof     believable decoys from a profile (ghost / troll / artist)
    custom    per-field actions from the metadata editor

Whatever the mode, the saved file never carries the original's embedded thumbnail
(a small copy of the *unedited* photo, faces included) and its Orientation is always 1,
because the pixels were already rotated upright when the photo was loaded.
"""
from __future__ import annotations

import io
import os
import random
import tempfile
from dataclasses import dataclass, field

import cv2
import numpy as np
import piexif
from PIL import Image, PngImagePlugin

import math
from datetime import datetime, timedelta

from core.metadata_spoofer import (
    MODERN_PHONES,
    PROFILES,
    _build_gps_ifd,
    _fake_timestamp,
    _pick_camera,
    _pick_gps,
)

MODES = ("keep", "location", "strip", "spoof", "custom")
FIELD_KEYS = ("gps", "make", "model", "software", "datetime", "copyright", "exposure", "fingerprint")
# Metadata outside EXIF. The saved file never carries these (the photo is re-encoded, or, when only
# the metadata is cleaned, their segments are dropped) except the color profile, which is kept.
EXTRA_KEYS = ("xmp", "iptc", "text", "extra_images", "icc")

# Tags that identify the device or its owner rather than the photo
_FINGERPRINT_TAGS = (("Exif", piexif.ExifIFD.BodySerialNumber), ("Exif", piexif.ExifIFD.LensSerialNumber),
                     ("Exif", piexif.ExifIFD.CameraOwnerName), ("Exif", piexif.ExifIFD.ImageUniqueID),
                     ("Exif", piexif.ExifIFD.MakerNote), ("0th", piexif.ImageIFD.Artist))

# Formats that can carry EXIF. BMP, GIF and the rest are always saved without metadata.
METADATA_FORMATS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}
JPEG_QUALITY = 95

# Files are written to a private temp file and then renamed into place; they get the permissions
# a normally created file would (or keep those of the file they replace), not mkstemp's 0600.
_UMASK = os.umask(0)
os.umask(_UMASK)

_EXPOSURE_TAGS = (piexif.ExifIFD.ExposureTime, piexif.ExifIFD.FNumber,
                  piexif.ExifIFD.ISOSpeedRatings, piexif.ExifIFD.Flash)
_DATETIME_TAGS = ((("0th", piexif.ImageIFD.DateTime)),
                  (("Exif", piexif.ExifIFD.DateTimeOriginal)),
                  (("Exif", piexif.ExifIFD.DateTimeDigitized)))


@dataclass
class FieldChange:
    key: str            # one of FIELD_KEYS, or "thumbnail"
    before: str | None  # readable value in the original (None: not there)
    after: str | None   # readable value in the saved file (None: not there)
    action: str         # "keep" | "remove" | "replace"


@dataclass
class MetadataPlan:
    mode: str
    exif: dict | None                     # piexif dict to write; None writes no EXIF
    png_text: dict = field(default_factory=dict)
    changes: list = field(default_factory=list)
    supported: bool = True                # False: this format can't hold metadata
    profile: str | None = None
    icc: bytes | None = None              # the original's color profile, written back
    pixels_upright: bool = True           # False when only the metadata is cleaned (pixels untouched)


# ── reading ──────────────────────────────────────────────────────────────────

def load_exif(path: str) -> dict | None:
    """The photo's EXIF as a piexif dict, or None when it has none (or can't be read)."""
    try:
        with Image.open(path) as im:
            raw = im.info.get("exif")
            fmt = im.format
        if not raw and fmt == "TIFF":
            data = piexif.load(path)
        elif raw:
            if not raw.startswith((b"Exif\x00\x00", b"II*\x00", b"MM\x00*")):
                raw = b"Exif\x00\x00" + raw
            data = piexif.load(raw)
        else:
            return None
    except Exception:
        return None
    return data if _has_any(data) else None


def _has_any(exif: dict | None) -> bool:
    return bool(exif) and any(exif.get(ifd) for ifd in ("0th", "Exif", "GPS", "1st")) or bool(exif and exif.get("thumbnail"))


def _text(ifd: dict, tag) -> str | None:
    value = ifd.get(tag)
    if isinstance(value, bytes):
        value = value.decode(errors="ignore").strip("\x00").strip()
    elif value is not None:
        value = str(value)
    return value or None


def _ratio(value) -> float | None:
    if isinstance(value, (tuple, list)) and len(value) == 2 and value[1]:
        return value[0] / value[1]
    return None


def gps_of(exif: dict | None) -> tuple[float, float] | None:
    gps = (exif or {}).get("GPS") or {}

    def decimal(dms, ref):
        if not dms or len(dms) < 3:
            return None
        parts = [_ratio(p) for p in dms[:3]]
        if parts[0] is None:
            return None
        value = parts[0] + (parts[1] or 0) / 60 + (parts[2] or 0) / 3600
        return -value if ref in (b"S", b"W", "S", "W") else value

    lat = decimal(gps.get(piexif.GPSIFD.GPSLatitude), gps.get(piexif.GPSIFD.GPSLatitudeRef, b"N"))
    lon = decimal(gps.get(piexif.GPSIFD.GPSLongitude), gps.get(piexif.GPSIFD.GPSLongitudeRef, b"E"))
    if lat is None or lon is None:
        return None
    return round(lat, 6), round(lon, 6)


def fields_of(exif: dict | None) -> dict:
    """Readable values of the fields the app shows and edits (None where absent)."""
    exif = exif or {}
    zeroth, sub = exif.get("0th") or {}, exif.get("Exif") or {}
    gps = gps_of(exif)
    exposure = None
    shutter, fnumber = _ratio(sub.get(piexif.ExifIFD.ExposureTime)), _ratio(sub.get(piexif.ExifIFD.FNumber))
    iso = sub.get(piexif.ExifIFD.ISOSpeedRatings)
    if isinstance(iso, (tuple, list)):
        iso = iso[0] if iso else None
    if any(v is not None for v in (shutter, fnumber, iso)):
        exposure = " · ".join(filter(None, [
            (f"1/{round(1 / shutter)} s" if shutter and shutter < 1 else f"{shutter:g} s") if shutter else None,
            f"f/{fnumber:.1f}" if fnumber else None,
            f"ISO {iso}" if iso else None,
        ]))
    stamp = _text(sub, piexif.ExifIFD.DateTimeOriginal) or _text(zeroth, piexif.ImageIFD.DateTime)
    if stamp and len(stamp) >= 10 and stamp[4] == ":" and stamp[7] == ":":
        stamp = f"{stamp[:4]}-{stamp[5:7]}-{stamp[8:]}"      # EXIF's "2026:10:24 18:42" → "2026-10-24 18:42"
    ids = [_text(sub, piexif.ExifIFD.BodySerialNumber), _text(sub, piexif.ExifIFD.LensSerialNumber),
           _text(sub, piexif.ExifIFD.CameraOwnerName), _text(zeroth, piexif.ImageIFD.Artist),
           _text(sub, piexif.ExifIFD.ImageUniqueID)]
    if piexif.ExifIFD.MakerNote in sub:
        ids.append("MakerNote")
    fingerprint = " · ".join(v for v in ids if v) or None
    return {
        "gps": f"{gps[0]:.5f}, {gps[1]:.5f}" if gps else None,
        "make": _text(zeroth, piexif.ImageIFD.Make),
        "model": _text(zeroth, piexif.ImageIFD.Model),
        "software": _text(zeroth, piexif.ImageIFD.Software),
        "datetime": stamp,
        "copyright": _text(zeroth, piexif.ImageIFD.Copyright),
        "exposure": exposure,
        "fingerprint": fingerprint,
    }


_FACE_REGION_MARKERS = (b"mwg-rs:Regions", b"MP:RegionInfo", b"MPRI:Regions", b"mwg-rs:RegionList")


def jpeg_segments(data: bytes) -> tuple[list[tuple[int, bytes]], bytes]:
    """
    Split a JPEG into its marker segments up to and including the scan (SOS → EOI), and
    whatever follows the first EOI (other images: MPF previews, depth maps, vendor trailers).
    Each segment is (marker, raw bytes including the FF xx marker).
    """
    if data[:2] != b"\xff\xd8":
        raise ValueError("not a JPEG")
    segments, i = [(0xD8, data[:2])], 2
    while i + 4 <= len(data):
        if data[i] != 0xFF:
            raise ValueError("bad JPEG marker")
        marker = data[i + 1]
        if marker == 0xFF:          # fill byte
            i += 1
            continue
        if marker == 0xDA:          # start of scan: entropy-coded data up to the EOI
            j = i + 2
            while True:
                j = data.find(b"\xff", j)
                if j < 0 or j + 1 >= len(data):
                    return segments + [(0xDA, data[i:])], b""
                nxt = data[j + 1]
                if nxt == 0xD9:
                    segments.append((0xDA, data[i:j + 2]))
                    return segments, data[j + 2:]
                j += 2 if nxt == 0x00 or 0xD0 <= nxt <= 0xD7 else 1
        length = int.from_bytes(data[i + 2:i + 4], "big")
        segments.append((marker, data[i:i + 2 + length]))
        i += 2 + length
    return segments, b""


def inspect_extras(path: str) -> dict:
    """What the file carries besides EXIF: XMP (and face regions in it), IPTC, text notes,
    extra images, and the ICC color profile (bytes)."""
    found = {"xmp": False, "face_regions": False, "iptc": False, "text": [], "extra_images": False, "icc": None}
    try:
        with Image.open(path) as im:
            info, fmt = dict(im.info), im.format
            text_keys = list(getattr(im, "text", {}) or {}) if fmt == "PNG" else []
            tags = dict(getattr(im, "tag_v2", {}) or {}) if fmt == "TIFF" else {}
    except Exception:
        return found
    xmp = info.get("xmp") or tags.get(700) or b""
    if isinstance(xmp, str):
        xmp = xmp.encode(errors="ignore")
    found["xmp"] = bool(xmp)
    found["face_regions"] = any(m in xmp for m in _FACE_REGION_MARKERS)
    found["icc"] = info.get("icc_profile") or None
    found["text"] = [k for k in text_keys if k not in ("XML:com.adobe.xmp",)]
    found["iptc"] = bool(tags.get(33723))
    if fmt == "JPEG":
        try:
            with open(path, "rb") as fh:
                segments, trailer = jpeg_segments(fh.read())
            for marker, raw in segments:
                payload = raw[4:]
                if marker == 0xED and payload.startswith(b"Photoshop 3.0"):
                    found["iptc"] = True
                elif marker == 0xE2 and payload.startswith(b"MPF\x00"):
                    found["extra_images"] = True
                elif marker == 0xFE:
                    found["text"].append("JPEG comment")
            if trailer.strip(b"\x00"):
                found["extra_images"] = True
        except (OSError, ValueError):
            pass
    return found


def has_thumbnail(exif: dict | None) -> bool:
    return bool(exif and (exif.get("thumbnail") or exif.get("1st")))


# ── planning ─────────────────────────────────────────────────────────────────

def _copy(exif: dict | None) -> dict:
    exif = exif or {}
    return {ifd: dict(exif.get(ifd) or {}) for ifd in ("0th", "Exif", "GPS", "Interop")}


def _sanitize(exif: dict, size: tuple[int, int] | None, orientation) -> dict:
    """Never keep the embedded thumbnail. Orientation is 1 when the pixels were rotated upright
    on loading, or the original value when they are written back untouched."""
    exif.pop("1st", None)
    exif.pop("thumbnail", None)
    exif.setdefault("0th", {}).pop(piexif.ImageIFD.Orientation, None)
    if orientation not in (None, 1):
        exif["0th"][piexif.ImageIFD.Orientation] = orientation
    if size:
        width, height = size
        sub = exif.setdefault("Exif", {})
        if piexif.ExifIFD.PixelXDimension in sub:
            sub[piexif.ExifIFD.PixelXDimension] = width
        if piexif.ExifIFD.PixelYDimension in sub:
            sub[piexif.ExifIFD.PixelYDimension] = height
    return exif


def _set_datetime(exif: dict, value: str | None) -> None:
    for ifd, tag in _DATETIME_TAGS:
        exif.setdefault(ifd, {}).pop(tag, None)
        if value:
            exif[ifd][tag] = value.encode()


def _decoy_exposure() -> dict:
    return {
        piexif.ExifIFD.ExposureTime: (1, random.choice([30, 60, 100, 125, 250, 500])),
        piexif.ExifIFD.FNumber: (random.choice([18, 20, 25, 28, 35, 40]), 10),
        piexif.ExifIFD.ISOSpeedRatings: random.choice([100, 200, 400, 800]),
        piexif.ExifIFD.Flash: 0,
    }


def _nearby(lat: float, lon: float, rng=random) -> tuple[float, float]:
    """A point 2–8 km from (lat, lon) in a random direction: the same city, not the same street."""
    distance, bearing = rng.uniform(2.0, 8.0), rng.uniform(0, 2 * math.pi)
    dlat = distance / 111.32 * math.cos(bearing)
    dlon = distance / (111.32 * max(math.cos(math.radians(lat)), 0.01)) * math.sin(bearing)
    return round(max(-89.9, min(89.9, lat + dlat)), 6), round(((lon + dlon + 180) % 360) - 180, 6)


def _shifted(stamp: str | None, rng=random) -> str:
    """The real capture time moved by 1–10 days and up to 5 hours, either way."""
    try:
        when = datetime.strptime(stamp or "", "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return _fake_timestamp("recent")
    delta = timedelta(days=rng.randint(1, 10), hours=rng.randint(0, 5), minutes=rng.randint(0, 59),
                      seconds=rng.randint(0, 59))
    later = when + delta
    # Never into the future, and never capped at "now": a capture time equal to the moment the
    # file was saved is a giveaway, and photos saved together would all share it
    when = later if rng.random() < 0.5 and later < datetime.now() - timedelta(hours=1) else when - delta
    return when.strftime("%Y:%m:%d %H:%M:%S")


def _blend(original: dict | None) -> tuple[dict, dict]:
    """Decoys that look like an ordinary photo, derived from (but never equal to) the real ones."""
    real_make = (fields_of(original)["make"] or "").lower()
    phones = [p for p in MODERN_PHONES if p[0].lower() != real_make] or MODERN_PHONES
    make, model, software = random.choice(phones)
    sub = (original or {}).get("Exif") or {}
    raw_stamp = sub.get(piexif.ExifIFD.DateTimeOriginal) or ((original or {}).get("0th") or {}).get(piexif.ImageIFD.DateTime)
    stamp = _shifted(raw_stamp.decode(errors="ignore") if isinstance(raw_stamp, bytes) else raw_stamp)
    exif = {
        "0th": {piexif.ImageIFD.Make: make.encode(), piexif.ImageIFD.Model: model.encode(),
                piexif.ImageIFD.Software: software.encode()},
        "Exif": {piexif.ExifIFD.ColorSpace: 1,
                 piexif.ExifIFD.ExposureTime: (1, random.choice([60, 120, 250, 500, 1000])),
                 piexif.ExifIFD.FNumber: (random.choice([16, 17, 18, 19, 22]), 10),
                 piexif.ExifIFD.ISOSpeedRatings: random.choice([50, 64, 100, 200, 400, 800]),
                 piexif.ExifIFD.Flash: 16},
        "GPS": {}, "Interop": {},
    }
    _set_datetime(exif, stamp)
    real = gps_of(original)
    if real:
        exif["GPS"] = _build_gps_ifd(*_nearby(*real))
        # An altitude of exactly 0 m stands out: carry over the real one, a little off, or leave it out
        gps_real = (original or {}).get("GPS") or {}
        alt = gps_real.get(piexif.GPSIFD.GPSAltitude)
        exif["GPS"].pop(piexif.GPSIFD.GPSAltitude, None)
        exif["GPS"].pop(piexif.GPSIFD.GPSAltitudeRef, None)
        try:
            metres = alt[0] / alt[1] if alt and alt[1] else None
        except (TypeError, IndexError):
            metres = None
        if metres is not None:
            # 3–15 m up or down: close to the real one, but never equal to it after rounding
            moved = max(0.0, metres + random.choice((-1, 1)) * random.uniform(3, 15))
            if round(moved * 10) == round(metres * 10):
                moved = metres + 3
            exif["GPS"][piexif.GPSIFD.GPSAltitude] = (round(moved * 10), 10)
            exif["GPS"][piexif.GPSIFD.GPSAltitudeRef] = gps_real.get(piexif.GPSIFD.GPSAltitudeRef, b"\x00")
    return exif, {"Software": software, "Author": make}


def _decoy(profile: str, original: dict | None) -> tuple[dict, dict]:
    """A fresh set of believable fake metadata (EXIF and PNG text) for a profile."""
    if profile == "blend":
        return _blend(original)
    settings = PROFILES.get(profile, PROFILES["troll"])
    real_make = (fields_of(original)["make"] or "").lower()
    make, model, software = _pick_camera(settings.get("camera"))
    for _attempt in range(20):   # a decoy that happens to match the real maker would read as "kept"
        if make.lower() != real_make:
            break
        make, model, software = _pick_camera("random")
    lat, lon = _pick_gps(settings.get("gps_preset"), None)
    stamp = _fake_timestamp(settings.get("fake_datetime_mode", "random"))
    exif = {
        "0th": {
            piexif.ImageIFD.Make: make.encode(),
            piexif.ImageIFD.Model: model.encode(),
            piexif.ImageIFD.Software: software.encode(),
            piexif.ImageIFD.Orientation: 1,
        },
        "Exif": {piexif.ExifIFD.ColorSpace: 1, **_decoy_exposure()},
        "GPS": _build_gps_ifd(lat, lon),
        "Interop": {},
    }
    _set_datetime(exif, stamp)
    # "artist" keeps the photographer's own copyright line, when the photo has one
    copyright_text = fields_of(original)["copyright"] if settings.get("keep_copyright") else None
    if copyright_text:
        exif["0th"][piexif.ImageIFD.Copyright] = copyright_text.encode()
    png_text = {"Software": software, "Author": make}
    return exif, png_text


def _custom(actions: dict, original: dict | None) -> dict:
    """Per-field actions from the editor applied to the original's metadata."""
    exif = _copy(original)
    zeroth, sub = exif["0th"], exif["Exif"]
    make, model, software = _pick_camera("random")
    decoys = {"make": make, "model": model, "software": software,
              "datetime": _fake_timestamp("random"), "copyright": "All rights reserved"}
    text_tags = {"make": piexif.ImageIFD.Make, "model": piexif.ImageIFD.Model,
                 "software": piexif.ImageIFD.Software, "copyright": piexif.ImageIFD.Copyright}

    for ifd, tag in _FINGERPRINT_TAGS:   # the editor has no row for these: never carried over
        exif[ifd].pop(tag, None)

    for key in ("make", "model", "software", "copyright", "datetime"):
        action = actions.get(key, "keep")
        if action == "keep":
            continue
        value = None
        if action == "spoof":
            value = decoys[key]
        elif isinstance(action, dict):
            value = (action.get("value") or "").strip() or None
        if key == "datetime":
            _set_datetime(exif, value)
        else:
            zeroth.pop(text_tags[key], None)
            if value:
                zeroth[text_tags[key]] = value.encode()

    gps_action = actions.get("gps", "keep")
    if gps_action == "strip":
        exif["GPS"] = {}
    elif gps_action == "spoof":
        exif["GPS"] = _build_gps_ifd(*_pick_gps("pacific", None))
    elif isinstance(gps_action, dict) and "lat" in gps_action and "lon" in gps_action:
        exif["GPS"] = _build_gps_ifd(float(gps_action["lat"]), float(gps_action["lon"]))

    exposure_action = actions.get("exposure", "keep")
    if exposure_action in ("strip", "spoof"):
        for tag in _EXPOSURE_TAGS:
            sub.pop(tag, None)
        if exposure_action == "spoof":
            sub.update(_decoy_exposure())
    return exif


def make_plan(original: dict | None, mode: str, *, ext: str, profile: str | None = None,
              field_actions: dict | None = None, size: tuple[int, int] | None = None,
              extras: dict | None = None, pixels_upright: bool = True) -> MetadataPlan:
    """
    What the saved file will carry, field by field, for `mode`.
    extras: inspect_extras() of the source file, so the report can list XMP, IPTC & co.
    pixels_upright: False when the pixels are written back untouched (metadata-only cleaning).
    """
    if mode not in MODES:
        raise ValueError(f"unknown metadata mode {mode!r}")
    ext = ext.lower()
    supported = ext in METADATA_FORMATS
    png_text: dict = {}

    if mode == "keep":
        exif = _copy(original)
    elif mode == "location":
        exif = _copy(original)
        exif["GPS"] = {}
    elif mode == "strip":
        exif = None
    elif mode == "spoof":
        exif, png_text = _decoy(profile or "troll", original)
    else:
        exif = _custom(field_actions or {}, original)

    original_orientation = ((original or {}).get("0th") or {}).get(piexif.ImageIFD.Orientation)
    orientation = None if pixels_upright else original_orientation
    if exif is not None:
        exif = _sanitize(exif, size, orientation)
        if not _has_any(exif):
            exif = None
    elif orientation not in (None, 1):
        exif = {"0th": {piexif.ImageIFD.Orientation: orientation}, "Exif": {}, "GPS": {}, "Interop": {}}
    extras = extras or {}
    icc = extras.get("icc") if supported else None
    if not supported:
        exif, png_text = None, {}
    if ext != ".png":
        png_text = {}

    before, after = fields_of(original), fields_of(exif)
    changes = []
    for key in FIELD_KEYS:
        b, a = before[key], after[key]
        if b is None and a is None:
            continue
        action = "keep" if b == a else "remove" if a is None else "replace"
        changes.append(FieldChange(key, b, a, action))
    if has_thumbnail(original):
        changes.append(FieldChange("thumbnail", "yes", None, "remove"))
    if extras.get("xmp"):
        changes.append(FieldChange("xmp", "face_regions" if extras.get("face_regions") else "yes", None, "remove"))
    if extras.get("iptc"):
        changes.append(FieldChange("iptc", "yes", None, "remove"))
    if extras.get("text"):
        changes.append(FieldChange("text", ", ".join(extras["text"]), None, "remove"))
    if extras.get("extra_images"):
        changes.append(FieldChange("extra_images", "yes", None, "remove"))
    if extras.get("icc"):
        changes.append(FieldChange("icc", "yes", "yes" if icc else None, "keep" if icc else "remove"))

    return MetadataPlan(mode=mode, exif=exif, png_text=png_text, changes=changes, supported=supported,
                        profile=profile, icc=icc, pixels_upright=pixels_upright)


# ── writing ──────────────────────────────────────────────────────────────────

def _dump(exif: dict) -> bytes:
    """piexif.dump, dropping tags it can't encode instead of failing the whole save."""
    try:
        return piexif.dump(exif)
    except Exception:
        pass
    clean: dict = {ifd: {} for ifd in ("0th", "Exif", "GPS", "Interop")}
    for ifd in clean:
        for tag, value in (exif.get(ifd) or {}).items():
            trial = {k: dict(v) for k, v in clean.items()}
            trial[ifd][tag] = value
            try:
                piexif.dump(trial)
            except Exception:
                continue
            clean[ifd][tag] = value
    return piexif.dump(clean)


def _icc_segments(icc: bytes) -> bytes:
    """The ICC profile as JPEG APP2 segments (split in chunks of at most 65 519 bytes)."""
    chunk = 65519
    parts = [icc[i:i + chunk] for i in range(0, len(icc), chunk)] or [b""]
    out = b""
    for n, part in enumerate(parts, 1):
        payload = b"ICC_PROFILE\x00" + bytes([n, len(parts)]) + part
        out += b"\xff\xe2" + (len(payload) + 2).to_bytes(2, "big") + payload
    return out


def _with_jpeg_metadata(segments: list[tuple[int, bytes]], exif_bytes: bytes | None, icc: bytes | None,
                        keep_icc_segments: bool) -> bytes:
    """Rebuild a JPEG from its segments: JFIF / Adobe headers, the new EXIF, the color profile
    and the image data; every other APPn segment and comment is dropped."""
    head, body = [], []
    for marker, raw in segments:
        payload = raw[4:]
        if marker == 0xD8:
            continue
        if marker == 0xE0 or marker == 0xEE:          # JFIF / Adobe color transform: needed to decode
            head.append(raw)
        elif marker == 0xE2 and payload.startswith(b"ICC_PROFILE") and keep_icc_segments:
            head.append(raw)
        elif 0xE0 <= marker <= 0xEF or marker == 0xFE:  # EXIF, XMP, MPF, IPTC, vendor data, comments
            continue
        else:
            body.append(raw)
    out = b"\xff\xd8" + b"".join(head)
    if exif_bytes:
        exif_payload = exif_bytes if exif_bytes.startswith(b"Exif\x00\x00") else b"Exif\x00\x00" + exif_bytes
        out += b"\xff\xe1" + (len(exif_payload) + 2).to_bytes(2, "big") + exif_payload
    if icc and not keep_icc_segments:
        out += _icc_segments(icc)
    return out + b"".join(body)


def _encode(image_bgr: np.ndarray, ext: str, plan: MetadataPlan) -> bytes:
    exif_bytes = _dump(plan.exif) if plan.exif else None

    if ext in (".jpg", ".jpeg"):
        ok, buf = cv2.imencode(".jpg", image_bgr, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        if not ok:
            raise OSError("JPEG encoding failed")
        segments, _trailer = jpeg_segments(buf.tobytes())
        # metadata goes in as new segments; the encoded pixels are not touched again
        return _with_jpeg_metadata(segments, exif_bytes, plan.icc, keep_icc_segments=False)

    if ext in (".png", ".webp", ".tif", ".tiff") and (exif_bytes or plan.png_text or plan.icc):
        rgb = Image.fromarray(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB))
        out = io.BytesIO()
        kwargs = {}
        if exif_bytes:
            kwargs["exif"] = exif_bytes
        if plan.icc:
            kwargs["icc_profile"] = plan.icc
        if ext == ".png":
            if plan.png_text:
                info = PngImagePlugin.PngInfo()
                for key, value in plan.png_text.items():
                    info.add_text(key, value)
                kwargs["pnginfo"] = info
            rgb.save(out, "PNG", **kwargs)
        elif ext == ".webp":
            rgb.save(out, "WEBP", quality=JPEG_QUALITY, method=6, **kwargs)
        else:
            # libtiff refuses EXIF together with LZW / deflate, so EXIF-carrying TIFFs are uncompressed
            rgb.save(out, "TIFF", **kwargs)
        return out.getvalue()

    ok, buf = cv2.imencode(ext, image_bgr)
    if not ok:
        raise OSError(f"encoding {ext} failed")
    return buf.tobytes()


def write_image(image_bgr: np.ndarray, path: str, plan: MetadataPlan) -> None:
    """Encode once with the planned metadata and replace `path` atomically."""
    ext = os.path.splitext(path)[1].lower()
    _write_atomically(path, _encode(image_bgr, ext, plan))


def clean_file(source: str, target: str, plan: MetadataPlan) -> None:
    """
    Write `source` to `target` with only the planned metadata, without changing its pixels:
    JPEG data is copied as-is (no re-encoding) and anything after the main image (MPF
    previews, depth maps) is dropped; PNG, WebP (lossless) and TIFF are rewritten pixel for pixel.
    """
    ext = os.path.splitext(target)[1].lower()
    src_ext = os.path.splitext(source)[1].lower()
    exif_bytes = _dump(plan.exif) if plan.exif else None

    if src_ext in (".jpg", ".jpeg") and ext in (".jpg", ".jpeg"):
        with open(source, "rb") as fh:
            segments, _trailer = jpeg_segments(fh.read())
        data = _with_jpeg_metadata(segments, exif_bytes, plan.icc, keep_icc_segments=bool(plan.icc))
    else:
        with Image.open(source) as im:
            im.load()
            frame = im.copy()
        out = io.BytesIO()
        kwargs = {}
        if exif_bytes and ext in METADATA_FORMATS:
            kwargs["exif"] = exif_bytes
        if plan.icc and ext in METADATA_FORMATS:
            kwargs["icc_profile"] = plan.icc
        if ext == ".png":
            frame.save(out, "PNG", **kwargs)
        elif ext == ".webp":
            frame.save(out, "WEBP", lossless=True, **kwargs)
        elif ext in (".tif", ".tiff"):
            frame.save(out, "TIFF", **kwargs)
        elif ext in (".jpg", ".jpeg"):
            frame.convert("RGB").save(out, "JPEG", quality=JPEG_QUALITY, **kwargs)
        else:
            frame.save(out, format=Image.registered_extensions().get(ext, "PNG"))
        data = out.getvalue()
    _write_atomically(target, data)


def _write_atomically(path: str, data: bytes) -> None:
    folder = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(prefix=".dotscramble-", suffix=os.path.splitext(path)[1], dir=folder)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        try:
            mode = os.stat(path).st_mode & 0o7777
        except OSError:
            mode = 0o666 & ~_UMASK
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ── checking ─────────────────────────────────────────────────────────────────

def verify(path: str, plan: MetadataPlan, original: dict | None) -> list[str]:
    """Problems found in the saved file ([] when it carries exactly what was planned)."""
    saved = load_exif(path)
    problems = []
    if has_thumbnail(saved):
        problems.append("thumbnail")
    orientation = ((saved or {}).get("0th") or {}).get(piexif.ImageIFD.Orientation)
    planned_orientation = ((plan.exif or {}).get("0th") or {}).get(piexif.ImageIFD.Orientation) or 1
    if (orientation or 1) != planned_orientation:
        problems.append("orientation")
    extras = inspect_extras(path)
    unplanned_text = [k for k in extras["text"] if k not in plan.png_text]   # decoy text is planned
    if extras["xmp"] or extras["iptc"] or extras["extra_images"] or unplanned_text:
        problems.append("extras_left")

    saved_gps, planned_gps, original_gps = gps_of(saved), gps_of(plan.exif), gps_of(original)
    if planned_gps is None and saved_gps is not None:
        problems.append("gps_left")
    if (plan.mode in ("spoof", "custom") and original_gps and saved_gps
            and planned_gps != original_gps and _near(saved_gps, original_gps)):
        problems.append("real_gps")
    if plan.exif is None and any(v for k, v in fields_of(saved).items()):
        problems.append("metadata_left")
    return problems


def _near(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return abs(a[0] - b[0]) < 1e-4 and abs(a[1] - b[1]) < 1e-4
