"""
Saving with metadata (core/metadata_writer). Each test pins down a bug that 1.5.x shipped:
the original's embedded thumbnail (the unedited photo, faces included) written back into
the saved file, a second lossy JPEG encode, a double rotation, Custom "keep" keeping
nothing, and Decoy writing the real data back for WebP / TIFF.
"""
import io
import os
from datetime import date

import cv2
import numpy as np
import piexif
import pytest
from PIL import Image, ImageOps

from core import metadata_writer as mw
from core.daily_quota import DailyQuota

GPS = (30.044444, 31.235556)


@pytest.fixture(scope="module")
def phone_photo(tmp_path_factory):
    """A portrait photo stored landscape with Orientation=6, like a phone writes it, with GPS,
    camera, exposure, copyright and a sharp embedded thumbnail."""
    folder = tmp_path_factory.mktemp("meta")
    rng = np.random.default_rng(7)
    portrait = Image.fromarray(rng.integers(0, 255, (600, 400, 3), dtype=np.uint8))   # 400×600 upright
    stored = portrait.rotate(90, expand=True)                                           # 600×400 on disk
    thumb = io.BytesIO()
    stored.resize((160, 107)).save(thumb, "JPEG")
    exif = {
        "0th": {piexif.ImageIFD.Make: b"Samsung", piexif.ImageIFD.Model: b"SM-S918B",
                piexif.ImageIFD.Orientation: 6, piexif.ImageIFD.Copyright: b"(c) Kareem"},
        "Exif": {piexif.ExifIFD.DateTimeOriginal: b"2026:10:24 18:42:00", piexif.ExifIFD.ExposureTime: (1, 120),
                 piexif.ExifIFD.FNumber: (18, 10), piexif.ExifIFD.ISOSpeedRatings: 200},
        "GPS": {piexif.GPSIFD.GPSLatitudeRef: b"N", piexif.GPSIFD.GPSLatitude: ((30, 1), (2, 1), (4000, 100)),
                piexif.GPSIFD.GPSLongitudeRef: b"E", piexif.GPSIFD.GPSLongitude: ((31, 1), (14, 1), (800, 100))},
        "1st": {piexif.ImageIFD.JPEGInterchangeFormat: 0, piexif.ImageIFD.JPEGInterchangeFormatLength: 0},
        "thumbnail": thumb.getvalue(),
    }
    path = folder / "phone.jpg"
    stored.save(path, "JPEG", quality=95, exif=piexif.dump(exif))
    image = cv2.imread(str(path))   # OpenCV applies the orientation: 400 wide, 600 tall
    return {"path": str(path), "image": image, "exif": mw.load_exif(str(path)), "folder": folder}


def save(photo, mode, ext, **kw):
    image = photo["image"]
    plan = mw.make_plan(photo["exif"], mode, ext=ext, size=(image.shape[1], image.shape[0]), **kw)
    out = str(photo["folder"] / f"out-{mode}-{kw.get('profile', '')}{ext}")
    mw.write_image(image, out, plan)
    return out, plan, mw.load_exif(out)


def test_the_fixture_is_a_real_phone_photo(phone_photo):
    fields = mw.fields_of(phone_photo["exif"])
    assert mw.gps_of(phone_photo["exif"]) == pytest.approx(GPS, abs=1e-5)
    assert fields["make"] == "Samsung" and fields["datetime"] == "2026-10-24 18:42:00"
    assert mw.has_thumbnail(phone_photo["exif"])
    assert phone_photo["image"].shape[:2] == (600, 400)


# ── the thumbnail, orientation and quality bugs ─────────────────────────────

@pytest.mark.parametrize("mode", ["keep", "location", "strip", "spoof", "custom"])
@pytest.mark.parametrize("ext", [".jpg", ".png", ".webp", ".tiff"])
def test_never_writes_the_original_thumbnail(phone_photo, mode, ext):
    out, plan, saved = save(phone_photo, mode, ext, profile="troll" if mode == "spoof" else None)
    assert not mw.has_thumbnail(saved)
    assert mw.verify(out, plan, phone_photo["exif"]) == []


@pytest.mark.parametrize("ext", [".jpg", ".png", ".webp", ".tiff"])
def test_saved_photo_is_shown_upright(phone_photo, ext):
    out, _plan, saved = save(phone_photo, "keep", ext)
    assert (saved["0th"].get(piexif.ImageIFD.Orientation) or 1) == 1
    assert ImageOps.exif_transpose(Image.open(out)).size == (400, 600)


def test_jpeg_is_encoded_once(phone_photo):
    out, _plan, _saved = save(phone_photo, "keep", ".jpg")
    ok, direct = cv2.imencode(".jpg", phone_photo["image"], [cv2.IMWRITE_JPEG_QUALITY, mw.JPEG_QUALITY])
    assert Image.open(out).quantization == Image.open(io.BytesIO(direct.tobytes())).quantization


# ── what each mode keeps ─────────────────────────────────────────────────────

def test_keep_keeps_everything_else(phone_photo):
    _out, _plan, saved = save(phone_photo, "keep", ".jpg")
    assert mw.fields_of(saved) == mw.fields_of(phone_photo["exif"])


def test_location_removes_only_gps(phone_photo):
    _out, plan, saved = save(phone_photo, "location", ".jpg")
    before, after = mw.fields_of(phone_photo["exif"]), mw.fields_of(saved)
    assert after["gps"] is None
    assert {k: v for k, v in after.items() if k != "gps"} == {k: v for k, v in before.items() if k != "gps"}
    assert [c.action for c in plan.changes if c.key == "gps"] == ["remove"]


@pytest.mark.parametrize("ext", [".jpg", ".png", ".webp", ".tiff"])
def test_strip_leaves_nothing(phone_photo, ext):
    _out, plan, saved = save(phone_photo, "strip", ext)
    assert plan.exif is None
    assert not any(mw.fields_of(saved).values())


@pytest.mark.parametrize("ext", [".jpg", ".png", ".webp", ".tiff"])
def test_decoy_never_writes_the_real_data(phone_photo, ext):
    _out, _plan, saved = save(phone_photo, "spoof", ext, profile="troll")
    fields = mw.fields_of(saved)
    lat, lon = mw.gps_of(saved)
    assert abs(lat - GPS[0]) > 1 or abs(lon - GPS[1]) > 1
    assert fields["make"] != "Samsung" and fields["model"] != "SM-S918B"
    assert fields["copyright"] is None


def test_artist_decoy_keeps_the_real_copyright(phone_photo):
    _out, _plan, saved = save(phone_photo, "spoof", ".jpg", profile="artist")
    assert mw.fields_of(saved)["copyright"] == "(c) Kareem"
    assert mw.fields_of(saved)["make"] != "Samsung"


def test_custom_keep_really_keeps(phone_photo):
    actions = {"gps": "strip", "make": "keep", "model": {"value": "Pixel 9"},
               "datetime": "keep", "exposure": "keep", "copyright": "strip"}
    _out, plan, saved = save(phone_photo, "custom", ".jpg", field_actions=actions)
    fields = mw.fields_of(saved)
    assert fields["gps"] is None
    assert fields["make"] == "Samsung"
    assert fields["model"] == "Pixel 9"
    assert fields["datetime"] == "2026-10-24 18:42:00"
    assert fields["exposure"] == mw.fields_of(phone_photo["exif"])["exposure"]
    assert fields["copyright"] is None
    actions_by_key = {c.key: c.action for c in plan.changes}
    assert actions_by_key == {"gps": "remove", "make": "keep", "model": "replace", "datetime": "keep",
                              "copyright": "remove", "exposure": "keep", "thumbnail": "remove"}


def test_custom_custom_gps(phone_photo):
    _out, _plan, saved = save(phone_photo, "custom", ".jpg", field_actions={"gps": {"lat": 48.8566, "lon": 2.3522}})
    assert mw.gps_of(saved) == pytest.approx((48.8566, 2.3522), abs=1e-4)


@pytest.mark.parametrize("mode", ["keep", "spoof"])
def test_bmp_cannot_carry_metadata_and_says_so(phone_photo, mode):
    out, plan, _saved = save(phone_photo, mode, ".bmp", profile="ghost" if mode == "spoof" else None)
    assert plan.supported is False and plan.exif is None
    assert mw.load_exif(out) is None
    assert all(c.action == "remove" for c in plan.changes)


def test_photo_without_metadata_has_no_changes(phone_photo, tmp_path):
    path = tmp_path / "plain.png"
    cv2.imwrite(str(path), phone_photo["image"])
    assert mw.load_exif(str(path)) is None
    assert mw.make_plan(None, "keep", ext=".jpg").changes == []


# ── the check after saving ───────────────────────────────────────────────────

def test_verify_catches_a_leftover_thumbnail(phone_photo):
    out, plan, _saved = save(phone_photo, "keep", ".jpg")
    with_thumb = dict(phone_photo["exif"])
    piexif.insert(piexif.dump(with_thumb), out)          # put the original EXIF, thumbnail and all, back
    assert "thumbnail" in mw.verify(out, plan, phone_photo["exif"])
    assert "orientation" in mw.verify(out, plan, phone_photo["exif"])


def test_verify_catches_gps_that_should_be_gone(phone_photo):
    out, _keep_plan, _saved = save(phone_photo, "keep", ".jpg")
    location_plan = mw.make_plan(phone_photo["exif"], "location", ext=".jpg")
    assert "gps_left" in mw.verify(out, location_plan, phone_photo["exif"])


def test_verify_catches_metadata_after_strip(phone_photo):
    out, _keep_plan, _saved = save(phone_photo, "keep", ".jpg")
    strip_plan = mw.make_plan(phone_photo["exif"], "strip", ext=".jpg")
    assert "metadata_left" in mw.verify(out, strip_plan, phone_photo["exif"])


def test_write_leaves_no_temporary_files(phone_photo):
    before = set(os.listdir(phone_photo["folder"]))
    save(phone_photo, "location", ".png")
    leftovers = [n for n in set(os.listdir(phone_photo["folder"])) - before if n.startswith(".dotscramble-")]
    assert leftovers == []


def test_saved_files_get_normal_permissions(phone_photo, tmp_path):
    umask = os.umask(0)
    os.umask(umask)
    out = tmp_path / "new.jpg"
    plan = mw.make_plan(phone_photo["exif"], "strip", ext=".jpg")
    mw.write_image(phone_photo["image"], str(out), plan)
    assert out.stat().st_mode & 0o777 == 0o666 & ~umask          # not mkstemp's private 0600
    os.chmod(out, 0o640)
    mw.write_image(phone_photo["image"], str(out), plan)          # replacing keeps the file's own mode
    assert out.stat().st_mode & 0o777 == 0o640


def test_tags_piexif_cannot_encode_are_dropped_not_fatal():
    exif = {"0th": {piexif.ImageIFD.Make: b"Samsung", piexif.ImageIFD.Orientation: "not a number"},
            "Exif": {}, "GPS": {}, "Interop": {}}
    data = piexif.load(mw._dump(exif))
    assert data["0th"][piexif.ImageIFD.Make] == b"Samsung"
    assert piexif.ImageIFD.Orientation not in data["0th"]


# ── the Free tier's daily allowance ──────────────────────────────────────────

class FakeDB:
    def __init__(self):
        self.values = {}

    def get_setting(self, key, default=None):
        return self.values.get(key, default)

    def save_setting(self, key, value, setting_type="general"):
        self.values[key] = value
        return True


def test_daily_quota_counts_down_and_resets_the_next_day():
    db, day = FakeDB(), [date(2026, 10, 28)]
    quota = DailyQuota(db, limit=4, today=lambda: day[0])
    assert quota.remaining() == 4
    assert [quota.consume() for _ in range(5)] == [3, 2, 1, 0, 0]
    assert quota.remaining() == 0
    day[0] = date(2026, 10, 29)
    assert quota.remaining() == 4


def test_daily_quota_survives_a_broken_setting():
    db = FakeDB()
    db.values["free_location_removals"] = "not json"
    assert DailyQuota(db, limit=4).remaining() == 4


# ── the report shows real values, in every language ─────────────────────────

@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("lang", ["en", "ar", "fa", "es", "ru", "de", "tr"])
def test_report_has_text_for_every_mode(app, phone_photo, lang):
    from PySide6.QtWidgets import QLabel, QPushButton
    from gui.metadata_report import MetadataReportDialog
    from src.managers.localization_manager import get_locale_manager

    get_locale_manager().set_language(lang)
    try:
        plans = [mw.make_plan(phone_photo["exif"], m, ext=".jpg", profile="ghost") for m in mw.MODES]
        plans.append(mw.make_plan(phone_photo["exif"], "keep", ext=".bmp"))
        for plan in plans:
            dlg = MetadataReportDialog(None, plan=plan, filename="photo.jpg")
            texts = [w.text() for w in dlg.findChildren(QLabel) + dlg.findChildren(QPushButton)]
            assert not [t for t in texts if t.startswith(("metadata.", "ui."))], texts
            if plan.supported and plan.mode == "keep":
                assert "Samsung" in " ".join(texts) and "30.04444" in " ".join(texts)
            dlg.deleteLater()
    finally:
        get_locale_manager().set_language("en")


# ── Phase 2: what lives outside EXIF, metadata-only cleaning, Blend in ──────

XMP_WITH_FACES = (b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
                  b'<rdf:Description xmlns:mwg-rs="http://www.metadataworkinggroup.com/schemas/regions/">'
                  b'<mwg-rs:Regions>Ahmed</mwg-rs:Regions></rdf:Description></rdf:RDF></x:xmpmeta>')


def _segment(marker: int, payload: bytes) -> bytes:
    return bytes([0xFF, marker]) + (len(payload) + 2).to_bytes(2, "big") + payload


@pytest.fixture(scope="module")
def rich_photo(phone_photo):
    """The phone photo plus everything that lives outside the usual EXIF fields: serial numbers,
    a MakerNote, the owner's name, XMP with face regions, IPTC, a comment, an sRGB profile and a
    second image after the end of the first (like an MPF depth map)."""
    from PIL import ImageCms
    icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    exif = piexif.load(phone_photo["path"])
    exif["Exif"][piexif.ExifIFD.BodySerialNumber] = b"R5CW30ABCDE"
    exif["Exif"][piexif.ExifIFD.MakerNote] = b"SAMSUNG\x00secret"
    exif["0th"][piexif.ImageIFD.Artist] = b"Kareem Ehab"
    buf = io.BytesIO()
    Image.open(phone_photo["path"]).save(buf, "JPEG", quality=95, exif=piexif.dump(exif), icc_profile=icc, xmp=XMP_WITH_FACES)
    data = buf.getvalue()
    second = io.BytesIO()
    Image.new("RGB", (32, 32), "red").save(second, "JPEG")
    rich = (data[:2] + _segment(0xED, b"Photoshop 3.0\x008BIM\x04\x04\x00\x00\x00\x00\x00\x05\x1c\x02\x78\x00\x01A")
            + _segment(0xFE, b"taken at home") + data[2:] + second.getvalue())
    path = phone_photo["folder"] / "rich.jpg"
    path.write_bytes(rich)
    png = phone_photo["folder"] / "ai.png"
    from PIL import PngImagePlugin
    info = PngImagePlugin.PngInfo()
    info.add_text("parameters", "a photo of my street, Steps: 20")
    Image.open(phone_photo["path"]).convert("RGB").save(png, pnginfo=info, icc_profile=icc)
    return {"path": str(path), "png": str(png), "icc": icc, "image": cv2.imread(str(path)),
            "exif": mw.load_exif(str(path)), "extras": mw.inspect_extras(str(path)), "folder": phone_photo["folder"]}


def test_finds_everything_outside_exif(rich_photo):
    extras = rich_photo["extras"]
    assert extras["xmp"] and extras["face_regions"] and extras["iptc"] and extras["extra_images"]
    assert extras["text"] == ["JPEG comment"]
    assert extras["icc"] == rich_photo["icc"]
    assert mw.inspect_extras(rich_photo["png"])["text"] == ["parameters"]
    assert "R5CW30ABCDE" in mw.fields_of(rich_photo["exif"])["fingerprint"]


@pytest.mark.parametrize("mode", ["keep", "location", "strip", "spoof"])
def test_saving_drops_everything_outside_exif_but_keeps_the_color_profile(rich_photo, mode):
    image = rich_photo["image"]
    plan = mw.make_plan(rich_photo["exif"], mode, ext=".jpg", profile="blend", extras=rich_photo["extras"],
                        size=(image.shape[1], image.shape[0]))
    out = str(rich_photo["folder"] / f"rich-{mode}.jpg")
    mw.write_image(image, out, plan)
    extras = mw.inspect_extras(out)
    assert not (extras["xmp"] or extras["iptc"] or extras["text"] or extras["extra_images"])
    assert extras["icc"] == rich_photo["icc"]
    assert mw.verify(out, plan, rich_photo["exif"]) == []
    keys = {c.key: c.action for c in plan.changes}
    assert {keys[k] for k in ("xmp", "iptc", "text", "extra_images")} == {"remove"} and keys["icc"] == "keep"


@pytest.mark.parametrize("mode,kept", [("keep", True), ("location", True), ("strip", False), ("spoof", False), ("custom", False)])
def test_device_ids_follow_the_mode(rich_photo, mode, kept):
    plan = mw.make_plan(rich_photo["exif"], mode, ext=".jpg", profile="troll", field_actions={})
    assert (mw.fields_of(plan.exif)["fingerprint"] is not None) is kept


def test_cleaning_a_jpeg_copies_the_image_data_byte_for_byte(rich_photo):
    plan = mw.make_plan(rich_photo["exif"], "location", ext=".jpg", extras=rich_photo["extras"], pixels_upright=False)
    out = str(rich_photo["folder"] / "rich_clean.jpg")
    mw.clean_file(rich_photo["path"], out, plan)
    original_scan = [raw for marker, raw in mw.jpeg_segments(open(rich_photo["path"], "rb").read())[0] if marker == 0xDA]
    cleaned_segments, trailer = mw.jpeg_segments(open(out, "rb").read())
    assert [raw for marker, raw in cleaned_segments if marker == 0xDA] == original_scan
    assert trailer == b""                                                 # the hidden second image is gone
    saved = mw.load_exif(out)
    assert mw.gps_of(saved) is None and mw.fields_of(saved)["make"] == "Samsung"
    assert saved["0th"][piexif.ImageIFD.Orientation] == 6                 # pixels untouched, so the tag stays
    assert mw.inspect_extras(out)["icc"] == rich_photo["icc"]
    assert mw.verify(out, plan, rich_photo["exif"]) == []


@pytest.mark.parametrize("ext", [".png", ".webp", ".tiff"])
def test_cleaning_other_formats_keeps_every_pixel(rich_photo, ext):
    source = str(rich_photo["folder"] / f"src{ext}")
    Image.open(rich_photo["png"]).save(source, **({"lossless": True} if ext == ".webp" else {}))
    plan = mw.make_plan(mw.load_exif(source), "strip", ext=ext, extras=mw.inspect_extras(source), pixels_upright=False)
    out = str(rich_photo["folder"] / f"src_clean{ext}")
    mw.clean_file(source, out, plan)
    assert np.array_equal(np.asarray(Image.open(source).convert("RGB")), np.asarray(Image.open(out).convert("RGB")))
    assert mw.inspect_extras(out)["text"] == []


def test_blend_in_looks_ordinary_but_is_not_real(rich_photo):
    import math
    real_lat, real_lon = mw.gps_of(rich_photo["exif"])
    for _ in range(30):
        exif = mw.make_plan(rich_photo["exif"], "spoof", ext=".jpg", profile="blend").exif
        fields = mw.fields_of(exif)
        assert fields["make"].lower() != "samsung"
        lat, lon = mw.gps_of(exif)
        km = math.hypot((lat - real_lat) * 111.32, (lon - real_lon) * 111.32 * math.cos(math.radians(real_lat)))
        assert 1.9 <= km <= 8.2
        from datetime import datetime, timedelta
        when = datetime.fromisoformat(fields["datetime"])
        shift = abs(when - datetime(2026, 10, 24, 18, 42))
        assert timedelta(days=1) <= shift <= timedelta(days=10, hours=6)
        assert when < datetime.now() - timedelta(minutes=30), "never the save time, never the future"
        assert fields["fingerprint"] is None
        assert piexif.GPSIFD.GPSAltitude not in exif["GPS"], "no made-up 0 m altitude"
    assert mw.gps_of(mw.make_plan(None, "spoof", ext=".jpg", profile="blend").exif) is None


def test_cleaner_never_overwrites_and_reports_what_it_did(rich_photo, tmp_path):
    from gui.metadata_cleaner import clean_one, clean_target
    src = tmp_path / "trip.jpg"
    src.write_bytes(open(rich_photo["path"], "rb").read())
    (tmp_path / "trip_clean.jpg").write_bytes(b"already here")
    assert clean_target(str(src)) == str(tmp_path / "trip_clean (2).jpg")
    status, target, removed = clean_one(str(src), "location")
    assert (status, removed) == ("done", True) and target.endswith("trip_clean (2).jpg")
    assert (tmp_path / "trip_clean.jpg").read_bytes() == b"already here"
    status, target, removed = clean_one(target, "location")          # already clean: nothing left to remove
    assert status == "nothing" and target is None
    plain = tmp_path / "plain.bmp"
    cv2.imwrite(str(plain), rich_photo["image"])
    assert clean_one(str(plain), "strip")[0] == "unsupported"


def test_batch_free_always_strips(rich_photo, tmp_path):
    from core.batch_processor import BatchProcessor
    out = str(tmp_path / "processed.jpg")
    BatchProcessor._save(rich_photo["image"], rich_photo["path"], out, {"is_pro": False, "metadata_mode": "keep"})
    assert mw.load_exif(out) is None
    BatchProcessor._save(rich_photo["image"], rich_photo["path"], out, {"is_pro": True, "metadata_mode": "location"})
    assert mw.gps_of(mw.load_exif(out)) is None and mw.fields_of(mw.load_exif(out))["make"] == "Samsung"


@pytest.mark.parametrize("lang", ["en", "ar", "fa", "es", "ru", "de", "tr"])
def test_inspector_and_cleaner_have_text_in_every_language(app, rich_photo, lang):
    from PySide6.QtWidgets import QLabel, QPushButton, QRadioButton
    from gui.metadata_cleaner import MetadataCleanerDialog
    from gui.metadata_inspector import MetadataInspectorDialog
    from gui.metadata_report import MetadataReportDialog
    from src.managers.localization_manager import get_locale_manager

    get_locale_manager().set_language(lang)
    try:
        dialogs = [MetadataInspectorDialog(None, exif=rich_photo["exif"], extras=rich_photo["extras"], filename="x.jpg"),
                   MetadataReportDialog(None, plan=mw.make_plan(rich_photo["exif"], "spoof", ext=".jpg", profile="blend",
                                                                extras=rich_photo["extras"]), filename="x.jpg"),
                   MetadataCleanerDialog(None, is_pro=False, quota=DailyQuota(FakeDB()))]
        for dlg in dialogs:
            texts = [w.text() for w in dlg.findChildren(QLabel) + dlg.findChildren(QPushButton) + dlg.findChildren(QRadioButton)]
            assert not [t for t in texts if t.startswith(("metadata.", "ui.", "batch."))], texts
            dlg.deleteLater()
    finally:
        get_locale_manager().set_language("en")


# ── "Save metadata only": the open photo, untouched, with new metadata ────────

@pytest.mark.parametrize("mode", ["location", "strip", "spoof"])
def test_saving_metadata_only_keeps_the_photo_and_shows_it_upright(phone_photo, mode):
    # what the main window does when nothing was edited: plan for the file as stored, then copy it
    plan = mw.make_plan(phone_photo["exif"], mode, ext=".jpg", profile="blend", pixels_upright=False)
    out = str(phone_photo["folder"] / f"only-{mode}.jpg")
    mw.clean_file(phone_photo["path"], out, plan)
    assert mw.verify(out, plan, phone_photo["exif"]) == []
    assert mw.gps_of(mw.load_exif(out)) != GPS
    with open(phone_photo["path"], "rb") as a, open(out, "rb") as b:
        assert mw.jpeg_segments(a.read())[0][-1] == mw.jpeg_segments(b.read())[0][-1]   # same image data
    assert cv2.imread(out).shape == phone_photo["image"].shape                          # still upright


def test_blend_never_dates_a_recent_photo_at_the_save_time():
    from datetime import datetime, timedelta
    just_taken = (datetime.now() - timedelta(hours=2)).strftime("%Y:%m:%d %H:%M:%S")
    for seed in range(200):
        import random
        shifted = datetime.strptime(mw._shifted(just_taken, random.Random(seed)), "%Y:%m:%d %H:%M:%S")
        assert shifted < datetime.now() - timedelta(minutes=30)
        assert timedelta(days=1) <= datetime.now() - timedelta(hours=2) - shifted <= timedelta(days=10, hours=6)


def test_blend_keeps_a_real_altitude_only_slightly_off():
    exif = {"GPS": {piexif.GPSIFD.GPSLatitudeRef: b"N", piexif.GPSIFD.GPSLatitude: ((30, 1), (2, 1), (4000, 100)),
                    piexif.GPSIFD.GPSLongitudeRef: b"E", piexif.GPSIFD.GPSLongitude: ((31, 1), (14, 1), (800, 100)),
                    piexif.GPSIFD.GPSAltitude: (745, 10), piexif.GPSIFD.GPSAltitudeRef: b"\x00"}}
    for _ in range(20):
        alt = mw.make_plan(exif, "spoof", ext=".jpg", profile="blend").exif["GPS"][piexif.GPSIFD.GPSAltitude]
        assert 59 <= alt[0] / alt[1] <= 90 and alt[0] / alt[1] != 74.5
