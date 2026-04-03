#!/usr/bin/env python3
"""Check welke PDFs tags kunnen lezen/schrijven.

Dit script scant een folder (recursief) en test voor elke PDF of:
1. Tags gelezen kunnen worden
2. Een test-tag geschreven en weer gelezen kan worden

Voor PDFs waar dit faalt, wordt een Markdown sidecar file aangemaakt.

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
        # Tags worden opgeslagen in 'subject' veld (Calibre-compatibel)
        doc = fitz.open(str(pdf_path))
        original_metadata = doc.metadata.copy()
        original_subject = original_metadata.get('subject', '') or ''

        # Stap 2: Voeg test tag toe aan subject (met komma-spatie separator)
        if original_subject:
            new_subject = f"{original_subject}, {test_tag}"
        else:
            new_subject = test_tag

        doc.set_metadata({
            'subject': new_subject,
            'title': original_metadata.get('title', ''),
            'author': original_metadata.get('author', ''),
            'keywords': original_metadata.get('keywords', ''),
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
        saved_subject = doc2.metadata.get('subject', '') or ''
        doc2.close()

        if test_tag not in saved_subject:
            return False, "Tag not found after save"

        # Stap 5: Verwijder test tag (herstel origineel)
        doc3 = fitz.open(str(pdf_path))
        doc3.set_metadata({
            'subject': original_subject,
            'title': original_metadata.get('title', ''),
            'author': original_metadata.get('author', ''),
            'keywords': original_metadata.get('keywords', ''),
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


def create_sidecar_for_pdf(pdf_path: Path) -> bool:
    """Maak een Markdown sidecar file voor een PDF.

    Als er al een sidecar bestaat, worden bestaande tags behouden.
    Tags uit de PDF worden gemerged met bestaande sidecar tags.

    Args:
        pdf_path: Path naar de PDF file

    Returns:
        True als sidecar aangemaakt/bijgewerkt is
    """
    # Import sidecar helpers
    sys.path.insert(0, str(Path(__file__).parent))
    from core.metadata_extractor import (
        get_sidecar_path, read_sidecar_metadata, write_sidecar_metadata
    )

    sidecar_path = get_sidecar_path(pdf_path)

    # Check of er al een sidecar bestaat met tags - zo ja, behoud die
    existing_tags = []
    existing_metadata = {}
    if sidecar_path.exists():
        sidecar_meta = read_sidecar_metadata(pdf_path)
        if sidecar_meta:
            existing_tags = sidecar_meta.tags or []
            # Filter de placeholder tag eruit als die ertussen zit
            existing_tags = [t for t in existing_tags if t != "__tag_in_sidecar__"]
            # Behoud andere metadata velden
            for field in ['booktitle', 'isbn', 'publisher', 'language', 'description',
                          'series', 'series_index', 'rating', 'notes', 'author_sort',
                          'publication_date', 'pages', 'translator', 'illustrator', 'year']:
                val = getattr(sidecar_meta, field, None)
                if val:
                    existing_metadata[field] = val
            if sidecar_meta.authors:
                existing_metadata['author'] = ', '.join(sidecar_meta.authors)

    # Probeer ook tags uit PDF te lezen (uit subject veld, Calibre-compatibel)
    pdf_tags = []
    try:
        try:
            import pymupdf as fitz
        except ImportError:
            import fitz

        doc = fitz.open(str(pdf_path))
        subject = doc.metadata.get('subject', '') or ''
        doc.close()

        if subject:
            # Tags worden gescheiden door komma-spatie
            pdf_tags = [t.strip() for t in subject.split(', ') if t.strip()]
    except Exception:
        pass

    # Merge tags: sidecar tags hebben prioriteit, voeg PDF tags toe die nog niet bestaan
    # (case-sensitive vergelijking)
    merged_tags = list(existing_tags)
    for tag in pdf_tags:
        if tag not in merged_tags:
            merged_tags.append(tag)

    # Bouw metadata dict
    metadata = dict(existing_metadata)

    # Schrijf sidecar
    # Note: we voegen een placeholder tag toe voor problematische PDFs zonder tags.
    if merged_tags:
        metadata['tags'] = merged_tags
    else:
        # Maak sidecar met marker zodat we weten dat deze PDF problematisch is
        # (Bij volgende tag-edit wordt sidecar gebruikt i.p.v. PDF metadata)
        metadata['tags'] = ["__tag_in_sidecar__"]

    return write_sidecar_metadata(sidecar_path, metadata)


def scan_folder(folder: Path, create_sidecar: bool = True, verbose: bool = True):
    """Scan een folder voor PDFs en test tag support.

    Args:
        folder: Folder om te scannen
        create_sidecar: Maak sidecar files voor problematische PDFs
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

            if create_sidecar:
                if create_sidecar_for_pdf(pdf_path):
                    if verbose:
                        print(f"         -> Created sidecar file")
                else:
                    if verbose:
                        print(f"         -> Failed to create sidecar file")

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

        if create_sidecar:
            print(f"\nMarkdown sidecar files created for {failed_count} PDFs.")
            print("Tags for these PDFs will be stored in the sidecar files.")


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
