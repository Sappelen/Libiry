# Libiry macOS Build

## For end users: .app or .dmg

### Option 1: DMG (recommended)
1. Download `Libiry.dmg`
2. Double-click to open
3. Drag `Libiry.app` to the Applications folder
4. Launch from Applications or Spotlight

### Option 2: .app directly
1. Download `Libiry.app`
2. Move to Applications folder
3. First launch: Right-click > Open (to bypass Gatekeeper)

## Building the app

### Requirements
- macOS 10.15+ (Catalina or newer)
- Python 3.10 or 3.11
- Xcode Command Line Tools

```bash
# Install Xcode CLI tools
xcode-select --install

# Install Python (if needed)
brew install python@3.11
```

### Build .app bundle
```bash
cd macos
chmod +x build-macos.sh
./build-macos.sh
```

Output: `build-macos/dist/Libiry.app`

### Build .dmg for distribution
```bash
./build-macos.sh --dmg
```

Output: `build-macos/Libiry.dmg`

## Running from source (development)

```bash
# One-time setup
chmod +x macos/install.sh
./macos/install.sh

# Run
chmod +x macos/run.sh
./macos/run.sh
```

## Troubleshooting

### "Libiry.app is damaged and can't be opened"
This happens when the app isn't signed. Fix with:
```bash
xattr -cr /Applications/Libiry.app
```

### "Libiry.app cannot be opened because the developer cannot be verified"
Right-click the app > Open > Open

### App doesn't start
Check Console.app for error messages, or run from terminal:
```bash
/Applications/Libiry.app/Contents/MacOS/Libiry
```

## Files

- `build-macos.sh` - Builds .app and optionally .dmg
- `libiry.spec` - PyInstaller configuration
- `install.sh` - Install dependencies for source
- `run.sh` - Run from source
- `README.md` - This documentation
