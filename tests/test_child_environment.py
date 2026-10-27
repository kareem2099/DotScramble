"""
Programs the packaged app starts (Tesseract above all) must not inherit the PyInstaller
bundle's LD_LIBRARY_PATH, or they load its older libstdc++ and fail.
"""
import sys

import pytest

from core import auto_updater as au
from src.main import restore_child_library_path

BUNDLE = "/tmp/_MEI123"

linux_only = pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux loader only")


@linux_only
def test_puts_back_the_users_library_path():
    env = {"LD_LIBRARY_PATH": BUNDLE, "LD_LIBRARY_PATH_ORIG": "/opt/lib"}
    restore_child_library_path(env, frozen=True)
    assert env["LD_LIBRARY_PATH"] == "/opt/lib"


@linux_only
def test_drops_the_bundle_path_when_the_user_had_none():
    env = {"LD_LIBRARY_PATH": BUNDLE, "PATH": "/usr/bin"}
    restore_child_library_path(env, frozen=True)
    assert env == {"PATH": "/usr/bin"}


def test_running_from_source_changes_nothing():
    env = {"LD_LIBRARY_PATH": "/opt/lib", "LD_LIBRARY_PATH_ORIG": "/other"}
    restore_child_library_path(env, frozen=False)
    assert env == {"LD_LIBRARY_PATH": "/opt/lib", "LD_LIBRARY_PATH_ORIG": "/other"}


@linux_only
@pytest.mark.parametrize("start", [
    {"LD_LIBRARY_PATH": BUNDLE, "LD_LIBRARY_PATH_ORIG": "/opt/lib"},
    {"LD_LIBRARY_PATH": BUNDLE},
])
def test_self_restart_environment_is_unchanged(start):
    # The updater's relaunch must end up the same whether or not startup already fixed the env.
    fixed = dict(start)
    restore_child_library_path(fixed, frozen=True)
    assert au.restart_environment(fixed) == au.restart_environment(start)
