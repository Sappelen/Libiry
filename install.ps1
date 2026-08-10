# Libiry Windows Installer
# Copies Libiry to %LOCALAPPDATA%\Programs\Libiry, creates venv and desktop shortcut.
# Run from the extracted Libiry folder:
#   powershell -ExecutionPolicy Bypass -File install.ps1

$source = $PSScriptRoot
$target = "$env:LOCALAPPDATA\Programs\Libiry"

# --- Validate Python before doing anything ---
$pythonPath = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $pythonPath -or $pythonPath -like "*WindowsApps*") {
    Write-Host ""
    Write-Host "ERROR: Python from python.org is required."
    Write-Host "The Windows Store version is not compatible with this installer."
    Write-Host ""
    Write-Host "Install Python 3.12 with one of these:"
    Write-Host "  winget install Python.Python.3.12"
    Write-Host "  or: https://www.python.org/downloads/"
    Write-Host ""
    Write-Host "During installation, check 'Add Python to PATH'."
    exit 1
}

Write-Host "Installing Libiry to $target..."
if (Test-Path $target) { Remove-Item $target -Recurse -Force }
Copy-Item $source $target -Recurse -Force

Write-Host "Setting up Python environment (this takes a minute)..."
$py = if (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }
& $py -m venv "$target\venv"
& "$target\venv\Scripts\python" -m pip install --upgrade pip --quiet
& "$target\venv\Scripts\pip" install -r "$target\requirements.txt" --quiet

Write-Host "Creating desktop shortcut..."
$sh = New-Object -COM WScript.Shell
$sc = $sh.CreateShortcut("$([Environment]::GetFolderPath('Desktop'))\Libiry.lnk")
$sc.TargetPath       = "$target\venv\Scripts\pythonw.exe"
$sc.Arguments        = "main.py"
$sc.WorkingDirectory = $target
$sc.IconLocation     = "$target\resources\icons\Libiry.ico"
$sc.Save()

Write-Host ""
Write-Host "Done! Libiry installed to: $target"
Write-Host "Start Libiry from the desktop shortcut."
Write-Host "You can now delete the ZIP folder that you downloaded."