"""
Cython build script for license_manager.py
───────────────────────────────────────────
Compiles src/managers/license_manager.py into a native .so/.pyd extension
so the source cannot be read or trivially decompiled.

Usage:
    python setup_license.py build_ext --inplace

Output:
    src/managers/license_manager.cpython-3XX-<platform>.so  (Linux/macOS)
    src/managers/license_manager.cpython-3XX-<platform>.pyd (Windows)

After compiling, DELETE or .gitignore the original .py file before shipping.
"""

from setuptools import setup, Extension
from Cython.Build import cythonize
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))

extensions = [
    Extension(
        # Module name — must match the import path used in the app
        "src.managers.license_manager",
        sources=[os.path.join(HERE, "src", "managers", "license_manager.py")],
        extra_compile_args=[
            # Strip debug symbols for a smaller, harder-to-analyze binary
            "-O2",
        ] if sys.platform != "win32" else ["/O2"],
    )
]

setup(
    name="dotscramble_license",
    ext_modules=cythonize(
        extensions,
        compiler_directives={
            # Disable docstrings — removes readable source hints from binary
            "embedsignature": False,
            "emit_code_comments": False,
            # Optimize
            "language_level": "3",
            "boundscheck": False,
            "wraparound": True,
        },
        # Don't ship the generated .c files in the dist
        include_path=[HERE],
    ),
    zip_safe=False,
)
