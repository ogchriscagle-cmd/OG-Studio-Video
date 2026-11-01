# -*- mode: python ; coding: utf-8 -*-
from app_version import VERSION
from PyInstaller.utils.hooks import collect_submodules, copy_metadata


a = Analysis(
    ['studio_app.py'],
    pathex=[],
    binaries=[],
    datas=[('studio', 'studio')] + copy_metadata('transformers') + copy_metadata('huggingface-hub'),
    hiddenimports=collect_submodules('transformers.models.blip') + [
        'transformers.models.bert.tokenization_bert',
        'transformers.models.bert.tokenization_bert_fast',
        'webview.platforms.edgechromium', 'sklearn.utils._cython_blas',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'IPython', 'pytest', 'tkinter', 'tensorflow', 'jax'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=f'OG-Studio-v{VERSION}-windows-x64',
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
)
