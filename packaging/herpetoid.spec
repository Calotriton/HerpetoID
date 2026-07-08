# PyInstaller spec for HerpetoID.
#
# Build (from the project root, with the venv active):
#     pyinstaller packaging/herpetoid.spec
#
# Output: dist/HerpetoID/HerpetoID.exe (a one-folder Windows application).

import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

_here = SPECPATH  # noqa: F821  (injected by PyInstaller)

# Bundle the packaged Markdown manual, and the package metadata so entry-point plugin
# discovery keeps working inside the frozen application.
datas = collect_data_files("herpetoid", includes=["resources/**/*"])
datas += copy_metadata("herpetoid")

# First-party plugins are imported dynamically via entry points; make sure they are collected.
hiddenimports = collect_submodules("herpetoid.plugins")

a = Analysis(
    [os.path.join(_here, "main.py")],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="HerpetoID",
    debug=False,
    strip=False,
    upx=False,
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="HerpetoID",
)
