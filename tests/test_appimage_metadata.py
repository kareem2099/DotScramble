"""
What build.py puts into the AppImage for AppImageHub and AppImage tools: the AppStream
metainfo, the shared desktop entry, and the zsync update information.
"""
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import build
from version_info import VERSION

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def project_root(monkeypatch):
    monkeypatch.chdir(ROOT)  # build.py uses paths relative to the project root


def test_metainfo_lists_the_current_version_first():
    root = ET.fromstring(build.metainfo_xml(VERSION))
    assert root.findtext("id") == build.APPSTREAM_ID
    releases = [r.get("version") for r in root.find("releases")]
    assert releases[0] == VERSION
    assert len(releases) == len(set(releases)) <= 5


def test_metainfo_is_named_the_way_appimagehub_reads_it():
    assert build.METAINFO_NAME == f"{build.APPSTREAM_ID}.appdata.xml"
    assert build.METAINFO_TEMPLATE.is_file()


def test_metainfo_refuses_a_version_missing_from_the_changelog():
    with pytest.raises(ValueError, match="CHANGELOG"):
        build.metainfo_xml("99.0.0")


def test_releases_come_from_changelog_headings():
    found, block = build.appstream_releases("## [2.0.0] - 2027-01-02\n\n## [Unreleased]\n## [1.9.0] - 2026-12-01\n")
    assert found == [("2.0.0", "2027-01-02"), ("1.9.0", "2026-12-01")]
    assert '<release version="2.0.0" date="2027-01-02">' in block


def test_metainfo_launchable_and_screenshots_exist():
    root = ET.fromstring(build.metainfo_xml(VERSION))
    assert root.findtext("launchable") == "DotScramble.desktop"
    for image in root.iter("image"):
        name = image.text.rsplit("/", 1)[-1]
        assert (ROOT / "docs/screenshots" / name).is_file(), name


def test_icons_for_every_size_exist():
    for size in build.ICON_SIZES:
        assert (ROOT / f"assets/icons/png/dotscramble-{size}.png").is_file()
    assert (ROOT / "assets/icons/dotscramble.svg").is_file()


def test_desktop_entry_is_listed_once_in_menus():
    entry = build.desktop_entry("dotscramble")
    assert "Exec=dotscramble\n" in entry
    assert "Categories=Graphics;2DGraphics;RasterGraphics;Photography;\n" in entry
    assert "Utility" not in entry


@pytest.mark.skipif(not shutil.which("desktop-file-validate"), reason="desktop-file-utils not installed")
def test_desktop_entry_validates_without_hints(tmp_path):
    path = tmp_path / "DotScramble.desktop"
    path.write_text(build.desktop_entry("DotScramble"))
    result = subprocess.run(["desktop-file-validate", str(path)], capture_output=True, text=True)
    assert result.returncode == 0 and not result.stdout.strip(), result.stdout


def test_update_information_points_at_the_released_zsync():
    kind, user, repo, tag, filename = build.APPIMAGE_UPDATE_INFO.split("|")
    assert (kind, user, repo, tag) == ("gh-releases-zsync", "kareem2099", "DotScramble", "latest")
    assert filename == "DotScramble-Linux-x86_64.AppImage.zsync"
