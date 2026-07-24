# Building Libiry Installers

This document describes how to build Library installers for distribution.

## Quick Start

### Windows (creating LibrarySetup.exe)

1. Install [Inno Setup 6](https://jrsoftware.org/isinfo.php) (free)
2. Double-click on `build_windows.bat`
3. Result: `dist\installer\LibirySetup.exe`

### macOS (creating .dmg)

```bash
chmod +x build_macos.sh
./build_macos.sh
```
Result: `dist/installer/Libiry-Installer.dmg`

### Linux (creating AppImage)

```bash
chmod +x build_linux.sh
./build_linux.sh
```
Result: `dist/installer/Libiry-x86_64.AppImage`

---

## Automatic Builds via GitHub

After the push to GitHub, installers are automatically built with every release:

```bash
# Create a new release
git tag v1.0.0
git push origin v1.0.0
```

The installers will then appear on the GitHub Releases page.

---

## Manual Build (Step by Step)

### Requirements

| Platform | Required |
|----------|---------|
| Windows | Python 3.10+, Inno Setup 6 |
| macOS | Python 3.10+, Xcode Command Line Tools |
| Linux | Python 3.10+, FUSE, SDL2 libs |

### Windows Details

1. **PyInstaller** bundles Python + Kivy + all dependencies
2. **Inno Setup** creates the installer with:
   - Desktop shortcut
   - Start Menu entry
   - Uninstaller in Windows Apps

### macOS Details

1. **PyInstaller** creates an `.app` bundle
2. **hdiutil** creates a `.dmg` disk image
3. Icon is automatically converted to `.icns`

### Linux Details

1. **PyInstaller** bundles everything into one folder
2. **appimagetool** creates an `.AppImage`
3. Works on Ubuntu, Fedora, Arch and other distributions

---

## Bestanden

| File | Target |
|---------|------|
| `libiry.spec` | PyInstaller config (Windows) |
| `libiry_macos.spec` | PyInstaller config (macOS/Linux) |
| `installer.iss` | Inno Setup script |
| `build_windows.bat` | Windows build script |
| `build_macos.sh` | macOS build script |
| `build_linux.sh` | Linux build script |
| `.github/workflows/build-release.yml` | GitHub Actions |
