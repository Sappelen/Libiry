Libiry gives you an overview of all your analog, digital and audiobooks. And if you want to add book summaries to your overview, you can do that too!<br>
It works with your own book folder structure. There's no separate database.<br>
<br>
More information can be found on https://libiry.org<br>
Note: Like the app itself, its documentation is also still under construction.<br>
<br>
INSTALLATION INSTRUCTIONS<br>
<br>
Windows:<br>
git clone https://github.com/sappelen/Libiry.git<br>
cd Libiry<br>
install.bat<br>
Libiry.bat<br>
<br>
Linux:<br>
<br>
1. System dependencies:<br>
sudo apt install python3-dev python3-venv libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev unrar<br>
<br>
2. Clone and move to /opt/:<br>
git clone https://github.com/Sappelen/Libiry.git ~/Libiry<br>
sudo mv ~/Libiry /opt/Libiry<br>
sudo chown -R $USER:$USER /opt/Libiry<br>
<br>
3. Set up venv and install packages:<br>
cd /opt/Libiry<br>
python3 -m venv venv<br>
venv/bin/pip install -r requirements.txt<br>
<br>
4. Command-line launcher:<br>
sudo ln -s /opt/Libiry/Libiry.sh /usr/local/bin/libiry<br>
<br>
5. Desktop entry:<br>
sed 's|Exec=Libiry|Exec=/opt/Libiry/Libiry.sh|' /opt/Libiry/linux/Libiry.desktop > ~/.local/share/applications/Libiry.desktop
update-desktop-database ~/.local/share/applications/<br>
<br>
6. Launch:<br>
libiry<br>

  sudo apt install python3-dev libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev
