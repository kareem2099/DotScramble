"""Make the project root importable (build, core, gui, src, version_info) for every test,
however pytest is started and whichever test file it collects first."""
import sys
from pathlib import Path

ROOT = str(Path(__file__).resolve().parents[1])
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
