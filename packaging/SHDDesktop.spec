# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent
datas = [(str(ROOT / 'assets'), 'assets')]
binaries = []
hiddenimports = []
tmp_ret = collect_all('qqmusic_api')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    [str(ROOT / 'app.py')],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PyQt5', 'PyQt6', 'PySide2'],
    noarchive=False,
    optimize=0,
)
# Qt6Core.dll imports the unsuffixed Windows ICU API. A Codex runtime on the
# build machine exposes an unrelated ICU 78 on PATH; PyInstaller can pick it
# up and then QtCore fails with WinError 127. Use the Windows system ICU.
a.binaries = [item for item in a.binaries if item[0].replace('\\', '/').split('/')[-1].lower()
              not in {'icuuc.dll', 'icudt78.dll'}]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='SHDDesktop',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[str(ROOT / 'assets' / 'app.ico')],
)
