"""
The image picker opens where the user was last time, with that photo selected, and lists
recently opened photos (from any folder) under Quick Access → Recent.
"""
import os

import pytest
from PIL import Image

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def photos(tmp_path):
    trip, work = tmp_path / "trip", tmp_path / "work"
    trip.mkdir(), work.mkdir()
    paths = {}
    for folder, name in ((trip, "beach.jpg"), (trip, "hotel.png"), (work, "desk.jpg")):
        Image.new("RGB", (40, 30), "teal").save(folder / name)
        paths[name] = str(folder / name)
    return paths


def _settle(app, ms=200):
    from PySide6.QtCore import QEventLoop, QTimer
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def test_opens_in_the_last_folder_with_the_last_photo_selected(app, photos):
    from core.image_picker import ImagePicker
    last = photos["hotel.png"]
    picker = ImagePicker(start_dir=os.path.dirname(last), select=last)
    _settle(app)
    assert picker._cwd == os.path.dirname(last)
    assert picker._selected == last
    assert [t.path for t in picker._tiles if t._selected] == [last]
    picker.deleteLater()


def test_recent_lists_photos_from_every_folder_newest_first(app, photos):
    from core.image_picker import RECENT, ImagePicker
    recent = [photos["desk.jpg"], photos["beach.jpg"], "/gone/deleted.jpg"]
    picker = ImagePicker(recent=recent)
    picker._navigate(RECENT)
    assert [t.path for t in picker._tiles] == recent[:2]      # a photo deleted since is left out
    assert picker.path_lbl.text() == "Recent"
    picker.deleteLater()


def test_no_recent_place_without_history_and_a_missing_folder_falls_back_home(app):
    from pathlib import Path
    from core.image_picker import ImagePicker
    from core.image_picker import SidebarItem
    picker = ImagePicker(start_dir="/no/such/folder", recent=[])
    assert picker._cwd == str(Path.home())
    assert "recent:" not in [item.path for item in picker.findChildren(SidebarItem)]
    picker.deleteLater()
