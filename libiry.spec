# -*- mode: python ; coding: utf-8 -*-
# =============================================================================
# PyInstaller spec file for Libiry
# =============================================================================
# Dit bestand configureert PyInstaller om Libiry te bundelen naar een
# standalone executable. PyInstaller analyseert de imports en bundelt
# Python + alle dependencies in één folder of één executable.
#
# Waarom deze aanpak:
# - onefile=False: Kivy werkt beter met folder-mode vanwege de vele DLLs
# - Tree() voor resources: behoud mapstructuur van icons en configs
# - Hidden imports: sommige Kivy/PIL modules worden niet automatisch gevonden
#
# Gebruik: pyinstaller libiry.spec
# =============================================================================

import os
import sys
from kivy_deps import sdl2, glew
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

# Pad naar project root (waar dit spec bestand staat)
SPEC_ROOT = os.path.dirname(os.path.abspath(SPEC))

# Hidden imports voor Kivy en PIL
# Let op: collect_submodules('kivy') faalt op kivy.garden (namespace package)
# Daarom specifieke modules die runtime nodig zijn handmatig toevoegen
hiddenimports = [
    # Kivy core modules die dynamisch worden geladen
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

# Voeg Kivy uix modules toe (widgets)
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

# Data files die meegebundeld moeten worden
# Format: (source_path, destination_folder)
datas = [
    (os.path.join(SPEC_ROOT, 'resources'), 'resources'),
    (os.path.join(SPEC_ROOT, 'customize'), 'customize'),
    (os.path.join(SPEC_ROOT, 'about.txt'), '.'),
]

# Verzamel Kivy data files (fonts, images, etc)
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
        # Excludes om bestandsgrootte te beperken
        'tkinter',      # Niet nodig, we gebruiken Kivy
        'matplotlib',   # Niet nodig
        'numpy.tests',  # Test files niet nodig
        'scipy',        # Niet nodig
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
    exclude_binaries=True,  # True = folder mode (aanbevolen voor Kivy)
    name='Libiry',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,  # Compressie voor kleinere bestanden
    console=False,  # False = geen console window (GUI app)
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
