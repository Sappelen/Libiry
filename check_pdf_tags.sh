#!/bin/bash
# Check PDF Tags - Test welke PDFs tags kunnen lezen/schrijven
#
# Gebruik:
#   ./check_pdf_tags.sh           - Vraagt om folder keuze
#   ./check_pdf_tags.sh [folder]  - Scant de opgegeven folder
#
# Voor PDFs waar tag-ondersteuning faalt, wordt een OPF sidecar file aangemaakt.

cd "$(dirname "$0")"

if [ -z "$1" ]; then
    echo
    echo "Check PDF Tags - Test tag-ondersteuning voor PDFs"
    echo "=================================================="
    echo
    echo "Geef een folder op om te scannen."
    echo
    read -p "Folder om te scannen (of Enter voor huidige folder): " FOLDER
    if [ -z "$FOLDER" ]; then
        FOLDER="."
    fi
    python3 check_pdf_tags.py "$FOLDER"
else
    python3 check_pdf_tags.py "$1"
fi

echo
