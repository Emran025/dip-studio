# PyInstaller specification shared by CI and local Windows builds.
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH)
assets = ROOT / "src" / "dip_studio" / "assets"
cv2_datas, cv2_binaries, cv2_hiddenimports = collect_all("cv2")
skimage_datas, skimage_binaries, skimage_hiddenimports = collect_all("skimage")

a = Analysis(
    [str(ROOT / "src" / "dip_studio" / "presentation" / "app.py")],
    pathex=[str(ROOT / "src")],
    binaries=cv2_binaries + skimage_binaries,
    datas=cv2_datas + skimage_datas + [(str(assets), "dip_studio/assets")],
    hiddenimports=cv2_hiddenimports + skimage_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="DIP-Studio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=str(assets / "DIP-Studio.ico"),
)
