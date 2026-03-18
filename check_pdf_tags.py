#!/usr/bin/env python3
"""Check welke PDFs tags kunnen lezen/schrijven.

Dit script scant een folder (recursief) en test voor elke PDF of:
1. Tags gelezen kunnen worden
2. Een test-tag geschreven en weer gelezen kan worden

Voor PDFs waar dit faalt, wordt een OPF sidecar file aangemaakt.

Gebruik:
    python check_pdf_tags.py [folder]

Als geen folder gegeven wordt, wordt de huidige folder gebruikt.
"""

import sys
from pathlib import Path
from typing import Tuple


def test_pdf_tags(pdf_path: Path) -> Tuple[bool, str]:
    """Test of een PDF tags kan lezen en schrijven.

    Args:
        pdf_path: Path naar de PDF file

    Returns:
        Tuple van (success, error_message)
    """
    try:
        # Import PyMuPDF
        try:
            import pymupdf as fitz
        except ImportError:
            import fitz
    except ImportError:
        return False, "PyMuPDF not installed"

    test_tag = "__libiry_test_tag__"

    try:
        # Stap 1: Open en lees metadata
        doc = fitz.open(str(pdf_path))
        original_metadata = doc.metadata.copy()
        original_keywords = original_metadata.get('keywords', '') or ''

        # Stap 2: Voeg test tag toe
        if original_keywords:
            new_keywords = f"{original_keywords}, {test_tag}"
        else:
            new_keywords = test_tag

        doc.set_metadata({
            'keywords': new_keywords,
            'title': original_metadata.get('title', ''),
            'author': original_metadata.get('author', ''),
            'subject': original_metadata.get('subject', ''),
            'creator': original_metadata.get('creator', ''),
            'producer': original_metadata.get('producer', ''),
            'creationDate': original_metadata.get('creationDate', ''),
            'modDate': original_metadata.get('modDate', ''),
        })

        # Stap 3: Probeer op te slaan (incremental)
        try:
            doc.save(str(pdf_path), incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
        except Exception as e:
            doc.close()
            return False, f"Incremental save failed: {e}"

        doc.close()

        # Stap 4: Heropen en check of tag gelezen kan worden
        doc2 = fitz.open(str(pdf_path))
        saved_keywords = doc2.metadata.get('keywords', '') or ''
        doc2.close()

        if test_tag not in saved_keywords:
            return False, "Tag not found after save"

        # Stap 5: Verwijder test tag (herstel origineel)
        doc3 = fitz.open(str(pdf_path))
        doc3.set_metadata({
            'keywords': original_keywords,
            'title': original_metadata.get('title', ''),
            'author': original_metadata.get('author', ''),
            'subject': original_metadata.get('subject', ''),
            'creator': original_metadata.get('creator', ''),
            'producer': original_metadata.get('producer', ''),
            'creationDate': original_metadata.get('creationDate', ''),
            'modDate': original_metadata.get('modDate', ''),
        })
        doc3.save(str(pdf_path), incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
        doc3.close()

        return True, ""

    except Exception as e:
        return False, str(e)


def create_opf_for_pdf(pdf_path: Path) -> bool:
    """Maak een OPF sidecar file voor een PDF.

    Als er al een OPF bestaat, worden bestaande tags behouden.
    Tags uit de PDF worden gemerged met bestaande OPF tags.

    Args:
        pdf_path: Path naar de PDF file

    Returns:
        True als OPF aangemaakt/bijgewerkt is
    """
    # Import OPF helpers
    sys.path.insert(0, str(Path(__file__).parent))
    from core.metadata_extractor import write_opf_tags, get_opf_path, read_opf_tags

    opf_path = get_opf_path(pdf_path)

    # Check of er al een OPF bestaat met tags - zo ja, behoud die
    existing_opf_tags = []
    if opf_path.exists():
        existing_opf_tags = read_opf_tags(pdf_path)
        # Filter de placeholder tag eruit als die ertussen zit
        existing_opf_tags = [t for t in existing_opf_tags if t != "__tag_in_OPF__"]

    # Probeer ook tags uit PDF te lezen
    pdf_tags = []
    try:
        try:
            import pymupdf as fitz
        except ImportError:
            import fitz

        doc = fitz.open(str(pdf_path))
        keywords = doc.metadata.get('keywords', '') or ''
        doc.close()

        if keywords:
            pdf_tags = [t.strip() for t in keywords.split(',') if t.strip()]
    except Exception:
        pass

    # Merge tags: OPF tags hebben prioriteit, voeg PDF tags toe die nog niet bestaan
    # (case-sensitive vergelijking)
    merged_tags = list(existing_opf_tags)
    for tag in pdf_tags:
        if tag not in merged_tags:
            merged_tags.append(tag)

    # Schrijf OPF
    # Note: write_opf_tags maakt geen bestand aan bij lege tags lijst,
    # dus we voegen een placeholder tag toe voor problematische PDFs zonder tags.
    if merged_tags:
        return write_opf_tags(pdf_path, merged_tags)
    else:
        # Maak OPF met marker zodat we weten dat deze PDF problematisch is
        # (Bij volgende tag-edit wordt OPF gebruikt i.p.v. PDF metadata)
        return write_opf_tags(pdf_path, ["__tag_in_OPF__"])


def scan_folder(folder: Path, create_opf: bool = True, verbose: bool = True):
    """Scan een folder voor PDFs en test tag support.

    Args:
        folder: Folder om te scannen
        create_opf: Maak OPF files voor problematische PDFs
        verbose: Toon voortgang
    """
    if not folder.exists():
        print(f"Error: Folder does not exist: {folder}")
        return

    # Verzamel alle PDFs
    pdfs = list(folder.rglob("*.pdf"))
    total = len(pdfs)

    if total == 0:
        print("No PDF files found.")
        return

    print(f"Found {total} PDF files. Testing tag support...\n")

    success_count = 0
    failed_count = 0
    failed_pdfs = []

    for i, pdf_path in enumerate(pdfs, 1):
        if verbose:
            print(f"[{i}/{total}] Testing: {pdf_path.name}...", end=" ")

        success, error = test_pdf_tags(pdf_path)

        if success:
            success_count += 1
            if verbose:
                print("OK")
        else:
            failed_count += 1
            failed_pdfs.append((pdf_path, error))
            if verbose:
                print(f"FAILED: {error}")

            if create_opf:
                if create_opf_for_pdf(pdf_path):
                    if verbose:
                        print(f"         -> Created OPF sidecar file")
                else:
                    if verbose:
                        print(f"         -> Failed to create OPF file")

    # Samenvatting
    print(f"\n{'='*60}")
    print(f"Results:")
    print(f"  Total PDFs:     {total}")
    print(f"  Tag support OK: {success_count}")
    print(f"  Tag support FAILED: {failed_count}")

    if failed_pdfs:
        print(f"\nProblematic PDFs:")
        for pdf_path, error in failed_pdfs:
            print(f"  - {pdf_path}: {error}")

        if create_opf:
            print(f"\nOPF sidecar files created for {failed_count} PDFs.")
            print("Tags for these PDFs will be stored in the OPF files.")


def main():
    """Main entry point."""
    if len(sys.argv) > 1:
        folder = Path(sys.argv[1])
    else:
        folder = Path.cwd()

    print(f"Scanning folder: {folder}\n")
    scan_folder(folder)


if __name__ == "__main__":
    main()
