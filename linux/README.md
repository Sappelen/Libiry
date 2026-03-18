# Libiry Linux Build

## Voor eindgebruikers: AppImage

Download `Libiry-x86_64.AppImage`, maak uitvoerbaar en start:

```bash
chmod +x Libiry-x86_64.AppImage
./Libiry-x86_64.AppImage
```

Optioneel: integreer in je systeem (desktop shortcut):
```bash
./Libiry-x86_64.AppImage --install
```

## AppImage bouwen

Vereisten:
- Linux systeem (Ubuntu 20.04+ aanbevolen)
- Python 3.10 of 3.11
- wget (voor appimagetool download)
- ImageMagick (optioneel, voor icon conversie)

```bash
# Installeer build dependencies (Ubuntu/Debian)
sudo apt install python3.11 python3.11-venv wget imagemagick

# Bouw AppImage
cd linux
chmod +x build-appimage.sh
./build-appimage.sh
```

Output: `build-linux/Libiry-x86_64.AppImage`

## Vanaf broncode draaien (development)

```bash
# Eenmalig: installeer dependencies
chmod +x linux/install.sh
./linux/install.sh

# Start Libiry
chmod +x linux/run.sh
./linux/run.sh
```

## Bestanden

- `build-appimage.sh` - Bouwt de AppImage
- `install.sh` - Installeert dependencies voor source
- `run.sh` - Start Libiry vanaf source
- `libiry.spec` - PyInstaller configuratie
- `Libiry.desktop` - Desktop entry voor AppImage
