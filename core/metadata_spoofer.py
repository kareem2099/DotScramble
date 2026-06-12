#!/usr/bin/env python3
"""
DotScramble — Metadata Spoofer
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Paid feature (Pro/Max tier).

Injects plausible-but-fake EXIF/metadata into JPEG or PNG files,
turning a silent strip (which can look suspicious) into active
disinformation against tracking algorithms.

Usage (standalone):
    python metadata_spoofer.py photo.jpg --profile ghost
    python metadata_spoofer.py photo.jpg --gps-preset pacific --camera random
    python metadata_spoofer.py photo.jpg --gps-custom 23.4 -54.2 --keep-copyright
    python metadata_spoofer.py photo.jpg --dry-run

Usage (import):
    from metadata_spoofer import spoof
    result = spoof("photo.jpg", profile="ghost")
    print(result)
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

import piexif
from PIL import Image, PngImagePlugin

# ─── Camera database ───────────────────────────────────────────────────────────
# Intentionally vintage / implausible to maximally confuse device fingerprinting
FAKE_CAMERAS: list[tuple[str, str, str]] = [
    ("Nokia",     "3310",              "Nokia Imaging 1.0"),
    ("Motorola",  "RAZR V3",           "Motorola Camera 1.2"),
    ("Samsung",   "SCH-U340",          "Samsung Digimax 2.1"),
    ("Casio",     "QV-10A",            "Casio Digital Camera"),
    ("Polaroid",  "PDC 640",           "Polaroid Software 1.1"),
    ("Kodak",     "DC40",              "Kodak EasyShare 3.0"),
    ("Fujifilm",  "FinePix A101",      "FinePixViewer Ver.3.1"),
    ("Canon",     "PowerShot A5",      "Canon PowerShot A5 JPEG"),
    ("Sony",      "Cyber-shot DSC-P1", "Sony DSC 1.0"),
    ("Olympus",   "D-340L",            "Olympus Optical Co."),
    ("Nikon",     "COOLPIX 900",       "Nikon COOLPIX900"),
    ("HP",        "PhotoSmart 315",    "HP Photosmart 315 v1.0"),
    ("Agfa",      "ePhoto 1680",       "Agfa Photo"),
    ("Minolta",   "DiMAGE E201",       "Minolta Co.,Ltd."),
    ("Panasonic", "DMC-LC33",          "Panasonic"),
]

# ─── GPS presets ───────────────────────────────────────────────────────────────
GPS_PRESETS: dict[str, tuple[float, float]] = {
    "pacific":    (   4.2234,  -157.4521),  # Middle of Pacific
    "atlantic":   (  23.8821,   -42.3312),  # Mid-Atlantic
    "indian":     ( -18.4456,    72.1234),  # Indian Ocean
    "antarctica": ( -89.3312,    12.0000),  # Antarctica
    "arctic":     (  89.1122,  -178.4343),  # Arctic Ocean
    "sahara":     (  23.4122,    10.9988),  # Remote Sahara (no cell towers)
    "mongolia":   (  45.2345,   101.5678),  # Remote Mongolian steppe
    "amazon":     (  -5.3421,   -63.2231),  # Deep Amazon basin
}

# ─── Profiles ──────────────────────────────────────────────────────────────────
# Opinionated presets for common use cases
PROFILES: dict[str, dict] = {
    "ghost": {
        # Maximum obfuscation — antique camera, Antarctic GPS, epoch timestamp
        "gps_preset":          "antarctica",
        "camera":              "Nokia 3310",
        "fake_datetime_mode":  "epoch",
        "keep_copyright":      False,
        "description":         "Maximum obfuscation. Nokia 3310 in Antarctica, year 2000.",
    },
    "troll": {
        # Plausibly wrong — recent vintage camera, random ocean, recent-ish date
        "gps_preset":          "pacific",
        "camera":              "random",
        "fake_datetime_mode":  "recent",
        "keep_copyright":      False,
        "description":         "Plausible-but-wrong. Random ocean, random vintage camera.",
    },
    "artist": {
        # For photographers — strips location+device, preserves copyright
        "gps_preset":          "atlantic",
        "camera":              "random",
        "fake_datetime_mode":  "random",
        "keep_copyright":      True,
        "description":         "Privacy for photographers. Keeps copyright, fakes location+device.",
    },
}


# ─── Internal helpers ──────────────────────────────────────────────────────────

def _dms_rational(value: float) -> tuple[tuple[int, int], ...]:
    """Convert decimal degrees → (deg, min, sec) as EXIF rational tuples."""
    abs_v = abs(value)
    deg   = int(abs_v)
    m_f   = (abs_v - deg) * 60
    mins  = int(m_f)
    secs  = round((m_f - mins) * 60 * 10_000)
    return ((deg, 1), (mins, 1), (secs, 10_000))


def _build_gps_ifd(lat: float, lon: float) -> dict:
    return {
        piexif.GPSIFD.GPSLatitudeRef:   b"S" if lat < 0 else b"N",
        piexif.GPSIFD.GPSLatitude:      _dms_rational(lat),
        piexif.GPSIFD.GPSLongitudeRef:  b"W" if lon < 0 else b"E",
        piexif.GPSIFD.GPSLongitude:     _dms_rational(lon),
        piexif.GPSIFD.GPSAltitude:      (0, 1),
        piexif.GPSIFD.GPSAltitudeRef:   b"\x00",
        piexif.GPSIFD.GPSMapDatum:      b"WGS-84",
    }


def _fake_timestamp(mode: str = "random") -> str:
    """Return EXIF-formatted fake timestamp."""
    if mode == "epoch":
        return "2000:01:01 00:00:00"
    elif mode == "recent":
        delta = timedelta(
            days=random.randint(30, 730),
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59),
        )
    else:  # "random"
        delta = timedelta(
            days=random.randint(365, 4380),
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59),
        )
    ts = datetime.now() - delta
    return ts.strftime("%Y:%m:%d %H:%M:%S")


def _pick_camera(camera_arg: str | None) -> tuple[str, str, str]:
    """Resolve camera arg → (make, model, software)."""
    if camera_arg is None or camera_arg.lower() == "random":
        return random.choice(FAKE_CAMERAS)
    # User typed e.g. "Nokia 3310" — find it or fall back to random
    needle = camera_arg.lower()
    for make, model, software in FAKE_CAMERAS:
        if needle in f"{make} {model}".lower():
            return make, model, software
    return random.choice(FAKE_CAMERAS)


def _pick_gps(
    preset: str | None,
    custom: tuple[float, float] | None,
    jitter: bool = True,
) -> tuple[float, float]:
    if custom:
        return custom
    if preset == "random":
        return (round(random.uniform(-80, 80), 4),
                round(random.uniform(-179, 179), 4))
    coords = GPS_PRESETS.get(preset or "pacific", GPS_PRESETS["pacific"])
    if jitter:
        lat = coords[0] + random.uniform(-0.08, 0.08)
        lon = coords[1] + random.uniform(-0.08, 0.08)
        return (round(lat, 4), round(lon, 4))
    return coords


# ─── Public API ────────────────────────────────────────────────────────────────

def spoof_jpeg(
    input_path: str,
    output_path: str,
    *,
    gps_preset: str = "pacific",
    gps_custom: tuple[float, float] | None = None,
    camera: str | None = "random",
    fake_datetime_mode: str = "random",
    keep_copyright: bool = False,
    copyright_text: str = "All rights reserved",
) -> dict:
    """
    Inject fake EXIF into a JPEG file and write to output_path.
    Returns a dict describing what was injected.
    """
    make, model, software = _pick_camera(camera)
    lat, lon = _pick_gps(gps_preset, gps_custom)
    dt_str = _fake_timestamp(fake_datetime_mode)

    zeroth_ifd = {
        piexif.ImageIFD.Make:           make.encode(),
        piexif.ImageIFD.Model:          model.encode(),
        piexif.ImageIFD.Software:       software.encode(),
        piexif.ImageIFD.DateTime:       dt_str.encode(),
        piexif.ImageIFD.XResolution:    (72, 1),
        piexif.ImageIFD.YResolution:    (72, 1),
        piexif.ImageIFD.ResolutionUnit: 2,
        piexif.ImageIFD.Orientation:    1,
    }
    if keep_copyright:
        zeroth_ifd[piexif.ImageIFD.Copyright] = copyright_text.encode()

    exif_ifd = {
        piexif.ExifIFD.DateTimeOriginal:  dt_str.encode(),
        piexif.ExifIFD.DateTimeDigitized: dt_str.encode(),
        piexif.ExifIFD.ColorSpace:        1,
        piexif.ExifIFD.FlashpixVersion:   b"0100",
        # Plausible but fake exposure data
        piexif.ExifIFD.ExposureTime:      (1, random.choice([30, 60, 100, 125, 250, 500])),
        piexif.ExifIFD.FNumber:           (random.choice([18, 20, 25, 28, 35, 40]), 10),
        piexif.ExifIFD.ISOSpeedRatings:   random.choice([100, 200, 400, 800]),
        piexif.ExifIFD.Flash:             0,
    }

    exif_bytes = piexif.dump({
        "0th":  zeroth_ifd,
        "Exif": exif_ifd,
        "GPS":  _build_gps_ifd(lat, lon),
    })

    img = Image.open(input_path).convert("RGB")
    img.save(output_path, "JPEG", exif=exif_bytes, quality=95)

    return {
        "format":   "JPEG",
        "camera":   f"{make} {model}",
        "software": software,
        "gps":      {"lat": lat, "lon": lon},
        "datetime": dt_str,
        "copyright_kept": keep_copyright,
        "output":   output_path,
    }


def spoof_png(
    input_path: str,
    output_path: str,
    *,
    camera: str | None = "random",
    fake_datetime_mode: str = "random",
    keep_copyright: bool = False,
    copyright_text: str = "All rights reserved",
) -> dict:
    """
    Inject fake text-chunk metadata into a PNG and write to output_path.
    Note: standard PNG has no GPS chunk — only JPEG gets fake GPS.
    """
    make, model, software = _pick_camera(camera)
    dt_str = _fake_timestamp(fake_datetime_mode)

    try:
        dt_obj  = datetime.strptime(dt_str, "%Y:%m:%d %H:%M:%S")
        png_dt  = dt_obj.strftime("%a %b %d %H:%M:%S %Y")
        iso_dt  = dt_obj.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    except ValueError:
        png_dt = iso_dt = dt_str

    pnginfo = PngImagePlugin.PngInfo()
    pnginfo.add_text("Software",       software)
    pnginfo.add_text("Author",         make)
    pnginfo.add_text("Comment",        f"Created with {software}")
    pnginfo.add_text("Creation Time",  png_dt)
    pnginfo.add_text("date:create",    iso_dt)
    pnginfo.add_text("date:modify",    iso_dt)
    if keep_copyright:
        pnginfo.add_text("Copyright", copyright_text)

    img = Image.open(input_path)
    img.save(output_path, "PNG", pnginfo=pnginfo)

    return {
        "format":   "PNG",
        "camera":   f"{make} {model}",
        "software": software,
        "gps":      None,   # PNG text-chunk GPS not supported
        "datetime": dt_str,
        "copyright_kept": keep_copyright,
        "output":   output_path,
    }


def spoof(
    input_path: str,
    output_path: str | None = None,
    *,
    profile: str | None = None,
    **kwargs,
) -> dict:
    """
    Auto-detect format, optionally apply a named profile, and spoof metadata.
    output_path defaults to <stem>_spoofed<ext> beside the original.

    Profiles: ghost | troll | artist
    """
    p   = Path(input_path)
    out = output_path or str(p.parent / f"{p.stem}_spoofed{p.suffix}")
    ext = p.suffix.lower()

    if not p.exists():
        raise FileNotFoundError(f"Input not found: {input_path}")

    # Merge profile defaults (kwargs win over profile)
    if profile:
        if profile not in PROFILES:
            raise ValueError(f"Unknown profile '{profile}'. Choose: {', '.join(PROFILES)}")
        merged = {**PROFILES[profile], **kwargs}
        merged.pop("description", None)
    else:
        merged = kwargs

    if ext in (".jpg", ".jpeg"):
        return spoof_jpeg(input_path, out, **merged)
    elif ext == ".png":
        # PNG doesn't use gps_preset/gps_custom — silently drop them
        png_kwargs = {k: v for k, v in merged.items()
                      if k not in ("gps_preset", "gps_custom")}
        return spoof_png(input_path, out, **png_kwargs)
    else:
        raise ValueError(f"Unsupported format: {ext!r}. Supported: .jpg, .jpeg, .png")


# ─── CLI ───────────────────────────────────────────────────────────────────────

def _build_cli() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dotscramble-spoof",
        description="DotScramble Metadata Spoofer — inject plausible fake metadata",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
profiles:
  ghost    Nokia 3310, Antarctica GPS, year 2000  (maximum obfuscation)
  troll    Random vintage camera, random ocean, recent-ish date
  artist   Fake location+device, preserve copyright  (for photographers)

examples:
  dotscramble-spoof photo.jpg --profile ghost
  dotscramble-spoof photo.jpg --gps-preset pacific --camera random
  dotscramble-spoof photo.jpg --gps-custom 23.4 -54.2 --keep-copyright
  dotscramble-spoof photo.jpg --dry-run
  dotscramble-spoof photo.png --profile troll -o output.png
        """,
    )
    p.add_argument("input", nargs="?", help="Input image (JPEG or PNG)")
    p.add_argument("-o", "--output", help="Output path (default: <stem>_spoofed<ext>)")
    p.add_argument("--profile",      choices=list(PROFILES), help="Use a named profile")
    p.add_argument("--gps-preset",   choices=list(GPS_PRESETS) + ["random"],
                   default="pacific", help="GPS location preset")
    p.add_argument("--gps-custom",   nargs=2, type=float, metavar=("LAT", "LON"),
                   help="Custom GPS coordinates (overrides --gps-preset)")
    p.add_argument("--camera",       default="random",
                   help='Camera to fake, e.g. "Nokia 3310" or "random"')
    p.add_argument("--datetime-mode", dest="fake_datetime_mode",
                   choices=["random", "recent", "epoch"], default="random",
                   help="How to generate the fake timestamp")
    p.add_argument("--keep-copyright", action="store_true",
                   help="Preserve copyright field (artist mode)")
    p.add_argument("--copyright-text", default="All rights reserved",
                   help="Copyright text to embed when --keep-copyright is set")
    p.add_argument("--list-cameras", action="store_true",
                   help="Print all available fake cameras and exit")
    p.add_argument("--list-gps",     action="store_true",
                   help="Print all GPS presets and exit")
    p.add_argument("--dry-run",      action="store_true",
                   help="Show what WOULD be injected without writing any file")
    p.add_argument("--json",         action="store_true",
                   help="Output result as JSON")
    return p


def main() -> None:
    parser = _build_cli()
    args   = parser.parse_args()

    if args.list_cameras:
        print("\nAvailable fake cameras:")
        for make, model, _ in FAKE_CAMERAS:
            print(f"  {make} {model}")
        sys.exit(0)

    if args.list_gps:
        print("\nGPS presets:")
        for name, (lat, lon) in GPS_PRESETS.items():
            print(f"  {name:<12} {lat:>9.4f}, {lon:>10.4f}")
        sys.exit(0)

    kwargs = dict(
        gps_preset=args.gps_preset,
        gps_custom=tuple(args.gps_custom) if args.gps_custom else None,
        camera=args.camera,
        fake_datetime_mode=args.fake_datetime_mode,
        keep_copyright=args.keep_copyright,
        copyright_text=args.copyright_text,
    )

    if args.dry_run:
        # Simulate without saving
        ext = Path(args.input).suffix.lower()
        make, model, software = _pick_camera(args.camera if not args.profile
                                             else PROFILES[args.profile].get("camera", args.camera))
        gps_preset_ = (PROFILES[args.profile].get("gps_preset", args.gps_preset)
                       if args.profile else args.gps_preset)
        lat, lon = _pick_gps(gps_preset_,
                             tuple(args.gps_custom) if args.gps_custom else None)
        dt_mode = (PROFILES[args.profile].get("fake_datetime_mode", args.fake_datetime_mode)
                   if args.profile else args.fake_datetime_mode)
        dt_str = _fake_timestamp(dt_mode)
        result = {
            "dry_run":  True,
            "format":   ext.lstrip(".").upper(),
            "camera":   f"{make} {model}",
            "software": software,
            "gps":      {"lat": lat, "lon": lon} if ext in (".jpg", ".jpeg") else None,
            "datetime": dt_str,
        }
    else:
        try:
            result = spoof(args.input, args.output, profile=args.profile, **kwargs)
        except (FileNotFoundError, ValueError) as e:
            print(f"[!] {e}", file=sys.stderr)
            sys.exit(1)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print("\n✔ DotScramble — Metadata Spoofed")
        print(f"  Camera   : {result['camera']}")
        print(f"  Software : {result['software']}")
        print(f"  DateTime : {result['datetime']}")
        if result.get("gps"):
            print(f"  GPS      : {result['gps']['lat']}, {result['gps']['lon']}")
        else:
            print(f"  GPS      : N/A (PNG format)")
        if not result.get("dry_run"):
            print(f"  Output   : {result['output']}")
        else:
            print(f"  [dry-run, no file written]")


if __name__ == "__main__":
    main()


# ─── Per-field helpers (used by MetadataCustomizerDialog) ─────────────────────

def read_exif_fields(image_path: str) -> dict:
    """
    Read current EXIF fields and return a structured dict for pre-filling the dialog.
    """
    result = {k: None for k in
              ("gps", "make", "model", "software", "datetime", "copyright", "exposure")}
    try:
        exif_dict = piexif.load(image_path)
    except Exception:
        return result

    zeroth = exif_dict.get("0th", {})
    exif   = exif_dict.get("Exif", {})
    gps    = exif_dict.get("GPS", {})

    def _decode(d, tag) -> str | None:
        v = d.get(tag)
        if isinstance(v, bytes):
            return v.decode(errors="ignore").strip("\x00")
        return str(v) if v is not None else None

    def _rational(tup) -> float | None:
        if isinstance(tup, (tuple, list)) and len(tup) == 2 and tup[1]:
            return tup[0] / tup[1]
        return None

    def _dms_to_decimal(dms_tuple, ref: bytes) -> float | None:
        if not dms_tuple or len(dms_tuple) < 3:
            return None
        try:
            d = _rational(dms_tuple[0]) or 0
            m = _rational(dms_tuple[1]) or 0
            s = _rational(dms_tuple[2]) or 0
            val = d + m / 60 + s / 3600
            if ref in (b"S", b"W"):
                val = -val
            return round(val, 6)
        except Exception:
            return None

    result["make"]      = _decode(zeroth, piexif.ImageIFD.Make)
    result["model"]     = _decode(zeroth, piexif.ImageIFD.Model)
    result["software"]  = _decode(zeroth, piexif.ImageIFD.Software)
    result["datetime"]  = _decode(zeroth, piexif.ImageIFD.DateTime)
    result["copyright"] = _decode(zeroth, piexif.ImageIFD.Copyright)

    lat = _dms_to_decimal(
        gps.get(piexif.GPSIFD.GPSLatitude),
        gps.get(piexif.GPSIFD.GPSLatitudeRef, b"N"),
    )
    lon = _dms_to_decimal(
        gps.get(piexif.GPSIFD.GPSLongitude),
        gps.get(piexif.GPSIFD.GPSLongitudeRef, b"E"),
    )
    if lat is not None and lon is not None:
        result["gps"] = {"lat": lat, "lon": lon}

    et  = _rational(exif.get(piexif.ExifIFD.ExposureTime))
    fn  = _rational(exif.get(piexif.ExifIFD.FNumber))
    iso = exif.get(piexif.ExifIFD.ISOSpeedRatings)
    if any(x is not None for x in (et, fn, iso)):
        result["exposure"] = {
            "shutter": f"1/{int(1/et)}" if et and et > 0 else "?",
            "fnumber": f"f/{fn:.1f}"    if fn else "?",
            "iso":     iso or "?",
        }
    return result


def spoof_custom(
    input_path: str,
    output_path: str | None = None,
    *,
    field_actions: dict,
) -> dict:
    """
    Apply per-field EXIF actions to a JPEG or PNG.

    field_actions keys: gps, make, model, software, datetime, copyright, exposure
    Values: "keep" | "strip" | "spoof" | {"value": str}  (gps uses {"lat":..,"lon":..})
    """
    p   = Path(input_path)
    out = output_path or str(p.parent / f"{p.stem}_custom{p.suffix}")
    ext = p.suffix.lower()

    if not p.exists():
        raise FileNotFoundError(f"Input not found: {input_path}")

    current = read_exif_fields(input_path)
    make, model, software = _pick_camera("random")

    def _resolve_text(key: str, fake_fn) -> str | None:
        action = field_actions.get(key, "keep")
        if action == "strip":   return None
        if action == "keep":    return current.get(key)
        if action == "spoof":   return fake_fn()
        if isinstance(action, dict): return action.get("value", "")
        return current.get(key)

    r_make      = _resolve_text("make",      lambda: make)
    r_model     = _resolve_text("model",     lambda: model)
    r_software  = _resolve_text("software",  lambda: software)
    r_datetime  = _resolve_text("datetime",  lambda: _fake_timestamp("random"))
    r_copyright = _resolve_text("copyright", lambda: "All rights reserved")

    gps_action = field_actions.get("gps", "keep")
    if gps_action == "strip":        r_gps = None
    elif gps_action == "keep":       r_gps = current.get("gps")
    elif gps_action == "spoof":      lat, lon = _pick_gps("pacific", None); r_gps = {"lat": lat, "lon": lon}
    elif isinstance(gps_action, dict): r_gps = gps_action
    else:                            r_gps = current.get("gps")

    exp_action = field_actions.get("exposure", "keep")
    if exp_action == "strip":
        r_exp = None
    elif exp_action == "spoof":
        r_exp = {
            "shutter": (1, random.choice([30, 60, 100, 125, 250, 500])),
            "fnumber": (random.choice([18, 20, 25, 28, 35, 40]), 10),
            "iso":     random.choice([100, 200, 400, 800]),
        }
    else:
        r_exp = None   # keep → already in the original bytes

    injected: dict = {}

    if ext in (".jpg", ".jpeg"):
        zeroth: dict = {
            piexif.ImageIFD.XResolution:    (72, 1),
            piexif.ImageIFD.YResolution:    (72, 1),
            piexif.ImageIFD.ResolutionUnit: 2,
            piexif.ImageIFD.Orientation:    1,
        }
        exif_ifd: dict = {
            piexif.ExifIFD.ColorSpace:      1,
            piexif.ExifIFD.FlashpixVersion: b"0100",
        }
        gps_ifd: dict = {}

        if r_make:      zeroth[piexif.ImageIFD.Make]      = r_make.encode()
        if r_model:     zeroth[piexif.ImageIFD.Model]     = r_model.encode()
        if r_software:  zeroth[piexif.ImageIFD.Software]  = r_software.encode()
        if r_copyright: zeroth[piexif.ImageIFD.Copyright] = r_copyright.encode()
        if r_datetime:
            zeroth[piexif.ImageIFD.DateTime]           = r_datetime.encode()
            exif_ifd[piexif.ExifIFD.DateTimeOriginal]  = r_datetime.encode()
            exif_ifd[piexif.ExifIFD.DateTimeDigitized] = r_datetime.encode()
        if r_exp:
            exif_ifd[piexif.ExifIFD.ExposureTime]    = r_exp["shutter"]
            exif_ifd[piexif.ExifIFD.FNumber]         = r_exp["fnumber"]
            exif_ifd[piexif.ExifIFD.ISOSpeedRatings] = r_exp["iso"]
            exif_ifd[piexif.ExifIFD.Flash]           = 0
        if r_gps:
            gps_ifd = _build_gps_ifd(r_gps["lat"], r_gps["lon"])

        exif_bytes = piexif.dump({"0th": zeroth, "Exif": exif_ifd, "GPS": gps_ifd})
        img = Image.open(input_path).convert("RGB")
        img.save(out, "JPEG", exif=exif_bytes, quality=95)
        injected = {
            "camera":    f"{r_make or '—'} {r_model or '—'}".strip(),
            "software":  r_software,
            "gps":       r_gps,
            "datetime":  r_datetime,
            "copyright": r_copyright,
        }

    elif ext == ".png":
        pnginfo = PngImagePlugin.PngInfo()
        if r_software:  pnginfo.add_text("Software",  r_software)
        if r_make:      pnginfo.add_text("Author",    r_make)
        if r_copyright: pnginfo.add_text("Copyright", r_copyright)
        if r_datetime:
            try:
                from datetime import datetime as _dt
                dt_obj = _dt.strptime(r_datetime, "%Y:%m:%d %H:%M:%S")
                pnginfo.add_text("Creation Time", dt_obj.strftime("%a %b %d %H:%M:%S %Y"))
                pnginfo.add_text("date:create",   dt_obj.strftime("%Y-%m-%dT%H:%M:%S+00:00"))
                pnginfo.add_text("date:modify",   dt_obj.strftime("%Y-%m-%dT%H:%M:%S+00:00"))
            except Exception:
                pnginfo.add_text("Creation Time", r_datetime)
        img = Image.open(input_path)
        img.save(out, "PNG", pnginfo=pnginfo)
        injected = {"camera": r_make, "software": r_software,
                    "gps": None, "datetime": r_datetime}
    else:
        raise ValueError(f"Unsupported format: {ext!r}")

    injected["output"] = out
    injected["mode"]   = "custom"
    return injected
