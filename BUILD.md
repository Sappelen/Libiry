# Building Libiry Installers

Dit document beschrijft hoe je Libiry installers bouwt voor distributie.

## Snelle Start

### Windows (LibirySetup.exe maken)

1. Installeer [Inno Setup 6](https://jrsoftware.org/isinfo.php) (gratis)
2. Dubbelklik op `build_windows.bat`
3. Resultaat: `dist\installer\LibirySetup.exe`

### macOS (.dmg maken)

```bash
chmod +x build_macos.sh
./build_macos.sh
```
Resultaat: `dist/installer/Libiry-Installer.dmg`

### Linux (AppImage maken)

```bash
chmod +x build_linux.sh
./build_linux.sh
```
Resultaat: `dist/installer/Libiry-x86_64.AppImage`

---

## Automatische Builds via GitHub

Na het pushen naar GitHub worden installers automatisch gebouwd bij elke release:

```bash
# Maak een nieuwe release
git tag v1.0.0
git push origin v1.0.0
```

De installers verschijnen dan op de GitHub Releases pagina.

---

## Handmatig Bouwen (Stap voor Stap)

### Vereisten

| Platform | Vereist |
|----------|---------|
| Windows | Python 3.10+, Inno Setup 6 |
| macOS | Python 3.10+, Xcode Command Line Tools |
| Linux | Python 3.10+, FUSE, SDL2 libs |

### Windows Details

1. **PyInstaller** bundelt Python + Kivy + alle dependencies
2. **Inno Setup** maakt de installer met:
   - Desktop shortcut
   - Start Menu entry
   - Uninstaller in Windows Apps

### macOS Details

1. **PyInstaller** maakt een `.app` bundle
2. **hdiutil** maakt een `.dmg` disk image
3. Icon wordt automatisch geconverteerd naar `.icns`

### Linux Details

1. **PyInstaller** bundelt alles naar één folder
2. **appimagetool** maakt een `.AppImage`
3. Werkt op Ubuntu, Fedora, Arch, en andere distributies

---

## Bestanden

| Bestand | Doel |
|---------|------|
| `libiry.spec` | PyInstaller config (Windows) |
| `libiry_macos.spec` | PyInstaller config (macOS/Linux) |
| `installer.iss` | Inno Setup script |
| `build_windows.bat` | Windows build script |
| `build_macos.sh` | macOS build script |
| `build_linux.sh` | Linux build script |
| `.github/workflows/build-release.yml` | GitHub Actions |
