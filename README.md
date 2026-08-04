Libiry gives you an overview of all your analog, digital and audiobooks. And if you want to add book summaries to your overview, you can do that too!<br>
It works with your own book folder structure. There's no separate database.<br>
<br>
More information can be found on https://libiry.org<br>
Note: Like the app itself, its documentation is also still under construction.<br>
<br>
INSTALL INSTRUCTIONS<br>
<br>
Windows:<br>
git clone https://github.com/sappelen/Libiry.git<br>
cd Libiry<br>
install.bat<br>
Libiry.bat<br>
<br>
Linux:<br>
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
cd /opt/Libiry<br>
chmod +x linux/uninstall.sh<br>
./linux/uninstall.sh<br>
<br>
The script asks three questions:<br>
1. Confirm removal of the app, symlink and desktop entry<br>
2. Whether to also remove settings (~/.config/Libiry)<br>
3. Whether to also remove the cover cache (~/.cache/Libiry)<br>
