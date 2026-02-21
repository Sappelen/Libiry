"""Extract metadata from various ebook formats."""

from pathlib import Path
from typing import Optional, List, Dict
from dataclasses import dataclass, field
import re


@dataclass
class BookMetadata:
    """Container for book metadata.

    Veldvolgorde gebaseerd op Goodreads CSV export voor maximale compatibiliteit.

    Velden die automatisch uit ebooks geëxtraheerd kunnen worden:
    - booktitle, authors, isbn: basis identificatie
    - rating: beoordeling (vaak Calibre, schaal 0-10 intern, 0-5 getoond)
    - publisher, year, language: publicatie info
    - tags: genres/onderwerpen (uit dc:subject)
    - series, series_index: serie informatie (vaak Calibre)
    - description: samenvatting/omschrijving

    Velden voor gebruikersinvoer:
    - notes: persoonlijke notities
    - cover_url: URL naar cover afbeelding
    """
    # Volgorde: Goodreads CSV export
    cover_url: str = ""                              # UI: cover afbeelding
    booktitle: str = ""                              # Goodreads: Title
    authors: List[str] = field(default_factory=list) # Goodreads: Author
    isbn: str = ""                                   # ISBN
    rating: Optional[float] = None                   # Goodreads: My Rating (0-10 Calibre, 0-5 getoond)
    publisher: str = ""                              # Goodreads: Publisher
    year: str = ""                                   # Goodreads: Year Published
    language: str = ""                               # Extra: taal
    tags: List[str] = field(default_factory=list)    # Goodreads: Bookshelves
    series: str = ""                                 # Extra: serie naam
    series_index: Optional[float] = None             # Extra: serie volgnummer
    description: str = ""                            # Goodreads: My Review
    notes: str = ""                                  # Goodreads: Private Notes


# Default field names - kunnen aangepast worden via customize.txt
# Deze namen worden gebruikt bij het parsen en schrijven van markdown bestanden
# Volgorde gebaseerd op Goodreads CSV export voor maximale compatibiliteit
DEFAULT_FIELD_NAMES = {
    'cover': 'cover',              # UI: cover afbeelding (niet in Goodreads)
    'booktitle': 'booktitle',      # Goodreads: Title
    'author': 'author',            # Goodreads: Author
    'isbn': 'isbn',                # ISBN
    'rating': 'rating',            # Goodreads: My Rating
    'publisher': 'publisher',      # Goodreads: Publisher
    'year': 'year',                # Goodreads: Year Published
    'language': 'language',        # Extra: taal (niet in Goodreads)
    'tags': 'tags',                # Goodreads: Bookshelves
    'series': 'series',            # Extra: serie naam (niet in Goodreads)
    'series_index': 'series_index',# Extra: serie volgnummer
    'description': 'description',  # Goodreads: My Review (of boekbeschrijving)
    'notes': 'notes',              # Goodreads: Private Notes
}


class MetadataExtractor:
    """Extract metadata from various ebook formats."""

    def __init__(self, field_names: Dict[str, str] = None):
        """
        Initialize with optional custom field names.

        Args:
            field_names: Dict mapping standard names to custom names
                         e.g. {'cover': 'coverimage', 'booktitle': 'title'}
        """
        self.field_names = DEFAULT_FIELD_NAMES.copy()
        if field_names:
            self.field_names.update(field_names)

    def extract(self, filepath: Path) -> BookMetadata:
        """
        Extract metadata from ebook file.

        Args:
            filepath: Path to the ebook file

        Returns:
            BookMetadata object with extracted data
        """
        suffix = filepath.suffix.lower()

        extractors = {
            '.epub': self._extract_epub,
            '.mobi': self._extract_mobi,
            '.azw3': self._extract_mobi,
            '.azw': self._extract_mobi,
            '.pdf': self._extract_pdf,
            '.cbz': self._extract_comic,
            '.cbr': self._extract_comic,
            '.md': self._extract_markdown,
            '.markdown': self._extract_markdown,
        }

        extractor = extractors.get(suffix)
        if extractor:
            try:
                return extractor(filepath)
            except Exception as e:
                print(f"Failed to extract metadata from {filepath}: {e}")

        # Return metadata with filename as title fallback
        return BookMetadata(booktitle=filepath.stem)

    def _extract_epub(self, filepath: Path) -> BookMetadata:
        """Extract metadata from EPUB file.

        Probeert meerdere methodes in volgorde van betrouwbaarheid:
        1. Direct OPF parsing (meest betrouwbaar, werkt met EPUB 2.0 en 3.0)
        2. ebookmeta library
        3. ebooklib library

        EPUB 3.0 bestanden (zoals die van Calibre) gebruiken id-attributen
        op dc:title en dc:creator elementen die sommige libraries niet goed
        verwerken. Directe OPF parsing lost dit op.
        """
        meta = BookMetadata(booktitle=filepath.stem)

        # Methode 1: Direct OPF parsing - meest betrouwbaar voor EPUB 2.0 en 3.0
        try:
            meta = self._extract_epub_direct(filepath, meta)
            # Als we titel hebben gevonden, zijn we klaar
            if meta.booktitle and meta.booktitle != filepath.stem:
                return meta
        except Exception as e:
            print(f"Direct OPF parsing error: {e}")

        # Methode 2: ebookmeta library
        try:
            from ebookmeta import get_metadata
            book_meta = get_metadata(str(filepath))

            if book_meta.title:
                meta.booktitle = book_meta.title

            if hasattr(book_meta, 'author_list') and book_meta.author_list:
                meta.authors = list(book_meta.author_list)
            elif hasattr(book_meta, 'authors') and book_meta.authors:
                meta.authors = list(book_meta.authors) if isinstance(book_meta.authors, (list, tuple)) else [book_meta.authors]
            elif hasattr(book_meta, 'author') and book_meta.author:
                meta.authors = [book_meta.author]

            if hasattr(book_meta, 'identifier') and book_meta.identifier:
                isbn = self._extract_isbn(book_meta.identifier)
                if isbn:
                    meta.isbn = isbn

            if hasattr(book_meta, 'tags') and book_meta.tags:
                meta.tags = list(book_meta.tags) if isinstance(book_meta.tags, (list, tuple)) else [book_meta.tags]

            if hasattr(book_meta, 'series') and book_meta.series:
                meta.series = book_meta.series
            if hasattr(book_meta, 'series_index') and book_meta.series_index:
                try:
                    meta.series_index = float(book_meta.series_index)
                except (ValueError, TypeError):
                    pass

            if hasattr(book_meta, 'publisher') and book_meta.publisher:
                meta.publisher = book_meta.publisher
            if hasattr(book_meta, 'lang') and book_meta.lang:
                meta.language = book_meta.lang
            if hasattr(book_meta, 'description') and book_meta.description:
                meta.description = book_meta.description
            if hasattr(book_meta, 'publish_date') and book_meta.publish_date:
                # Extract year from date
                year_match = re.match(r'^(\d{4})', str(book_meta.publish_date))
                if year_match:
                    meta.year = year_match.group(1)

            if meta.booktitle and meta.booktitle != filepath.stem:
                return meta

        except ImportError:
            pass
        except Exception as e:
            print(f"ebookmeta error: {e}")

        # Methode 3: ebooklib library
        try:
            import ebooklib
            from ebooklib import epub
            book = epub.read_epub(str(filepath))

            title = book.get_metadata('DC', 'title')
            if title:
                meta.booktitle = title[0][0]

            creators = book.get_metadata('DC', 'creator')
            if creators:
                meta.authors = [c[0] for c in creators]

            identifiers = book.get_metadata('DC', 'identifier')
            for ident in identifiers:
                isbn = self._extract_isbn(str(ident[0]))
                if isbn:
                    meta.isbn = isbn
                    break

            subjects = book.get_metadata('DC', 'subject')
            if subjects:
                meta.tags = [s[0] for s in subjects]

            publishers = book.get_metadata('DC', 'publisher')
            if publishers:
                meta.publisher = publishers[0][0]

            languages = book.get_metadata('DC', 'language')
            if languages:
                meta.language = languages[0][0]

            descriptions = book.get_metadata('DC', 'description')
            if descriptions:
                meta.description = descriptions[0][0]

            dates = book.get_metadata('DC', 'date')
            if dates:
                year_match = re.match(r'^(\d{4})', str(dates[0][0]))
                if year_match:
                    meta.year = year_match.group(1)

            # Calibre-specific metadata
            calibre_meta = book.get_metadata('OPF', 'meta')
            for item in calibre_meta:
                attrs = item[1] if len(item) > 1 else {}
                name = attrs.get('name', '')
                content = attrs.get('content', '')

                if name == 'calibre:series':
                    meta.series = content
                elif name == 'calibre:series_index':
                    try:
                        meta.series_index = float(content)
                    except (ValueError, TypeError):
                        pass
                elif name == 'calibre:rating':
                    try:
                        meta.rating = float(content)
                    except (ValueError, TypeError):
                        pass

            return meta

        except ImportError:
            print("Neither ebookmeta nor ebooklib installed for EPUB metadata")
        except Exception as e:
            print(f"EPUB metadata error: {e}")

        return meta

    def _extract_epub_direct(self, filepath: Path, meta: BookMetadata) -> BookMetadata:
        """Extract metadata directly from EPUB OPF file.

        EPUB is een ZIP-bestand met daarin een OPF file die de metadata bevat.
        Deze methode parsed de OPF XML direct, wat betrouwbaarder is voor
        zowel EPUB 2.0 als EPUB 3.0 formaten.

        EPUB 3.0 (zoals Calibre produceert) gebruikt id-attributen:
          <dc:title id="id-1">Titel</dc:title>
          <dc:creator id="id-2">Auteur</dc:creator>

        EPUB 2.0 gebruikt geen id-attributen:
          <dc:title>Titel</dc:title>
          <dc:creator opf:role="aut">Auteur</dc:creator>

        Beide formaten worden correct verwerkt.
        """
        import zipfile
        import xml.etree.ElementTree as ET

        # Dublin Core namespace
        DC_NS = 'http://purl.org/dc/elements/1.1/'
        OPF_NS = 'http://www.idpf.org/2007/opf'

        with zipfile.ZipFile(filepath, 'r') as zf:
            # Vind de OPF file via container.xml
            try:
                container_xml = zf.read('META-INF/container.xml')
                container = ET.fromstring(container_xml)

                # Zoek rootfile element
                ns = {'c': 'urn:oasis:names:tc:opendocument:xmlns:container'}
                rootfile = container.find('.//c:rootfile', ns)
                if rootfile is None:
                    # Probeer zonder namespace
                    rootfile = container.find('.//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile')

                if rootfile is not None:
                    opf_path = rootfile.get('full-path')
                else:
                    # Fallback: zoek naar .opf file
                    opf_files = [n for n in zf.namelist() if n.endswith('.opf')]
                    opf_path = opf_files[0] if opf_files else None

                if not opf_path:
                    return meta

                # Lees en parse OPF file
                opf_content = zf.read(opf_path)
                opf = ET.fromstring(opf_content)

                # Zoek metadata element
                metadata = opf.find(f'{{{OPF_NS}}}metadata')
                if metadata is None:
                    metadata = opf.find('metadata')
                if metadata is None:
                    return meta

                # Extract dc:title
                title_elem = metadata.find(f'{{{DC_NS}}}title')
                if title_elem is not None and title_elem.text:
                    meta.booktitle = title_elem.text.strip()

                # Extract dc:creator (authors)
                authors = []
                for creator in metadata.findall(f'{{{DC_NS}}}creator'):
                    if creator.text:
                        authors.append(creator.text.strip())
                if authors:
                    meta.authors = authors

                # Extract dc:identifier (ISBN)
                for identifier in metadata.findall(f'{{{DC_NS}}}identifier'):
                    if identifier.text:
                        isbn = self._extract_isbn(identifier.text)
                        if isbn:
                            meta.isbn = isbn
                            break

                # Extract dc:language
                lang_elem = metadata.find(f'{{{DC_NS}}}language')
                if lang_elem is not None and lang_elem.text:
                    meta.language = lang_elem.text.strip()

                # Extract dc:publisher
                pub_elem = metadata.find(f'{{{DC_NS}}}publisher')
                if pub_elem is not None and pub_elem.text:
                    meta.publisher = pub_elem.text.strip()

                # Extract dc:description
                desc_elem = metadata.find(f'{{{DC_NS}}}description')
                if desc_elem is not None and desc_elem.text:
                    meta.description = desc_elem.text.strip()

                # Extract dc:date (publication year)
                date_elem = metadata.find(f'{{{DC_NS}}}date')
                if date_elem is not None and date_elem.text:
                    # Extract year from date (can be YYYY, YYYY-MM, YYYY-MM-DD, etc.)
                    date_text = date_elem.text.strip()
                    year_match = re.match(r'^(\d{4})', date_text)
                    if year_match:
                        meta.year = year_match.group(1)

                # Extract dc:subject (tags)
                tags = []
                for subject in metadata.findall(f'{{{DC_NS}}}subject'):
                    if subject.text:
                        tags.append(subject.text.strip())
                if tags:
                    meta.tags = tags

                # Extract Calibre series metadata
                for meta_elem in metadata.findall(f'{{{OPF_NS}}}meta'):
                    name = meta_elem.get('name', '')
                    content = meta_elem.get('content', '')
                    if name == 'calibre:series' and content:
                        meta.series = content
                    elif name == 'calibre:series_index' and content:
                        try:
                            meta.series_index = float(content)
                        except (ValueError, TypeError):
                            pass

            except Exception as e:
                print(f"Error parsing OPF: {e}")

        return meta

    def _extract_mobi(self, filepath: Path) -> BookMetadata:
        """Extract metadata from MOBI/AZW3 file."""
        meta = BookMetadata(booktitle=filepath.stem)

        try:
            from mobi import Mobi
            book = Mobi(str(filepath))
            book.parse()

            if hasattr(book, 'title') and book.title:
                meta.booktitle = book.title

            if hasattr(book, 'author') and book.author:
                meta.authors = [book.author]

            if hasattr(book, 'isbn') and book.isbn:
                meta.isbn = book.isbn

            if hasattr(book, 'publisher') and book.publisher:
                meta.publisher = book.publisher

            if hasattr(book, 'language') and book.language:
                meta.language = book.language

        except ImportError:
            print("mobi library not installed for MOBI metadata")
        except Exception as e:
            print(f"MOBI metadata error: {e}")

        return meta

    def _extract_pdf(self, filepath: Path) -> BookMetadata:
        """Extract metadata from PDF file."""
        meta = BookMetadata(booktitle=filepath.stem)

        # Try PyMuPDF (supports both new 'pymupdf' and old 'fitz' import names)
        try:
            try:
                import pymupdf as fitz
            except ImportError:
                import fitz
            doc = fitz.open(str(filepath))
            pdf_meta = doc.metadata

            if pdf_meta:
                if pdf_meta.get('title'):
                    meta.booktitle = pdf_meta['title']

                if pdf_meta.get('author'):
                    # Split authors by common separators
                    authors_str = pdf_meta['author']
                    for sep in [';', ',', '&', ' and ']:
                        if sep in authors_str:
                            meta.authors = [a.strip() for a in authors_str.split(sep)]
                            break
                    else:
                        meta.authors = [authors_str]

                if pdf_meta.get('subject'):
                    meta.tags = [t.strip() for t in pdf_meta['subject'].split(',')]

                if pdf_meta.get('keywords'):
                    keywords = [k.strip() for k in pdf_meta['keywords'].split(',')]
                    meta.tags.extend(keywords)

                if pdf_meta.get('producer'):
                    meta.publisher = pdf_meta['producer']

            doc.close()

        except ImportError:
            # Fallback to PyPDF2
            try:
                from PyPDF2 import PdfReader
                reader = PdfReader(str(filepath))
                info = reader.metadata

                if info:
                    if info.title:
                        meta.booktitle = info.title
                    if info.author:
                        meta.authors = [info.author]

            except ImportError:
                print("Neither PyMuPDF nor PyPDF2 installed for PDF metadata")
        except Exception as e:
            print(f"PDF metadata error: {e}")

        return meta

    def _extract_comic(self, filepath: Path) -> BookMetadata:
        """Extract metadata from CBZ/CBR comic archive."""
        meta = BookMetadata(booktitle=filepath.stem)

        try:
            from comicbox.comic_archive import ComicArchive
            car = ComicArchive(filepath)
            comic_meta = car.get_metadata()

            if comic_meta:
                if hasattr(comic_meta, 'series') and comic_meta.series:
                    meta.series = comic_meta.series
                    meta.booktitle = comic_meta.series

                if hasattr(comic_meta, 'title') and comic_meta.title:
                    meta.booktitle = comic_meta.title

                if hasattr(comic_meta, 'issue') and comic_meta.issue:
                    try:
                        meta.series_index = float(comic_meta.issue)
                    except (ValueError, TypeError):
                        pass

                if hasattr(comic_meta, 'writer') and comic_meta.writer:
                    meta.authors = [comic_meta.writer] if isinstance(comic_meta.writer, str) else list(comic_meta.writer)

                if hasattr(comic_meta, 'publisher') and comic_meta.publisher:
                    meta.publisher = comic_meta.publisher

                if hasattr(comic_meta, 'tags') and comic_meta.tags:
                    meta.tags = list(comic_meta.tags) if isinstance(comic_meta.tags, (list, tuple)) else [comic_meta.tags]

        except ImportError:
            pass
        except Exception as e:
            print(f"Comic metadata error: {e}")

        return meta

    def _extract_isbn(self, identifier: str) -> str:
        """Extract ISBN from identifier string."""
        import re

        if not identifier:
            return ""

        identifier = str(identifier).upper()

        # Remove common prefixes
        for prefix in ['ISBN:', 'ISBN-10:', 'ISBN-13:', 'URN:ISBN:']:
            if identifier.startswith(prefix):
                identifier = identifier[len(prefix):]

        # Clean and validate
        cleaned = re.sub(r'[^0-9X]', '', identifier)

        # Valid ISBN-10 or ISBN-13
        if len(cleaned) == 10 or len(cleaned) == 13:
            return cleaned

        # Try to find ISBN pattern in the string
        isbn13_match = re.search(r'97[89]\d{10}', identifier.replace('-', '').replace(' ', ''))
        if isbn13_match:
            return isbn13_match.group()

        isbn10_match = re.search(r'\d{9}[\dX]', identifier.replace('-', '').replace(' ', ''))
        if isbn10_match:
            return isbn10_match.group()

        return ""

    def _extract_markdown(self, filepath: Path) -> BookMetadata:
        """
        Extract metadata from markdown file.

        AANGEPASTE LOGICA: Als YAML frontmatter aanwezig is, zoek eerst in de
        frontmatter naar [cover]/[booktitle]. Als die NIET gevonden worden in
        de frontmatter, doorzoek dan OOK de rest van het bestand (voor
        BookSpineScanner multi-book format waar frontmatter alleen scan-metadata bevat).
        """
        meta = BookMetadata(booktitle=filepath.stem)

        try:
            content = filepath.read_text(encoding='utf-8')
            content = content.replace('\r\n', '\n').replace('\r', '\n')

            # Check for YAML frontmatter
            yaml_match = re.match(r'^---[ \t]*\n(.*?)\n---', content, re.DOTALL)

            if yaml_match:
                # YAML frontmatter exists - search in frontmatter first
                yaml_content = yaml_match.group(1)
                meta = self._parse_markdown_fields(yaml_content, meta)

                # Als cover/booktitle niet in frontmatter gevonden, zoek ook in rest van bestand
                # Dit ondersteunt BookSpineScanner format waar frontmatter alleen scan-metadata bevat
                if not meta.cover_url and meta.booktitle == filepath.stem:
                    # Geen boek-metadata in frontmatter, zoek in rest van bestand
                    rest_content = content[yaml_match.end():]
                    meta = self._parse_markdown_fields(rest_content, meta)
            else:
                # No frontmatter - search entire file (for multi-book files)
                # Only extract first book's metadata
                meta = self._parse_markdown_fields(content, meta)

        except Exception as e:
            print(f"Markdown metadata error: {e}")

        return meta

    def _parse_markdown_fields(self, content: str, meta: BookMetadata) -> BookMetadata:
        """
        Parse metadata fields from content using configured field names.
        NO fallback to default names - only use configured field names.

        Ondersteunt tags in twee formaten:
        1. YAML lijst: tags: [fiction, sci-fi] of tags:\n  - fiction\n  - sci-fi
        2. Komma-gescheiden: tags: fiction, sci-fi
        """
        # Get configured field names (use default if not configured)
        cover_field = self.field_names.get('cover') or 'cover'
        title_field = self.field_names.get('booktitle') or 'booktitle'
        author_field = self.field_names.get('author') or 'author'
        isbn_field = self.field_names.get('isbn') or 'isbn'
        tags_field = self.field_names.get('tags') or 'tags'

        # Helper to find field value - NO fallback, only use configured name
        def find_field(field_name: str) -> str:
            pattern = rf'^{re.escape(field_name)}:\s*(.+?)$'
            match = re.search(pattern, content, re.MULTILINE | re.IGNORECASE)
            if match:
                return self._clean_field_value(match.group(1))
            return ""

        # Extract booktitle
        title = find_field(title_field)
        if title:
            meta.booktitle = title

        # Extract author(s)
        author = find_field(author_field)
        if author:
            # Handle multiple authors (comma or semicolon separated)
            if ',' in author or ';' in author:
                meta.authors = [a.strip() for a in re.split(r'[,;]', author)]
            else:
                meta.authors = [author]

        # Extract ISBN
        isbn_val = find_field(isbn_field)
        if isbn_val:
            meta.isbn = self._extract_isbn(isbn_val)

        # Extract cover URL for reference
        cover = find_field(cover_field)
        if cover:
            meta.cover_url = cover

        # Extract tags - ondersteunt meerdere formaten
        tags = self._parse_tags(content, tags_field)
        if tags:
            meta.tags = tags

        # If no booktitle but we have cover, use cover reference as title
        if not meta.booktitle and meta.cover_url:
            # Extract filename from cover URL/path
            cover_name = Path(meta.cover_url.strip('[]"\'!')).stem
            if cover_name:
                meta.booktitle = cover_name

        return meta

    def _parse_tags(self, content: str, tags_field: str) -> List[str]:
        """
        Parse tags uit markdown content.

        Ondersteunt formaten:
        1. YAML inline array: tags: [fiction, sci-fi, "space opera"]
        2. YAML block list:
           tags:
             - fiction
             - sci-fi
        3. Komma-gescheiden: tags: fiction, sci-fi, space opera

        Tags worden genormaliseerd: lowercase, getrimd, lege tags verwijderd.
        """
        tags = []

        # Format 1: YAML inline array [tag1, tag2, ...]
        inline_pattern = rf'^{re.escape(tags_field)}:\s*\[(.*?)\]'
        inline_match = re.search(inline_pattern, content, re.MULTILINE | re.IGNORECASE)
        if inline_match:
            # Parse items binnen brackets, respecteer quotes
            items_str = inline_match.group(1)
            # Split op komma maar niet binnen quotes
            items = re.findall(r'"([^"]+)"|\'([^\']+)\'|([^,\s][^,]*)', items_str)
            for match in items:
                # match is een tuple van 3 capture groups
                tag = match[0] or match[1] or match[2]
                tag = tag.strip().strip('"\'')
                if tag:
                    tags.append(tag)
            return self._normalize_tags(tags)

        # Format 2: YAML block list (tags:\n  - item\n  - item)
        block_pattern = rf'^{re.escape(tags_field)}:\s*$\n((?:\s+-\s+.+\n?)+)'
        block_match = re.search(block_pattern, content, re.MULTILINE | re.IGNORECASE)
        if block_match:
            items_block = block_match.group(1)
            for line in items_block.split('\n'):
                line = line.strip()
                if line.startswith('-'):
                    tag = line[1:].strip().strip('"\'')
                    if tag:
                        tags.append(tag)
            return self._normalize_tags(tags)

        # Format 3: Simple comma-separated
        simple_pattern = rf'^{re.escape(tags_field)}:\s*(.+?)$'
        simple_match = re.search(simple_pattern, content, re.MULTILINE | re.IGNORECASE)
        if simple_match:
            value = simple_match.group(1).strip()
            # Niet als het met [ begint (dat was format 1)
            if not value.startswith('['):
                for tag in re.split(r'[,;]', value):
                    tag = tag.strip().strip('"\'')
                    if tag:
                        tags.append(tag)
            return self._normalize_tags(tags)

        return []

    def _normalize_tags(self, tags: List[str]) -> List[str]:
        """
        Normaliseer tags: lowercase, trim, verwijder lege en duplicaten.
        Behoudt originele volgorde (eerste occurrence).
        """
        seen = set()
        normalized = []
        for tag in tags:
            tag_lower = tag.lower().strip()
            if tag_lower and tag_lower not in seen:
                seen.add(tag_lower)
                normalized.append(tag_lower)
        return normalized

    def _clean_field_value(self, value: str) -> str:
        """Clean field value by removing quotes, brackets, and whitespace."""
        value = value.strip()
        # Remove surrounding quotes
        if (value.startswith('"') and value.endswith('"')) or \
           (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        # Remove Obsidian wiki-link brackets
        if value.startswith('[[') and value.endswith(']]'):
            value = value[2:-2]
        if value.startswith('![[') and value.endswith(']]'):
            value = value[3:-2]
        return value.strip()

    # Maximum aantal boeken per markdown file om performance problemen te voorkomen.
    # Bij twins filter is matching O(n²), dus 1000 boeken = 1.000.000 vergelijkingen.
    # 100 is ruim voldoende voor BookSpineScanner (max ~30 boeken per foto).
    MAX_BOOKS_PER_MARKDOWN = 100

    def extract_all_books_from_markdown(self, filepath: Path) -> List[BookMetadata]:
        """
        Extract metadata for ALL books in a markdown file (for multi-book files).

        Ondersteunt zowel bestanden zonder frontmatter als BookSpineScanner format
        waar frontmatter alleen scan-metadata bevat en boekgegevens erbuiten staan.

        LIMIET: Maximaal MAX_BOOKS_PER_MARKDOWN (100) boeken per file om performance
        te waarborgen. Extra boeken worden genegeerd met een warning.

        Returns:
            List of BookMetadata, one per book found (max 100)
        """
        books = []

        try:
            content = filepath.read_text(encoding='utf-8')
            content = content.replace('\r\n', '\n').replace('\r', '\n')

            # Check for YAML frontmatter
            yaml_match = re.match(r'^---[ \t]*\n(.*?)\n---', content, re.DOTALL)

            # Bepaal welk deel van het bestand we moeten doorzoeken voor multi-book
            if yaml_match:
                # Has frontmatter - check if book metadata is in frontmatter
                yaml_content = yaml_match.group(1)
                cover_field = self.field_names.get('cover', 'cover')
                title_field = self.field_names.get('booktitle', 'booktitle')

                # Check of cover of booktitle in frontmatter staat
                cover_in_fm = re.search(rf'^{re.escape(cover_field)}:', yaml_content, re.MULTILINE | re.IGNORECASE)
                title_in_fm = re.search(rf'^{re.escape(title_field)}:', yaml_content, re.MULTILINE | re.IGNORECASE)

                if cover_in_fm or title_in_fm:
                    # Book metadata is in frontmatter - treat as single book
                    meta = self._extract_markdown(filepath)
                    books.append(meta)
                    return books
                else:
                    # Frontmatter bevat alleen scan-metadata (BookSpineScanner format)
                    # Zoek naar multi-book in de rest van het bestand
                    search_content = content[yaml_match.end():]
            else:
                # No frontmatter - search entire file
                search_content = content

            # Look for multiple cover: entries in search_content
            # Pattern (.*) matcht ook lege waarden - belangrijk voor Libiry2Go output
            # waar boeken zonder cover ook een "cover:" regel hebben
            cover_field = self.field_names.get('cover', 'cover')
            cover_pattern = rf'^{re.escape(cover_field)}:\s*(.*)$'
            cover_matches = list(re.finditer(cover_pattern, search_content, re.MULTILINE | re.IGNORECASE))

            if not cover_matches:
                # No covers found, return single book with filename
                books.append(BookMetadata(booktitle=filepath.stem))
            elif len(cover_matches) == 1:
                # Single cover, use normal extraction
                meta = self._extract_markdown(filepath)
                books.append(meta)
            else:
                # Multiple covers - extract each book's metadata
                # Limiteer aantal boeken voor performance (twins filter is O(n²))
                if len(cover_matches) > self.MAX_BOOKS_PER_MARKDOWN:
                    print(f"WARNING: {filepath.name} contains {len(cover_matches)} books, "
                          f"limiting to {self.MAX_BOOKS_PER_MARKDOWN} for performance. "
                          f"Split the file into smaller files for better results.")
                    cover_matches = cover_matches[:self.MAX_BOOKS_PER_MARKDOWN]

                for i, match in enumerate(cover_matches):
                    # Get content from this cover to next cover (or end of file)
                    start = match.start()
                    end = cover_matches[i + 1].start() if i + 1 < len(cover_matches) else len(search_content)
                    book_content = search_content[start:end]

                    meta = BookMetadata()
                    meta = self._parse_markdown_fields(book_content, meta)

                    # If no title, use cover reference
                    if not meta.booktitle:
                        cover_value = self._clean_field_value(match.group(1))
                        meta.booktitle = Path(cover_value).stem

                    books.append(meta)

        except Exception as e:
            print(f"Multi-book markdown extraction error: {e}")
            books.append(BookMetadata(booktitle=filepath.stem))

        return books
