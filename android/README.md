# Libiry Android Build

## Vereisten

Buildozer werkt **alleen op Linux** (of WSL2 op Windows).

### Linux (Ubuntu/Debian)
```bash
# System dependencies
sudo apt update
sudo apt install git zip unzip openjdk-17-jdk autoconf libtool \
    pkg-config zlib1g-dev libncurses5-dev libncursesw5-dev \
    libtinfo5 cmake libffi-dev libssl-dev

# Buildozer
pip3 install --user buildozer cython
```

### Windows (via WSL2)
```powershell
# In PowerShell als Administrator
wsl --install

# Na herstart, open Ubuntu terminal en volg Linux instructies
```

## Icons voorbereiden

Maak deze bestanden aan in `resources/icons/`:

1. **libiry_android.png** - App icon (512x512 PNG, voor Play Store)
2. **libiry_presplash.png** - Laadscherm (optioneel, 1080x1920 PNG)

Je kunt de bestaande Libiry.ico converteren:
```bash
convert resources/icons/Libiry.ico -resize 512x512 resources/icons/libiry_android.png
```

## APK bouwen

```bash
cd android
chmod +x build-android.sh
./build-android.sh debug      # Debug versie (voor testen)
./build-android.sh release    # Release versie (voor distributie)
```

**Let op:** Eerste build duurt 15-30 minuten (Android SDK/NDK download ~5GB).

## APK installeren

### Via USB (adb)
```bash
# Zet USB debugging aan op je telefoon
adb install -r bin/libiry-*-debug.apk
```

### Handmatig
1. Kopieer APK naar telefoon
2. Open bestand op telefoon
3. Sta "onbekende bronnen" toe indien gevraagd
4. Installeer

## Release APK (voor Play Store)

Voor een release APK heb je een signing key nodig:

```bash
# Eenmalig: maak signing key
keytool -genkey -v -keystore ~/libiry.keystore -alias libiry \
    -keyalg RSA -keysize 2048 -validity 10000

# Pas buildozer.spec aan (uncomment signing regels)
# Bouw release
./build-android.sh release
```

## Troubleshooting

### "SDK license not accepted"
```bash
# Accepteer licenties handmatig
~/.buildozer/android/platform/android-sdk/tools/bin/sdkmanager --licenses
```

### Build faalt
```bash
# Clean build
buildozer android clean
./build-android.sh debug
```

### App start niet
Check `adb logcat | grep python` voor Python errors.

## Bestanden

- `buildozer.spec` - Buildozer configuratie
- `build-android.sh` - Build script
- `README.md` - Deze documentatie
