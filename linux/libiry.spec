# -*- mode: python ; coding: utf-8 -*-
# =============================================================================
# PyInstaller spec file for Libiry - Linux versie
# =============================================================================
# Gebruik: pyinstaller linux/libiry.spec
# Dit creëert dist/Libiry/ met de Linux executable
# =============================================================================

import os
import sys
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

# Pad naar project root
SPEC_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(SPEC)))

# Hidden imports voor Kivy en PIL
hiddenimports = [
    # Kivy core modules
    'kivy.core.window',
    'kivy.core.text',
    'kivy.core.image',
    'kivy.core.clipboard',
    'kivy.core.audio',
    'kivy.core.spelling',
    'kivy.graphics.cgl',
    # PIL/Pillow modules
    'PIL.Image',
    'PIL.ImageDraw',
    'PIL.ImageFont',
    # App dependencies
    'ebookmeta',
    'mobi',
    'fitz',  # PyMuPDF
    'send2trash',
]

# Kivy uix modules
kivy_uix = [
    'kivy.uix.label', 'kivy.uix.button', 'kivy.uix.textinput',
    'kivy.uix.boxlayout', 'kivy.uix.gridlayout', 'kivy.uix.scrollview',
    'kivy.uix.image', 'kivy.uix.popup', 'kivy.uix.filechooser',
    'kivy.uix.checkbox', 'kivy.uix.slider', 'kivy.uix.spinner',
    'kivy.uix.widget', 'kivy.uix.floatlayout', 'kivy.uix.relativelayout',
    'kivy.uix.anchorlayout', 'kivy.uix.stacklayout', 'kivy.uix.scatter',
    'kivy.uix.behaviors', 'kivy.uix.recycleview',
]
hiddenimports += kivy_uix

# Data files
datas = [
    (os.path.join(SPEC_ROOT, 'resources'), 'resources'),
    (os.path.join(SPEC_ROOT, 'about.txt'), '.'),
]

# Verzamel Kivy data files
datas += collect_data_files('kivy')

a = Analysis(
    [os.path.join(SPEC_ROOT, 'main.py')],
    pathex=[SPEC_ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy.tests',
        'scipy',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Libiry',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # GUI app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Libiry',
)
