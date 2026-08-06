# -*- mode: python ; coding: utf-8 -*-
# =============================================================================
# PyInstaller spec file for Libiry - macOS version
# =============================================================================
# macOS-specifieke configuratie. Belangrijkste verschillen met Windows:
# - Geen sdl2/glew dep_bins (macOS bundelt deze anders)
# - .app bundle structuur
# - Aparte icon format (icns ipv ico)
#
# Gebruik: pyinstaller libiry_macos.spec
# =============================================================================

import os
import sys
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

SPEC_ROOT = os.path.dirname(os.path.abspath(SPEC))

hiddenimports = [
      'kivy.core.window',
      'kivy.core.text',
      'kivy.core.image',
      'kivy.core.clipboard',
      'kivy.core.audio',
      'kivy.core.spelling',
      'kivy.graphics.cgl',
      'PIL.Image',
      'PIL.ImageDraw',
      'PIL.ImageFont',
      'ebookmeta',
      'mobi',
      'fitz',
      'send2trash',
  ]

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

datas = [
    (os.path.join(SPEC_ROOT, 'resources'), 'resources'),
    (os.path.join(SPEC_ROOT, 'about.txt'), '.'),
]

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
    excludes=['tkinter', 'matplotlib', 'numpy.tests', 'scipy'],
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
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # macOS icon - moet .icns zijn, wordt gegenereerd door build script
    icon=os.path.join(SPEC_ROOT, 'resources', 'icons', 'Libiry.icns') if os.path.exists(os.path.join(SPEC_ROOT, 'resources', 'icons', 'Libiry.icns')) else None,
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

# macOS .app bundle
app = BUNDLE(
    coll,
    name='Libiry.app',
    icon=os.path.join(SPEC_ROOT, 'resources', 'icons', 'Libiry.icns') if os.path.exists(os.path.join(SPEC_ROOT, 'resources', 'icons', 'Libiry.icns')) else None,
    bundle_identifier='com.libiry.app',
    info_plist={
        'CFBundleName': 'Libiry',
        'CFBundleDisplayName': 'Libiry',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '0.5.0',
        'NSHighResolutionCapable': True,
        'NSRequiresAquaSystemAppearance': False,  # Support dark mode
    },
)
