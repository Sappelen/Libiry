Libiry gives you an overview of all your analog, digital and audiobooks. And if you want to add book summaries to your overview, you can do that too!<br>
It works with your own book folder structure. There's no separate database.<br>
<br>
More information can be found on https://libiry.org<br>
Note: Like the app itself, its documentation is also still under construction.<br>
<br>
INSTALL INSTRUCTIONS<br>
<br>
Windows:<br>
  End-user install instructions (Windows)

  ▎ Requirement: Python 3.11 or 3.12. Download from python.org/downloads (https://www.python.org/downloads/). During installation, check "Add Python to PATH".

  1. Download Libiry-0.5.x.zip from the Releases page (https://github.com/Sappelen/Libiry/releases).
  2. Right-click the ZIP → Extract All. The location doesn't matter — Downloads is fine.
  3. Open the extracted folder in File Explorer. Click the address bar at the top, type cmd, press Enter. A Command Prompt opens in that folder.
  4. Type exactly:
  powershell -ExecutionPolicy Bypass -File install.ps1
  4. Press Enter. Installation takes about two minutes.
  5. A Libiry shortcut appears on your desktop. You can delete the extracted folder.

  To uninstall:
  - Delete %LOCALAPPDATA%\Programs\Libiry (type this in the File Explorer address bar)
  - Delete the Libiry desktop shortcut
  - To also remove your settings and library index: delete %APPDATA%\Libiry
troubleshoot: if nothing happens, open a new powershell command:
 The script is correct. The problem is a stale PATH.
  What happened:
  1. install.ps1 ran → detected Windows Store Python → showed the error → exit 1 (nothing else ran)
  2. You ran winget install Python.Python.3.12 → Python installed
  3. You ran install.ps1 again in the same window → Get-Command python still found the old WindowsApps path because the window's PATH wasn't refreshed → exit 1 again
  Fix: close the current terminal window, open a new one, navigate back to the Libiry folder, then run again:
  powershell -ExecutionPolicy Bypass -File install.ps1
  The new window picks up the updated PATH from winget's Python installation and the script will proceed past the check.
 

● Prerequisites
  - Python 3.11 or 3.12 — download from python.org/downloads. During installation, check "Add Python to PATH".

  Installation
  1. Go to the Libiry GitHub releases page and download Source code (zip)
  2. Extract the ZIP to a folder of your choice, for example C:\Users\YourName\Libiry
  3. Open the extracted folder
  4. Double-click install.bat
  5. Wait for the installation to complete — a desktop shortcut is created automatically

  To run Libiry
  Use the desktop shortcut, or double-click Libiry.bat in the installation folder.

  To uninstall
  Delete the installation folder and the desktop shortcut. To also remove your settings, delete %APPDATA%\Libiry.

  ---
  That said — I'd still offer both paths on the releases page:

  ▎ Windows — Option A (recommended): Download LibirySetup.exe and run it. If Windows blocks it, use Option B.
  ▎
  ▎ Windows — Option B (requires Python): Download Source code (zip), extract, run install.bat.

  Most home users can click through SmartScreen with "More info → Run anyway". Only corporate machines with strict policies need Option B.


Download LibirySetup.exe from the Releases page (https://github.com/Sappelen/Libiry/releases).<br>
Run it. It installs Libiry and creates a desktop shortcut and Start Menu entry automatically.<br>
If Windows' Smartapp blocks installation, click on More info → Run anyway        

 That's a stricter block than the usual SmartScreen warning — no "More info" escape hatch. Two ways around it:

  Option A — right-click unblock (easiest):
  1. Right-click LibirySetup.exe → Properties
  2. At the bottom of the General tab: check Unblock
  3. Click Apply, OK, then run the installer

The "Get apps from the Store" button is the clue — that's not SmartScreen, that's a separate Windows setting that restricts app installation to the Microsoft Store only.
  Check: Settings → Apps → Advanced app settings → Choose where to get apps
  If it's set to "The Microsoft Store only", change it to "Anywhere" (or "Anywhere, but let me know if there's a comparable app in the Store"). Then try the installer again.
  This setting overrides SmartScreen entirely — no "More info" escape is possible when it's set to Store only, even as administrator.



  Option B — PowerShell:
  Unblock-File -Path "C:\path\to\LibirySetup.exe"
  Then run the installer normally.

  Both approaches remove the "downloaded from internet" mark that Windows attaches to the file. This is the permanent fix for that file — no need to change any security settings.

● Expected — this is Windows SmartScreen blocking an unsigned installer. It has nothing to do with your code; it happens to every new installer that hasn't built up a download reputation
  yet.

  For you and testers right now:
  Click More info → Run anyway. That's it.

  For end users long-term, three options:

  1. Wait for reputation — SmartScreen tracks download counts. After enough users download and run it without reporting problems, the warning disappears automatically. No action needed,
  just takes time.
  2. Code signing certificate — A paid certificate (~€100–400/year from DigiCert, Sectigo, etc.) signs the installer so SmartScreen trusts it immediately. Standard for commercial software.
  3. Document it — Add a note to your installation instructions: "Windows may show a SmartScreen warning. Click 'More info' → 'Run anyway'. This is normal for new software without a
  commercial certificate."




<br>
For developers:<br>
git clone https://github.com/sappelen/Libiry.git "C:\Program Files\Libiry"<br>
cd "C:\Program Files\Libiry"<br>
.\install.bat<br>
.\Libiry.bat<br>
To create a desktop shortcut, right-click Libiry.bat → Send to → Desktop (create shortcut). <br>
<br>
Alternatively, use %LOCALAPPDATA%\Programs instead of C:\Program Files  (no admin rights needed).<br>
<br>
Linux:<br>
<br>
Method 1:<br>
Download Libiry-0.5.0-Linux-x86_64.AppImage from the Releases page (https://github.com/Sappelen/Libiry/releases).<br><br>
type chmod +x Libiry-0.5.0-Linux-x86_64.AppImage in your terminal<br>
Run it (double-click it or type ./Libiry-0.5.0-Linux-x86_64.AppImage in your terminal)
<br>
Method 2:<br>
curl -O https://raw.githubusercontent.com/sappelen/Libiry/master/linux/install.sh<br>
chmod +x install.sh<br>
./install.sh<br>
<br>
Method 3 (for developers):<br>
git clone https://github.com/sappelen/Libiry.git<br>
cd Libiry<br>
chmod +x linux/install.sh<br>
sudo linux/install.sh<br>
libiry<br>
<br>
UNINSTALL INSTRUCTIONS<br>
<br>
Windows:<br>
Settings → Apps → search "Libiry" → Uninstall (requires the Inno Setup installer to have been used)<br>
Or: Start Menu → Libiry → Uninstall Libiry<br>
<br>
The uninstaller removes the app from Program Files. It does not remove user data. For a complete clean uninstall, also manually delete:<br>
- %APPDATA%\Libiry (settings and customizations)<br>
- %LOCALAPPDATA%\Libiry (cover cache)<br>
<br>
Linux:<br>
Method 1:<br>
Remove Libiry-0.5.0-Linux-x86_64.AppImage<br>
  - ~/.config/Libiry/ (settings)
  - ~/.cache/Libiry/ (cover cache)
  - ~/.kivy/ (Kivy config)

  This is standard AppImage behavior — by design. The upside is that reinstalling the AppImage picks up your old settings automatically.

  If a user wants a truly clean uninstall they'd need to delete those folders manually. Your Linux uninstall instructions for AppImage users should say:

  ▎ To uninstall: delete the .AppImage file.
  ▎ To also remove your settings: rm -rf ~/.config/Libiry ~/.cache/Libiry
  
can you make a list of everything that might have come onto their computer (python, kivy) and how to remove that again, with terminal instructions? also pointing out the dangers?         
● AppImage install leaves nothing system-level behind — Python and Kivy are bundled inside the AppImage file. The footprint is:

  ┌─────────────┬────────────────────────────────┬──────────────────────────────────┬──────────────────────────────────────────────────────────────────────┐
  │    What     │            Location            │          How to remove           │                                Danger                                │
  ├─────────────┼────────────────────────────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────────────┤
  │ The app     │ wherever you put the .AppImage │ rm ~/Downloads/Libiry-*.AppImage │ None                                                                 │
  ├─────────────┼────────────────────────────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────────────┤
  │ Settings    │ ~/.config/Libiry/              │ rm -rf ~/.config/Libiry/         │ Irreversible — your folder location and customizations are gone      │
  ├─────────────┼────────────────────────────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────────────┤
  │ Cover cache │ ~/.cache/Libiry/               │ rm -rf ~/.cache/Libiry/          │ Safe — rebuilds itself                                               │
  ├─────────────┼────────────────────────────────┼──────────────────────────────────┼──────────────────────────────────────────────────────────────────────┤
  │ Kivy config │ ~/.kivy/                       │ rm -rf ~/.kivy/                  │ Caution — if you have other Kivy apps, this removes their config too │
  └─────────────┴────────────────────────────────┴──────────────────────────────────┴──────────────────────────────────────────────────────────────────────┘

  Complete AppImage clean uninstall:
  rm ~/Downloads/Libiry-*.AppImage
  rm -rf ~/.config/Libiry/
  rm -rf ~/.cache/Libiry/
  Leave ~/.kivy/ unless you're certain you have no other Kivy apps.

  ---
  install.sh install touches system directories and requires sudo to clean up:

  ┌───────────────────┬──────────────────────────────────────────────────────┬─────────────────────────────────────────────────────────┬────────────────────────────────────┐
  │       What        │                       Location                       │                      How to remove                      │               Danger               │
  ├───────────────────┼──────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────┼────────────────────────────────────┤
  │ App + Python venv │ /opt/Libiry/                                         │ sudo rm -rf /opt/Libiry/                                │ None beyond losing the app         │
  ├───────────────────┼──────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────┼────────────────────────────────────┤
  │ CLI launcher      │ /usr/local/bin/libiry                                │ sudo rm /usr/local/bin/libiry                           │ None                               │
  ├───────────────────┼──────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────┼────────────────────────────────────┤
  │ System icon       │ /usr/share/pixmaps/libiry.png                        │ sudo rm /usr/share/pixmaps/libiry.png                   │ None                               │
  ├───────────────────┼──────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────┼────────────────────────────────────┤
  │ Desktop entry     │ ~/.local/share/applications/Libiry.desktop           │ rm ~/.local/share/applications/Libiry.desktop           │ None                               │
  ├───────────────────┼──────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────┼────────────────────────────────────┤
  │ User icon         │ ~/.local/share/icons/hicolor/256x256/apps/libiry.png │ rm ~/.local/share/icons/hicolor/256x256/apps/libiry.png │ None                               │
  ├───────────────────┼──────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────┼────────────────────────────────────┤
  │ Settings          │ ~/.config/Libiry/                                    │ rm -rf ~/.config/Libiry/                                │ Irreversible                       │
  ├───────────────────┼──────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────┼────────────────────────────────────┤
  │ Cover cache       │ ~/.cache/Libiry/                                     │ rm -rf ~/.cache/Libiry/                                 │ Safe                               │
  ├───────────────────┼──────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────┼────────────────────────────────────┤
  │ Kivy config       │ ~/.kivy/                                             │ rm -rf ~/.kivy/                                         │ Caution — other Kivy apps affected │
  ├───────────────────┼──────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────┼────────────────────────────────────┤
  │ System packages   │ libsdl2-dev, python3-venv, etc.                      │ see below                                               │ High danger                        │
  └───────────────────┴──────────────────────────────────────────────────────┴─────────────────────────────────────────────────────────┴────────────────────────────────────┘

  The uninstall.sh script handles everything except system packages and ~/.kivy/.

  System packages — do not remove blindly. The packages installed by install.sh (python3-dev, python3-venv, libsdl2-dev, etc.) may be needed by other software. Running:
  sudo apt-get remove python3-dev python3-venv libsdl2-dev
  sudo apt-get autoremove
  could remove dependencies shared with other apps. Only do this if you know these packages were not on your system before installing Libiry.




<br>
Methods 2 and 3:<br>
cd /opt/Libiry<br>
chmod +x linux/uninstall.sh<br>
./linux/uninstall.sh<br>
<br>
The script asks three questions:<br>
1. Confirm removal of the app, symlink and desktop entry<br>
2. Whether to also remove settings (~/.config/Libiry)<br>
3. Whether to also remove the cover cache (~/.cache/Libiry)<br>
