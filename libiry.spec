# -*- mode: python ; coding: utf-8 -*-
# =============================================================================
# PyInstaller spec file for Libiry
# =============================================================================
# This file configures PyInstaller to bundle Library into a
# standalone executable. PyInstaller analyzes the imports and bundles
# Python + all dependencies into one folder or one executable.
#
# Why this approach:
# - onefile=False: Kivy works better in folder mode because of the many DLLs
# - Tree() for resources: preserves the folder structure of icons and configs
# - Hidden imports: some Kivy/PIL modules are not found automatically
#
# Usage: pyinstaller libiry.spec
#=============================================================================

import os
import sys
from kivy_deps import sdl2, glew
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

# Path to project root (where this file sits)
SPEC_ROOT = os.path.dirname(os.path.abspath(SPEC))

# Hidden imports for Kivy en PIL
# Beware: collect_submodules('kivy') fails on kivy.garden (namespace package)
# Therefore manual addition of specific modules needed at runtime
hiddenimports = [
    # Kivy core modules dynamically loaded
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
    # Windows specifiek
    'win32timezone',
    # App dependencies
    'ebookmeta',
    'mobi',
    'fitz',  # PyMuPDF
    'send2trash',
]

# Add Kivy uix modules (widgets)
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

# Data files that must be bundled too
# Format: (source_path, destination_folder)
datas = [
    (os.path.join(SPEC_ROOT, 'resources'), 'resources'),
    (os.path.join(SPEC_ROOT, 'customize'), 'customize'),
    (os.path.join(SPEC_ROOT, 'about.txt'), '.'),
]

# Collect Kivy data files (fonts, images, etc)
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
        # Excludes to limit file size
        'tkinter',      # No need, we use Kivy
        'matplotlib',   # No need
        'numpy.tests',  # Test files, no need
        'scipy',        # No need
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
    exclude_binaries=True,  # True = folder mode (recommended for Kivy)
    name='Libiry',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,  # Compression for smaller files
    console=False,  # False = no console window (GUI app)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(SPEC_ROOT, 'resources', 'icons', 'Libiry.ico'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    *[Tree(p) for p in (sdl2.dep_bins + glew.dep_bins)],  # Kivy Windows dependencies
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Libiry',
)
