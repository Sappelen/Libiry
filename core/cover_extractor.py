"""Extract cover images from various ebook formats"""

from pathlib import Path
from PIL import Image
import io
import shutil
from typing import Optional, Dict

# Import from central location - no double code!
from core.libiry_style import DEFAULT_FIELD_NAMES

class CoverExtractor:
    """Extract covers from various ebook formats"""

    def __init__(self, field_names: Dict[str, str] = None):
        """Initialize with optional custom field names
        Args: field_names: Dict mapping standard names to custom names"""
        self.field_names = DEFAULT_FIELD_NAMES.copy()
        if field_names:
            self.field_names.update(field_names)

    def extract(self, filepath: Path) -> Optional[Image.Image]:
        """Extract cover from ebook file
        Search for a sidecar image first (f.e. book.pdf.jpg) in the same folder
        If that doesn't exist, try to extract a cover from the ebook itself
        Args: filepath: Path to the ebook file
        Returns PIL Image or None if no cover found or extraction failed"""
        # Check for sidecar cover image (f.e. book.pdf.jpg, book.epub.png)
        sidecar_cover = self._extract_sidecar_cover(filepath)
        if sidecar_cover:
            return sidecar_cover

        suffix = filepath.suffix.lower()

        extractors = {
            '.epub': self._extract_epub_cover,
            '.mobi': self._extract_mobi_cover,
            '.azw3': self._extract_mobi_cover,
            '.azw': self._extract_mobi_cover,
            '.pdf': self._extract_pdf_cover,
            '.cbz': self._extract_comic_cover,
            '.cbr': self._extract_comic_cover,
            '.md': self._extract_markdown_cover,
        }

        extractor = extractors.get(suffix)
        if extractor:
            try:
                return extractor(filepath)
            except Exception as e:
                print(f"Failed to extract cover from {filepath}: {e}")
                return None
        return None

    def _extract_sidecar_cover(self, filepath: Path) -> Optional[Image.Image]:
        """Extract cover from sidecar image file
        Searches for an image file with the same name as the book + image extension
        F.e.: book.pdf.jpg, book.epub.png, book.mobi.jpeg
        Args: filepath: Path to the ebook file
        Returns: PIL Image or None if no sidecar cover found"""
        # Supported image extensions
        image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp']

        for ext in image_extensions:
            # Sidecar format: book.pdf.jpg (extension after file name)
            sidecar_path = filepath.parent / (filepath.name + ext)
            if sidecar_path.exists():
                try:
                    return Image.open(sidecar_path)
                except Exception as e:
                    print(f"Failed to load sidecar cover {sidecar_path}: {e}")
                    continue

        return None

    def _extract_epub_cover(self, filepath: Path) -> Optional[Image.Image]:
        """Extract cover from EPUB file using ebookmeta"""
        try:
            from ebookmeta import get_metadata
            meta = get_metadata(str(filepath))
            if meta.cover_image_data:
                return Image.open(io.BytesIO(meta.cover_image_data))
        except ImportError:
            # Fallback: try with EbookLib
            try:
                import ebooklib
                from ebooklib import epub
                book = epub.read_epub(str(filepath))

                # Try to find cover image
                for item in book.get_items():
                    if item.get_type() == ebooklib.ITEM_cover:
                        return Image.open(io.BytesIO(item.get_content()))

                # Alternative: look for cover in images
                for item in book.get_items_of_type(ebooklib.ITEM_IMAGE):
                    if 'cover' in item.get_name().lower():
                        return Image.open(io.BytesIO(item.get_content()))
            except ImportError:
                print("Neither ebookmeta nor ebooklib installed for EPUB support")
        except Exception as e:
            print(f"EPUB extraction error: {e}")
        return None

    def _extract_mobi_cover(self, filepath: Path) -> Optional[Image.Image]:
        """Extract cover from MOBI/AZW3 file"""
        try:
            import mobi
            tempdir, _ = mobi.extract(str(filepath))

            # Look for cover in extracted files
            temppath = Path(tempdir)

            # Common locations for cover images
            possible_covers = [
                temppath / "Images" / "cover.jpg",
                temppath / "Images" / "cover.jpeg",
                temppath / "Images" / "cover.png",
            ]

            # Also search for any image with 'cover' in name
            for img_dir in [temppath / "Images", temppath / "images", temppath]:
                if img_dir.exists():
                    for img_file in img_dir.glob("*cover*"):
                        if img_file.suffix.lower() in ['.jpg', '.jpeg', '.png', '.gif']:
                            possible_covers.insert(0, img_file)

            # Also try first image as fallback
            for img_dir in [temppath / "Images", temppath / "images", temppath]:
                if img_dir.exists():
                    images = list(img_dir.glob("*.jpg")) + list(img_dir.glob("*.png"))
                    if images:
                        possible_covers.append(sorted(images)[0])

            for cover_path in possible_covers:
                if cover_path.exists():
                    img = Image.open(cover_path).copy()
                    # Clean up temp directory
                    shutil.rmtree(tempdir, ignore_errors=True)
                    return img

            shutil.rmtree(tempdir, ignore_errors=True)
        except ImportError:
            print("mobi library not installed for MOBI/AZW3 support")
        except Exception as e:
            print(f"MOBI extraction error: {e}")
        return None

    def _extract_pdf_cover(self, filepath: Path) -> Optional[Image.Image]:
        """Extract first page from PDF as cover"""
        # Try PyMuPDF (supports both new 'pymupdf' and old 'fitz' import names)
        try:
            try:
                import pymupdf as fitz
            except ImportError:
                import fitz
            doc = fitz.open(str(filepath))
            if len(doc) > 0:
                # Render first page at reasonable resolution
                page = doc[0]
                # Scale to get a good thumbnail size
                mat = fitz.Matrix(0.5, 0.5)
                pix = page.get_pixmap(matrix=mat)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                doc.close()
                return img
        except ImportError:
            # Fallback to pdf2image
            try:
                from pdf2image import convert_from_path
                images = convert_from_path(str(filepath), first_page=1, last_page=1)
                if images:
                    return images[0]
            except ImportError:
                print("Neither PyMuPDF nor pdf2image installed for PDF support")
        except Exception as e:
            print(f"PDF extraction error: {e}")
        return None

    def _extract_comic_cover(self, filepath: Path) -> Optional[Image.Image]:
        """Extract cover from CBZ/CBR comic archive"""
        try:
            from comicbox.comic_archive import ComicArchive
            car = ComicArchive(filepath)
            cover_data = car.get_cover_page()
            if cover_data:
                return Image.open(io.BytesIO(cover_data))
        except ImportError:
            # Fallback: manual extraction for CBZ (which is just a ZIP)
            if filepath.suffix.lower() == '.cbz':
                try:
                    import zipfile
                    with zipfile.ZipFile(filepath, 'r') as zf:
                        # Get sorted list of image files
                        image_files = sorted([
                            f for f in zf.namelist()
                            if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif'))
                            and not f.startswith('__MACOSX')
                        ])
                        if image_files:
                            with zf.open(image_files[0]) as img_file:
                                return Image.open(io.BytesIO(img_file.read()))
                except Exception as e:
                    print(f"CBZ fallback extraction error: {e}")

            # For CBR we need rarfile or unrar
            if filepath.suffix.lower() == '.cbr':
                try:
                    import rarfile
                    with rarfile.RarFile(filepath, 'r') as rf:
                        image_files = sorted([
                            f for f in rf.namelist()
                            if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif'))
                        ])
                        if image_files:
                            with rf.open(image_files[0]) as img_file:
                                return Image.open(io.BytesIO(img_file.read()))
                except ImportError:
                    print("rarfile library not installed for CBR support")
                except Exception as e:
                    print(f"CBR extraction error: {e}")
        except Exception as e:
            print(f"Comic extraction error: {e}")
        return None

    def _extract_markdown_cover(self, filepath: Path) -> Optional[Image.Image]:
        """Extract first valid cover image from markdown YAML frontmatter"""
        try:
            import re

            content = filepath.read_text(encoding='utf-8', errors='replace')
            content = content.replace('\r\n', '\n').replace('\r', '\n')

            # Get configured cover field name
            cover_field = self.field_names.get('cover') or 'cover'

            # Check for YAML frontmatter
            yaml_match = re.match(r'^---[ \t]*\n(.*?)\n---', content, re.DOTALL)
            if not yaml_match:
                return None

            yaml_content = yaml_match.group(1)

            # Stop early if field does not exist
            if not re.search(rf'{re.escape(cover_field)}:', yaml_content, re.IGNORECASE):
                return None

            seen_refs = set()

            # Pattern 1: Wiki links
            wiki_pattern = rf'{re.escape(cover_field)}:\s*"?!?\[\[([^\]]+)\]\]"?'

            for cover_ref in re.findall(wiki_pattern, yaml_content, re.IGNORECASE):
                cover_ref = cover_ref.strip()

                if not cover_ref or cover_ref in seen_refs:
                    continue

                seen_refs.add(cover_ref)

                img = self._load_cover_image(filepath, cover_ref)
                if img is not None:
                    return img

            # Pattern 2: Direct paths/URLs
            direct_pattern = rf'{re.escape(cover_field)}:\s*(?!\[\[)([^\n\[\]]+?)(?:\n|$)'

            for cover_ref in re.findall(direct_pattern, yaml_content, re.IGNORECASE):
                cover_ref = cover_ref.strip().strip('"\'')

                if not cover_ref or cover_ref in seen_refs:
                    continue

                seen_refs.add(cover_ref)

                img = self._load_cover_image(filepath, cover_ref)
                if img is not None:
                    return img

            return None

        except Exception as e:
            print(f"Markdown cover extraction error: {e}")
            return None
            
    def _load_cover_image(self, filepath: Path, cover_ref: str) -> Optional[Image.Image]:
        """Load a cover image from a local path or URL"""
        import io

        def open_image(path: Path) -> Optional[Image.Image]:
            try:
                return Image.open(path)
            except Exception:
                return None

        # URL
        if cover_ref.startswith(("http://", "https://")):
            try:
                import ssl
                import urllib.request

                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE

                req = urllib.request.Request(
                    cover_ref,
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36"
                        )
                    },
                )

                with urllib.request.urlopen(req, timeout=10, context=ctx) as response:
                    return Image.open(io.BytesIO(response.read()))

            except Exception as e:
                print(f"Failed to download image from {cover_ref}: {e}")
                return None

        # Direct relative path
        cover_path = filepath.parent / cover_ref

        if cover_path.is_file():
            img = open_image(cover_path)
            if img is not None:
                return img

        # Try common extensions
        if not Path(cover_ref).suffix:
            for ext in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                test_path = filepath.parent / f"{cover_ref}{ext}"

                if test_path.is_file():
                    img = open_image(test_path)
                    if img is not None:
                        return img
        return None