# Check PDF Tags - Test welke PDFs tags kunnen lezen/schrijven
#
# Gebruik:
#   .\check_pdf_tags.ps1           - Vraagt om folder keuze
#   .\check_pdf_tags.ps1 [folder]  - Scant de opgegeven folder
#
# Voor PDFs waar tag-ondersteuning faalt, wordt een OPF sidecar file aangemaakt.

param(
    [string]$Folder
)

Set-Location $PSScriptRoot

if ([string]::IsNullOrEmpty($Folder)) {
    Write-Host ""
    Write-Host "Check PDF Tags - Test tag-ondersteuning voor PDFs"
    Write-Host "=================================================="
    Write-Host ""
    Write-Host "Geef een folder op om te scannen."
    Write-Host ""
    $Folder = Read-Host "Folder om te scannen (of Enter voor huidige folder)"
    if ([string]::IsNullOrEmpty($Folder)) {
        $Folder = "."
    }
}

python check_pdf_tags.py $Folder

Write-Host ""
