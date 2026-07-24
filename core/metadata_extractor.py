"""Extract metadata from various ebook formats"""

from pathlib import Path
from typing import Optional, List, Dict
from dataclasses import dataclass, field
import re

@dataclass
class BookMetadata:
    """Container for book metadata
    Field sequence based on Goodreads CSV export for maximum compatibility
    Fields that can be extracted from ebooks automatically:
    - booktitle, authors, isbn: basic identification
    - rating: often Calibre, scale 0-10 internally, 0-5 shown
    - publisher, publication_date, language: publication info
    - tags: genres/subjects (from dc:subject)
    - series, series_index: often Calibre
    - description: summary/description
    Extra fields (EPUB/Calibre):
    - author_sort: opf:file-as
    - translator: dc:contributor with role="trl"
    - illustrator: dc:contributor with role="ill"
    - publication_date
    - pages: Calibre custom or EPUB meta
    Fields for user input:
    - notes
    - cover"""
    
    # Sequence: Goodreads CSV export + extra fields
    cover: str = ""                                  # UI: cover image
    booktitle: str = ""                              # Goodreads: Title
    authors: List[str] = field(default_factory=list) # Goodreads: Author
    author_sort: str = ""                            # Author sort name (opf:file-as)
    isbn: str = ""                                   # ISBN
    rating: Optional[float] = None                   # Goodreads: My Rating (0-10 Calibre, 0-5 shown)
    publisher: str = ""                              # Goodreads: Publisher
    publication_date: str = ""                       # Full publication date (YYYY-MM-DD) or Year published (as in Goodreads)
    language: str = ""                               # Language
    pages: str = ""                                  # Number of pages
    tags: List[str] = field(default_factory=list)    # Goodreads: Bookshelves
    series: str = ""                                 # Series name
    series_index: Optional[float] = None             # Series sequence number
    translator: str = ""                             # Translator (dc:contributor role="trl")
    illustrator: str = ""                            # Illustrator (dc:contributor role="ill")
    description: str = ""                            # Goodreads: My Review
    notes: str = ""                                  # Goodreads: Private Notes

# Central imports - no double code!
from core.libiry_style import (
    DEFAULT_FIELD_NAMES,
    convert_calibre_rating,
)

# =============================================================================
# XML/OPF Namespace Constants (for reuse)
# =============================================================================

# Namespaces. Use Clark notation for reliable matching
DC_NS = 'http://purl.org/dc/elements/1.1/' #Dublin Core namespace
OPF_NS = 'http://www.idpf.org/2007/opf'

# =============================================================================
# XML Helper Functions (central version - no double code!)
# =============================================================================

def has_value(val):
    return val is not None and str(val).strip() != ""

def find_dc_text(metadata_elem, tag: str, dc_ns: str = DC_NS) -> str:
    """Find Dublin Core text element in XML metadata
    Robust helper that works with various namespace variants
    Args:
        metadata_elem: XML element containing metadata
        tag: DC tag name (e.g., 'title', 'creator', 'identifier')
        dc_ns: Dublin Core namespace (default: standard DC namespace)
    Returns Text content of element, or empty string if not found"""
    # Try with full DC namespace (Clark notation)
    elem = metadata_elem.find(f'{{{dc_ns}}}{tag}')
    if elem is not None and elem.text:
        return elem.text.strip()
        
    # Try without namespace
    elem = metadata_elem.find(tag)
    if elem is not None and elem.text:
        return elem.text.strip()
    
    # Search in all children - check }tag and :tag patterns
    # This catches namespace variations (f.e. {ns}tag of prefix:tag)
    for e in metadata_elem:
        if e.tag.endswith(f'}}{tag}') or e.tag.endswith(f':{tag}') or e.tag == tag:
            if e.text:
                return e.text.strip()
    
    # Extra fallback: also search in nested elements (some OPF structures)
    for e in metadata_elem.iter():
        if e.tag.endswith(f'}}{tag}') or e.tag.endswith(f':{tag}') or e.tag == tag:
            if e.text:
                return e.text.strip()

    return ''

class MetadataExtractor:
    """Extract metadata from various ebook formats"""

    def __init__(self, field_names: Dict[str, str] = None):
        """Initialize with optional custom field names
        Args: field_names: Dict mapping standard names to custom names
        e.g. {'cover': 'CoverImage', 'booktitle': 'title'}"""

        self.field_names = DEFAULT_FIELD_NAMES.copy()
        if field_names:
            self.field_names.update(field_names)

    def extract(self, ebook_path: Path, use_sidecar: bool = True) -> BookMetadata:
        """Extract metadata from ebook file
        Args:
        ebook_path: Path to the ebook file
        use_sidecar: read from sidecar as well
        Returns: BookMetadata object with extracted data
        Metadata is read from:
        1. Markdown sidecar file, if it exists
        2. OPF sidecar file, if it exists
        3. E-book itself
        The markdown file always contains all metadata if it exists, the OPF file does not"""

        # STEP 1: Create a new BookMetadata-object
        merged = BookMetadata()
                    
        # STEP 2: For markdown files: get the metadata from there
        sidecar_metadata = None
        suffix = ebook_path.suffix.lower()
        #print(f"DEBUG suffix('{suffix}')")
        if suffix in ('.md', '.markdown'): # Markdown book (book.md): Read metadata from the file itself
            sidecar_metadata =  self.read_markdown_metadata(ebook_path)
        elif use_sidecar == True: #Markdown sidecar (book.pdf.md)
            sidecar_metadata = self.read_markdown_metadata(get_sidecar_path(ebook_path))
        #print(f"DEBUG sidecar_metadata('{sidecar_metadata}')")
        if not sidecar_metadata:
        
            # STEP 3: Read metadata from the file itself
            extractors = {
                '.epub': self._extract_epub,
                '.mobi': self._extract_mobi,
                '.azw3': self._extract_mobi,
                '.azw': self._extract_mobi,
                '.pdf': self._extract_pdf,
                '.cbz': self._extract_comic,
                '.cbr': self._extract_comic,
            }
            extractor = extractors.get(suffix)
            #print(f"DEBUG extractor('{extractor}')")
            native_meta = None

            if extractor:
                try:
                    native_meta = extractor(ebook_path)
                except Exception as e:
                    print(f"Could not read native metadata from {ebook_path}: {e}")
                
                # STEP 4: Read OPF sidecar
                opf_meta = None #init
                if use_sidecar == True:
                    opf_meta = extract_opf(ebook_path)
                    #print(f"DEBUG opf_meta('{opf_meta}')")
                if opf_meta: #When metadata for this book are edited in Libiry or when Calibre2Libiry was used, this will no longer be true
                    
                    # STEP 5: Merge. OPF overwrites native, if filled
                    if has_value(opf_meta.cover):
                        merged.cover = opf_meta.cover
                    elif native_meta: 
                        merged.cover = native_meta.cover
                    if has_value(opf_meta.booktitle): 
                        merged.booktitle = opf_meta.booktitle
                    elif native_meta: 
                        merged.booktitle = native_meta.booktitle
                    if has_value(opf_meta.authors):
                        merged.authors = opf_meta.authors
                    elif native_meta: 
                        merged.authors = native_meta.authors
                    if has_value(opf_meta.author_sort):
                        merged.author_sort = opf_meta.author_sort
                    elif native_meta: 
                        merged.author_sort = native_meta.author_sort
                    if has_value(opf_meta.isbn):
                        merged.isbn = opf_meta.isbn
                    elif native_meta: 
                        merged.isbn = native_meta.isbn
                    if has_value(opf_meta.rating):
                        merged.rating = opf_meta.rating
                    elif native_meta: 
                        merged.rating = native_meta.rating
                    if has_value(opf_meta.publisher):
                        merged.publisher = opf_meta.publisher
                    elif native_meta: 
                        merged.publisher = native_meta.publisher
                    if has_value(opf_meta.publication_date):
                        merged.publication_date = opf_meta.publication_date
                    elif native_meta: 
                        merged.publication_date = native_meta.publication_date
                    if has_value(opf_meta.language):
                        merged.language = opf_meta.language
                    elif native_meta: 
                        merged.language = native_meta.language
                    if has_value(opf_meta.pages):
                        merged.pages = opf_meta.pages
                    elif native_meta:
                        merged.pages = native_meta.pages
                    if has_value(opf_meta.tags):
                        merged.tags = opf_meta.tags
                    elif native_meta:
                        merged.tags = native_meta.tags
                    if has_value(opf_meta.series):
                        merged.series = opf_meta.series
                    elif native_meta:
                        merged.series = native_meta.series
                    if has_value(opf_meta.series_index):
                        merged.series_index = opf_meta.series_index
                    elif native_meta:
                        merged.series_index = native_meta.series_index
                    if has_value(opf_meta.translator):
                        merged.translator = opf_meta.translator
                    elif native_meta:
                        merged.translator = native_meta.translator
                    if has_value(opf_meta.illustrator):
                        merged.illustrator = opf_meta.illustrator
                    elif native_meta:
                        merged.illustrator = native_meta.illustrator
                    if has_value(opf_meta.description):
                        merged.description = opf_meta.description
                    elif native_meta:
                        merged.description = native_meta.description
                    if has_value(opf_meta.notes):
                        merged.notes = opf_meta.notes
                    elif native_meta:
                        merged.notes = native_meta.notes

                elif native_meta:
                    merged = native_meta #Native metadata exist, and no OPF or MD exists
             
        # STEP 6: Fill metadata from the sidecar
        else:
            if sidecar_metadata.cover:
                merged.cover = sidecar_metadata.cover # Don't worry, this info will ONLY be written to markdown files, covers in epub/cbz are not updated
            if sidecar_metadata.tags:
                merged.tags = sidecar_metadata.tags                
            if sidecar_metadata.booktitle:
                merged.booktitle = sidecar_metadata.booktitle
            if sidecar_metadata.authors:
                merged.authors = sidecar_metadata.authors
            # Copy all other fields
            for field in ['author_sort', 'isbn', 'rating', 'publisher', 
                          'publication_date', 'language', 'pages', 'series', 'series_index', 'translator', 'illustrator', 'description', 'notes']:
                val = getattr(sidecar_metadata, field, None)
                if val is not None and val != '':
                    setattr(merged, field, val)
                    
        # Fill merged.booktitle with file name, if empty
        if not has_value(merged.booktitle):
            merged.booktitle = ebook_path.stem
                    
        #print(f"DEBUG after STEP6 merged.booktitle: '{merged.booktitle}'")
        #print(f"DEBUG sidecar_metadata.booktitle: '{sidecar_metadata.booktitle}'")

        return merged

    def _extract_epub(self, ebook_path: Path) -> BookMetadata:
        """Extract metadata from EPUB file
        Try several methods:
        1. Direct OPF parsing (most reliable, works with EPUB 2.0 en 3.0)
        2. ebookmeta library
        3. ebooklib library
        EPUB 3.0 files (like those from Calibre) use id-attributes
        on dc:title and dc:creator elements that some libraries cannot process.
        Direct OPF parsing solves this"""
        meta = BookMetadata(booktitle=ebook_path.stem)

        # Method 1: Direct OPF parsing - most reliable for EPUB 2.0 and 3.0
        try:
            meta = self._extract_epub_direct(ebook_path, meta)
            # If we found the title, we are finished
            if meta.booktitle and meta.booktitle != ebook_path.stem:
                return meta
        except Exception as e:
            print(f"Direct OPF parsing error: {e}")

        # Method 2: ebookmeta library
        try:
            from ebookmeta import get_metadata
            book_meta = get_metadata(str(ebook_path))

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

            if meta.booktitle and meta.booktitle != ebook_path.stem:
                return meta

        except ImportError:
            pass
        except Exception as e:
            print(f"ebookmeta error: {e}")

        # Method 3: ebooklib library
        try:
            import ebooklib
            from ebooklib import epub
            book = epub.read_epub(str(ebook_path))

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
                    meta.publication_date = year_match.group(1)

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

    def _extract_epub_direct(self, ebook_path: Path, meta: BookMetadata) -> BookMetadata:
        """Extract metadata directly from EPUB OPF file
        EPUB is a ZIP file containing an OPF file with metadata
        This method parses the OPF XML directly, which is more reliable for EPUB 2.0 and EPUB 3.0 formats
        EPUB 3.0 (like Calibre produces) uses id attributes:
          <dc:title id="id-1">Title</dc:title>
          <dc:creator id="id-2">Author</dc:creator>
        EPUB 2.0 doesn't use id attributes:
          <dc:title>Title</dc:title>
          <dc:creator opf:role="aut">Author</dc:creator>
        Both formats are processed correctly"""
        
        import zipfile
        import xml.etree.ElementTree as ET

        with zipfile.ZipFile(ebook_path, 'r') as zf:
            # Find the OPF file via container.xml
            try:
                container_xml = zf.read('META-INF/container.xml')
                container = ET.fromstring(container_xml)

                # Find rootfile element
                ns = {'c': 'urn:oasis:names:tc:opendocument:xmlns:container'}
                rootfile = container.find('.//c:rootfile', ns)
                if rootfile is None:
                    # Try without namespace
                    rootfile = container.find('.//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile')

                if rootfile is not None:
                    opf_path = rootfile.get('full-path')
                else:
                    # Fallback: search for .opf file
                    opf_files = [n for n in zf.namelist() if n.endswith('.opf')]
                    opf_path = opf_files[0] if opf_files else None

                if not opf_path:
                    return meta

                # Read and parse OPF file
                opf_content = zf.read(opf_path)
                opf = ET.fromstring(opf_content)

                # Find metadata element
                metadata = opf.find(f'{{{OPF_NS}}}metadata')
                if metadata is None:
                    metadata = opf.find('metadata')
                if metadata is None:
                    return meta

                # Extract dc:title
                title_elem = metadata.find(f'{{{DC_NS}}}title')
                if title_elem is not None and title_elem.text:
                    meta.booktitle = title_elem.text.strip()

                # Extract dc:creator (authors) and author_sort (opf:file-as)
                authors = []
                author_sort = ""
                for creator in metadata.findall(f'{{{DC_NS}}}creator'):
                    if creator.text:
                        authors.append(creator.text.strip())
                        # opf:file-as attribute contains sort name (f.e. "Last name, Given name")
                        file_as = creator.get(f'{{{OPF_NS}}}file-as') or creator.get('opf:file-as')
                        if file_as and not author_sort:
                            author_sort = file_as.strip()
                if authors:
                    meta.authors = authors
                if author_sort:
                    meta.author_sort = author_sort

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
                    date_text = date_elem.text.strip()
                    meta.publication_date = date_text

                # Extract dc:contributor (translator, illustrator)
                # opf:role attribute indicates the role: trl=translator, ill=illustrator
                # We must try different ways to read the role attribute, because not all EPUB generators store it in the same manner
                translators = []
                illustrators = []

                # Helper to find role attribute (different namespace variants)
                def get_role(elem):
                    # Full OPF namespace (Clark notation)
                    role = elem.get(f'{{{OPF_NS}}}role')
                    if role:
                        return role.lower()
                    # No namespace (some EPUBs)
                    role = elem.get('role')
                    if role:
                        return role.lower()
                    # Search through all attributes for something ending on 'role'
                    for attr_name, attr_val in elem.attrib.items():
                        if attr_name.endswith('role') or attr_name.endswith('}role'):
                            return attr_val.lower()
                    return ''

                # Find contributors with DC namespace
                for contributor in metadata.findall(f'{{{DC_NS}}}contributor'):
                    if contributor.text:
                        name = contributor.text.strip()
                        role = get_role(contributor)
                        if role == 'trl':
                            translators.append(name)
                        elif role == 'ill':
                            illustrators.append(name)

                # Find contributors without namespace (sommige old EPUBs)
                for contributor in metadata.findall('contributor'):
                    if contributor.text:
                        name = contributor.text.strip()
                        role = get_role(contributor)
                        if role == 'trl' and name not in translators:
                            translators.append(name)
                        elif role == 'ill' and name not in illustrators:
                            illustrators.append(name)

                if translators:
                    meta.translator = ', '.join(translators)
                if illustrators:
                    meta.illustrator = ', '.join(illustrators)

                # Extract dc:subject (tags)
                tags = []
                for subject in metadata.findall(f'{{{DC_NS}}}subject'):
                    if subject.text:
                        tags.append(subject.text.strip())
                if tags:
                    meta.tags = tags

                # Extract Calibre-style metadata from <meta> elements
                # Search with and without OPF namespace (both exist)
                meta_elements = metadata.findall(f'{{{OPF_NS}}}meta')
                meta_elements.extend(metadata.findall('meta'))

                for meta_elem in meta_elements:
                    name = meta_elem.get('name', '')
                    content = meta_elem.get('content', '')

                    if name == 'calibre:series' and content:
                        meta.series = content
                    elif name == 'calibre:series_index' and content:
                        try:
                            meta.series_index = float(content)
                        except (ValueError, TypeError):
                            pass
                    elif name == 'calibre:rating' and content:
                        # Calibre uses 0-10, we show 0-5
                        try:
                            calibre_rating = float(content)
                            meta.rating = calibre_rating / 2.0
                        except (ValueError, TypeError):
                            pass
                    elif name == 'calibre:user_notes' and content:
                        meta.notes = content
                    # Pages can be stored in various Calibre custom columns
                    elif name in ('calibre:user_metadata:#pages', 'calibre:pages') and content:
                        meta.pages = content

                # Also search for source/page-count in standard meta elements
                for meta_elem in meta_elements:
                    prop = meta_elem.get('property', '')
                    if prop == 'rendition:page-count' and meta_elem.text:
                        meta.pages = meta_elem.text.strip()

            except Exception as e:
                print(f"Error parsing OPF: {e}")

        return meta

    def _extract_mobi(self, ebook_path: Path) -> BookMetadata:
        """Extracts metadata from MOBI/AZW3 file
        Tries multiple libraries for basic metadata:
        1. ebookmeta - for title, author etc.
        2. mobi - as fallback for basic metadata
        Tags are never read from ebookmeta, it's unreliable"""
        meta = BookMetadata(booktitle=ebook_path.stem)

        # Method 1: ebookmeta library
        try:
            from ebookmeta import get_metadata
            book_meta = get_metadata(str(ebook_path))

            if book_meta.title:
                meta.booktitle = book_meta.title
            if book_meta.author_list:
                meta.authors = list(book_meta.author_list)
            elif book_meta.author:
                meta.authors = [book_meta.author]
            if hasattr(book_meta, 'publish_info') and book_meta.publish_info:
                meta.publisher = book_meta.publish_info
            if hasattr(book_meta, 'lang') and book_meta.lang:
                meta.language = book_meta.lang

        except ImportError:
            # Method 2: mobi library as fallback
            try:
                from mobi import Mobi
                book = Mobi(str(ebook_path))
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
                pass
            except Exception:
                pass
        except Exception:
            pass

        return meta

    def _extract_pdf(self, ebook_path: Path) -> BookMetadata:
        """Reads native PDF metadata (title, author, keywords/tags)"""
        meta = BookMetadata(booktitle=ebook_path.stem)

        try:
            try:
                import pymupdf as fitz
            except ImportError:
                import fitz
            doc = fitz.open(str(ebook_path))
            pdf_meta = doc.metadata

            if pdf_meta:
                if pdf_meta.get('title'):
                    meta.booktitle = pdf_meta['title']

                if pdf_meta.get('author'):
                    # Split authors by unambiguous separators only
                    # Do NOT split on comma - "Last, First" is valid single author
                    authors_str = pdf_meta['author']
                    for sep in [';', '&', ' and ']:
                        if sep in authors_str:
                            meta.authors = [a.strip() for a in authors_str.split(sep)]
                            break
                    else:
                        meta.authors = [authors_str]

                # Tags: Calibre and many ebook tools save tags in the 'subject' field
                # The 'keywords' field often contains irrelevant data like URLs or generator info
                # Therefore: subject first, keywords as fallback
                # Handle newlines and commas
                # Tags are separated by ', ' (komma-space) - consistent with writing
                if pdf_meta.get('subject'):
                    subject = pdf_meta['subject'].strip()
                    # Subject values may use comma-space OR bare newlines as separators (tool-dependent)
                    raw = re.split(r',\s*|\r\n|\r|\n', subject)
                    meta.tags = [t.strip() for t in raw if t.strip()]
                elif pdf_meta.get('keywords'):
                    meta.tags = [pdf_meta['keywords'].strip()]

                # Note: The PDF 'producer' field is for the software that created the PDF (f.e. "Adobe Acrobat"), not for the book publisher

            doc.close()

        except ImportError:
            # Fallback to PyPDF2
            try:
                from PyPDF2 import PdfReader
                reader = PdfReader(str(ebook_path))
                info = reader.metadata

                if info:
                    if info.title:
                        meta.booktitle = info.title
                    if info.author:
                        meta.authors = [info.author]

            except ImportError:
                pass
        except Exception as e:
            print(f"PDF native metadata error: {e}")

        return meta

    def _extract_comic(self, ebook_path: Path) -> BookMetadata:
        """Extract metadata from CBZ/CBR comic archive
        Both formats read ComicInfo.xml for all fields on first read
        CBZ: native ZIP, no extra library needed
        CBR: requires rarfile library"""
        import xml.etree.ElementTree as ET
        meta = BookMetadata(booktitle=ebook_path.stem)
        is_cbr = ebook_path.suffix.lower() == '.cbr'

        if not is_cbr:
        # CBZ: read ComicInfo.xml from ZIP archive
            try:
                import zipfile
                with zipfile.ZipFile(ebook_path, 'r') as zf:
                    # Case-insensitive search for ComicInfo.xml
                    comicinfo_name = next(
                        (n for n in zf.namelist() if n.lower() == 'comicinfo.xml'), None)
                    if comicinfo_name:
                        xml_content = zf.read(comicinfo_name).decode('utf-8')
                        self._apply_comicinfo_xml(ET.fromstring(xml_content), ebook_path, meta)
            except Exception as e:
                # Log exception for debugging, but continue with fallbacks
                print(f"Error reading ComicInfo.xml from {ebook_path}: {e}")
        else:
            # CBR: read ComicInfo.xml from RAR archive
            try:
                import rarfile
                with rarfile.RarFile(ebook_path, 'r') as rf:
                    comicinfo_name = next(
                        (n for n in rf.namelist() if n.lower() == 'comicinfo.xml'), None)
                    if comicinfo_name:
                        xml_content = rf.read(comicinfo_name).decode('utf-8')
                        self._apply_comicinfo_xml(ET.fromstring(xml_content), ebook_path, meta)
            except ImportError:
                pass  # rarfile not installed; comicbox fallback below may help
            except Exception as e:
                print(f"Error reading ComicInfo.xml from {ebook_path}: {e}")

        # comicbox fallback: fills title/series/author/publisher when still missing
        if not meta.booktitle or meta.booktitle == ebook_path.stem:
            try:
                from comicbox.comic_archive import ComicArchive
                car = ComicArchive(ebook_path)
                comic_meta = car.get_metadata()
                if comic_meta:
                    if hasattr(comic_meta, 'series') and comic_meta.series:
                        meta.series = comic_meta.series
                    if hasattr(comic_meta, 'title') and comic_meta.title:
                        meta.booktitle = comic_meta.title
                    if hasattr(comic_meta, 'issue') and comic_meta.issue:
                        try:
                            meta.series_index = float(comic_meta.issue)
                        except (ValueError, TypeError):
                            pass
                    if hasattr(comic_meta, 'writer') and comic_meta.writer:
                        meta.authors = ([comic_meta.writer]
                                        if isinstance(comic_meta.writer, str)
                                        else list(comic_meta.writer))
                    if hasattr(comic_meta, 'publisher') and comic_meta.publisher:
                        meta.publisher = comic_meta.publisher
            except ImportError:
                pass
            except Exception:
                pass

        return meta

    def _apply_comicinfo_xml(self, root, ebook_path: Path, meta: BookMetadata):
        """Apply all fields from a parsed ComicInfo.xml root element to meta"""
        title_elem = root.find('Title')
        if title_elem is not None and title_elem.text:
            meta.booktitle = title_elem.text

        series_elem = root.find('Series')
        if series_elem is not None and series_elem.text:
            meta.series = series_elem.text

        tags_elem = root.find('Tags')
        if tags_elem is not None and tags_elem.text:
            meta.tags = [t.strip() for t in tags_elem.text.split(',') if t.strip()]

        writer_elem = root.find('Writer')
        if writer_elem is not None and writer_elem.text:
            meta.authors = [writer_elem.text]

        publisher_elem = root.find('Publisher')
        if publisher_elem is not None and publisher_elem.text:
            meta.publisher = publisher_elem.text

        number_elem = root.find('Number')
        if number_elem is not None and number_elem.text:
            try:
                meta.series_index = float(number_elem.text)
            except (ValueError, TypeError):
                pass

        year_elem = root.find('Year')
        if year_elem is not None and year_elem.text:
            meta.publication_date = year_elem.text

        lang_elem = root.find('LanguageISO')
        if lang_elem is not None and lang_elem.text:
            meta.language = lang_elem.text

        summary_elem = root.find('Summary')
        if summary_elem is not None and summary_elem.text:
            meta.description = summary_elem.text

        notes_elem = root.find('Notes')
        if notes_elem is not None and notes_elem.text:
            meta.notes = notes_elem.text

        pages_elem = root.find('PageCount')
        if pages_elem is not None and pages_elem.text:
            meta.pages = pages_elem.text

        rating_elem = root.find('CommunityRating')
        if rating_elem is not None and rating_elem.text:
            try:
                meta.rating = float(rating_elem.text)
            except (ValueError, TypeError):
                pass

        # Illustrator from Penciller field
        penciller_elem = root.find('Penciller')
        if penciller_elem is not None and penciller_elem.text:
            meta.illustrator = penciller_elem.text

        # Translator (not standard but we support it)
        translator_elem = root.find('Translator')
        if translator_elem is not None and translator_elem.text:
            meta.translator = translator_elem.text

    def _extract_isbn(self, identifier: str) -> str:
        """Extract ISBN from identifier string
        Deletes known prefixes. If the value contains exactly 10 or 13 digits,
        a cleaned up version (only digits/X) is returned, otherwise the original value is returned
        UUID values (urn:uuid:) are ignored"""
        import re

        if not identifier:
            return ""

        identifier = str(identifier).strip()

        # Skip UUID values - this is no ISBN
        if identifier.lower().startswith('urn:uuid:'):
            return ""

        # Remove common prefixes (case-insensitive)
        identifier_upper = identifier.upper()
        for prefix in ['ISBN:', 'ISBN-10:', 'ISBN-13:', 'URN:ISBN:']:
            if identifier_upper.startswith(prefix):
                identifier = identifier[len(prefix):].strip()
                break

        # Clean version: only digits and X
        cleaned = re.sub(r'[^0-9X]', '', identifier.upper())

        # As exactly 10 or 13 digits: return cleaned up version
        if len(cleaned) in (10, 13):
            return cleaned

        # Otherwise: return original value
        return identifier

    def _normalize_tags(self, tags: List[str]) -> List[str]:
        """Normalize tags: trim, delete empty and duplicates
        Keeps original sequence (first occurrence) and case"""
        seen = set()
        normalized = []
        for tag in tags:
            tag_stripped = tag.strip()
            if tag_stripped and tag_stripped not in seen:
                seen.add(tag_stripped)
                normalized.append(tag_stripped)
        return normalized

    def _clean_field_value(self, value: str) -> str:
        """Clean field value by removing quotes, brackets and whitespace"""
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

    def _parse_tags_from_yaml(self, tags_str: str) -> List[str]:
        """Parses tags from YAML and deletes quotes from the output
        Supports:
        - YAML block list: "  - fiction\\n  - sci-fi"  (valid in Obsidian)
        - Comma-separated: fiction, sci-fi
        - Tags in quotes: fiction, "Brando, Marlon", sci-fi
        - YAML array: [fiction, "sci fi"] -> reads it, but saves it as a YAML block list"""
        if not tags_str:
            return []

        tags_str = tags_str.strip()

        # Format 1: YAML block list with "- item" syntax (Obsidian-compatible)
        if '\n' in tags_str or tags_str.startswith('-'):
            tags = []
            for line in tags_str.split('\n'):
                line = line.strip()
                if line.startswith('-'):
                    # Remove the "- " prefix
                    tag = line[1:].strip()
                    # Remove quotes if aanwezig
                    if (tag.startswith('"') and tag.endswith('"')) or \
                       (tag.startswith("'") and tag.endswith("'")):
                        tag = tag[1:-1]
                    # Unescape quotes
                    tag = tag.replace('\\"', '"').replace("\\'", "'")
                    if tag:
                        tags.append(tag)
            if tags:
                return self._normalize_tags(tags)

        # Format 2: YAML array format: [tag1, tag2]
        if tags_str.startswith('[') and tags_str.endswith(']'):
            tags_str = tags_str[1:-1]

        # Format 3: Comma-separated (including tags in quotes)
        tags = []
        current = ''
        in_quotes = False
        quote_char = None
        i = 0

        while i < len(tags_str):
            char = tags_str[i]

            if char in ('"', "'") and not in_quotes:
                # Start of quoted string
                in_quotes = True
                quote_char = char
            elif char == quote_char and in_quotes:
                # End of quoted string (check for escaped quote)
                if i > 0 and tags_str[i-1] == '\\':
                    # Escaped quote - add to current
                    current = current[:-1] + char  # Verwijder backslash, add quote
                else:
                    in_quotes = False
                    quote_char = None
            elif char == ',' and not in_quotes:
                # Separator found
                tag = current.strip()
                if tag:
                    tags.append(tag)
                current = ''
            else:
                current += char

            i += 1

        # Last tag
        tag = current.strip()
        if tag:
            tags.append(tag)

        return self._normalize_tags(tags)

    def read_markdown_metadata(self, markdown_path: Path) -> Optional[BookMetadata]:
        """Read all metadata from a Markdown sidecar file (YAML frontmatter)
        Reads: booktitle, author, isbn, publisher, language, description, tags, series, series_index, rating, notes, author_sort, publication_date, pages, translator, illustrator
        Args: markdown_path: Path to the markdown file (either a book or a sidecar)
        Returns: BookMetadata object with all found fields, or None if sidecar doesn't exist"""
        # Gives back a BookMetadata with markdown_path.stem as fallback title
        meta = BookMetadata(booktitle=markdown_path.stem)

        if not markdown_path.exists():
            return None

        try:
            content = markdown_path.read_text(encoding='utf-8', errors='replace')
            content = content.replace('\r\n', '\n').replace('\r', '\n')

            # Check for YAML frontmatter (between --- and ---)
            yaml_match = re.match(r'^---[ \t]*\n(.*?)\n---', content, re.DOTALL)
            if yaml_match:
                # YAML frontmatter exists - parse metadata from it
                yaml_content = yaml_match.group(1)

                # Helper to find YAML field value with configured field name
                # Supports single-line values and multi-line values (with or without |)
                def find_field(standard_name: str) -> str:
                    # First try multi-line: field: followed by indented lines
                    # This works with or without the | character
                    # Pattern: field: [optional | or >] newline, then indented content
                    field_name = self.field_names.get(standard_name, standard_name) # from 'booktitle' to 'booktitlecustomfieldname'
                    #print(f"DEBUG find_field('{standard_name}') -> searches for '{field_name}'")
                    pattern_multi = rf'^{re.escape(field_name)}:\s*[|>]?\s*\n((?:[ \t]+.+\n?)+)'
                    match_multi = re.search(pattern_multi, yaml_content, re.MULTILINE | re.IGNORECASE)
                
                    if match_multi:
                        result = match_multi.group(1).strip()
                        # Reject if result starts at column 0 with a field pattern (not indented content) (so reject if the field you're looking for is not in the YAML frontmatter, and the result is another field)
                        first_line = match_multi.group(1).split('\n')[0]
                        if not first_line.startswith(' ') and not first_line.startswith('\t') and re.match(r'^\w+\s*:', first_line):
                            pass  # fall through to single-line check
                        else:
                            # Remove indentation from each line
                            lines = match_multi.group(1).split('\n')
                            # Determine minimum indentation
                            min_indent = float('inf')
                            for line in lines:
                                if line.strip():
                                    indent = len(line) - len(line.lstrip())
                                    min_indent = min(min_indent, indent)
                            if min_indent == float('inf'):
                                min_indent = 0
                            # Remove minimum indentation from each line
                            cleaned_lines = []
                            for line in lines:
                                if len(line) >= min_indent:
                                    cleaned_lines.append(line[int(min_indent):])
                                else:
                                    cleaned_lines.append(line.lstrip())
                            return '\n'.join(cleaned_lines).strip()

                    # Fallback: try single-line (field: value on same line)
                    #print(f"DEBUG pattern: {repr(rf'^{re.escape(field_name)}:\s*([^\n]+)$')}")
                    # Beware: \s* matches spaces AND newlines, so booktitlecustomname:\n + authorcustomname: matches if: field name + : + \s*(the newline) + ([^\n]+)(the next line).
                    # So no \s*, but [^\S\n]* instead (spaces but no newlines):
                    # pattern = rf'^{re.escape(field_name)}:\s*([^\n]+)$'
                    pattern = rf'^{re.escape(field_name)}:[^\S\n]*([^\n]+)$'
                    match = re.search(pattern, yaml_content, re.MULTILINE | re.IGNORECASE)
                    #print(f"DEBUG single-line '{field_name}': match={match.group(0) if match else 'GEEN'}")
                    if match:
                        #print(f"DEBUG single-line found: '{match.group(0)}'")
                        #print(f"DEBUG find_field('{standard_name}') -> found: '{match.group(1)}'")
                        value = match.group(1).strip()
                        # Remove surrounding quotes
                        if (value.startswith('"') and value.endswith('"')) or \
                           (value.startswith("'") and value.endswith("'")):
                            value = value[1:-1]
                        return value

                    return ''

                # Parse fields
                print(f"DEBUG yaml_content repr: {repr(yaml_content[:100])}")
                meta.cover = find_field('cover')
                meta.booktitle = find_field('booktitle')
                #print(f"DEBUG meta.booktitle in SR: '{meta.booktitle if meta else 'NO META'}'")
            
                # Author can be a string or a list
                author_str = find_field('author')
                if author_str:
                    # Check if it's a YAML array format
                    if author_str.startswith('[') and author_str.endswith(']'):
                        # YAML array: [Author One, Author Two] or ["Last, First", "Other Author"]
                        # Split on comma but respect quotes
                        authors = []
                        inner = author_str[1:-1]
                        # Simple quoted string handling
                        parts = []
                        current = ''
                        in_quotes = False
                        quote_char = None
                        for char in inner:
                            if char in ('"', "'") and not in_quotes:
                                in_quotes = True
                                quote_char = char
                            elif char == quote_char and in_quotes:
                                in_quotes = False
                                quote_char = None
                            elif char == ',' and not in_quotes:
                                parts.append(current.strip().strip('"\''))
                                current = ''
                                continue
                            current += char
                        if current.strip():
                            parts.append(current.strip().strip('"\''))
                        meta.authors = [a for a in parts if a]
                    else:
                        # Single author string - do NOT split on comma
                        # because "Last, First" is a valid single author name
                        # Multiple authors should use YAML array format
                        meta.authors = [author_str]

                meta.author_sort = find_field('author_sort')
                meta.isbn = find_field('isbn')

                # Rating
                rating_str = find_field('rating')
                if rating_str:
                    try:
                        meta.rating = float(rating_str)
                    except (ValueError, TypeError):
                        pass

                meta.publisher = find_field('publisher')
                meta.publication_date = find_field('publication_date')
                meta.language = find_field('language')
                meta.pages = find_field('pages')

                # Tags - Supports tags in two formats:
                # 1. YAML list: tags: [fiction, sci-fi] of tags:\n  - fiction\n  - sci-fi
                # 2. Comma separated: tags: fiction, sci-fi
                tags_str = find_field('tags')
                if tags_str:
                    meta.tags = self._parse_tags_from_yaml(tags_str)

                meta.series = find_field('series')

                # Series index
                series_index_str = find_field('series_index')
                if series_index_str:
                    try:
                        meta.series_index = float(series_index_str)
                    except (ValueError, TypeError):
                        pass

                meta.translator = find_field('translator')
                meta.illustrator = find_field('illustrator')
                meta.description = find_field('description')
                meta.notes = find_field('notes')
        
            # No frontmatter = no metadata (filename is set as booktitle)
        
        except Exception as e:
            print(f"Error reading markdown metadata from {markdown_path}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
        return meta

# =============================================================================
# Markdown sidecar file helpers
# =============================================================================
# Markdown sidecar files are used for metadata storage when:
# formaten waar metadata niet direct in het bestand kan worden opgeslagen:
# - CBR (RAR formaat, niet schrijfbaar)
# - MOBI/AZW/AZW3 (ebookmeta library is onbetrouwbaar)
# - Problematische PDFs (sommige PDFs ondersteunen geen metadata wijzigingen)
#
# The sidecar file has the same name as the ebook but with an .md extension.
# F.e. book.cbr -> book.cbr.md
#
# Structure: YAML frontmatter with ALL metadata fields.
# Tags with commas are quoted in the file but the quotes are suppressed in the UI.
# =============================================================================

import unicodedata

def clean_description(value):
    '''Cleans up text in YAML frontmatter for use in Obsidian
    Strips HTML tags and fixes encoding. Beautifulsoup4 and ftfy are optional; graceful degradation if not installed
    From:
    <b><i>"</i>Wonderful." <b><i>&#8212;</i>Michiko Kakutani, <i>New York Times</i></b><br>Celebrating the 20th
    anniversary  of storytelling phenomenon The Moth...
    To:
    "Wonderful." —Michiko Kakutani, New York Times
    Celebrating the 20th anniversary of storytelling phenomenon The Moth...'''

    if not value:
        return value

    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(value, "html.parser")

        # Convert <br> to newline so paragraph breaks survive tag stripping
        for br in soup.find_all('br'):
            br.replace_with('\n')

        # Append newline inside block-level elements so their text ends on its own line
        for tag in soup.find_all(['p', 'div', 'li', 'h1', 'h2', 'h3', 'h4']):
            tag.append('\n')

        text = soup.get_text()
    except ImportError:
        text = re.sub(r'<br\s*/?>', '\n', value, flags=re.IGNORECASE)
        text = re.sub(r'<[^>]+>', '', text)

    # Fix mojibake and normalize Unicode
    try:
        import ftfy
        text = ftfy.fix_text(text)
    except ImportError:
        pass
        
    text = unicodedata.normalize("NFKC", text)

    # Collapse horizontal whitespace within each line, but keep newlines
    lines = [' '.join(line.split()) for line in text.split('\n')]
    text = '\n'.join(lines).strip()

    # Cap consecutive blank lines at one (two newlines = one blank line)
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text

def find_cover_for_ebook(ebook_path: Path) -> Optional[str]:
    """Find the cover file for an ebook and return its filename.
    Looks for cover files in the same folder as the ebook with the pattern:
    {ebook_name}.{cover_ext} (e.g., book.pdf.jpg, book.epub.png)
    Args: ebook_path: Path to the ebook file
    Returns: cover filename (e.g., "book.pdf.png") if found, None otherwise"""
    COVER_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
    folder = ebook_path.parent
    ebook_name = ebook_path.name

    # Look for cover with pattern: book.pdf.jpg, book.pdf.png, etc.
    for ext in COVER_EXTENSIONS:
        cover_name = ebook_name + ext
        cover_path = folder / cover_name
        if cover_path.exists():
            return cover_name

    return None
    
def modify_markdown_metadata(ebook_path: Path, markdown_path: Path, metadata: dict, field_names: dict = None) -> bool:
    """Writes metadata to a markdown (book or sidecar) file (YAML frontmatter)
    Create a new file or update an existing one
    Keep content that is not in Libiry's metadata
    Always writes tags as YAML block list (Obsidian-compatible)
    Write ALL Libiry fields, including the empty ones (because they override potential filled metadata in the ebook)
    Args:
        markdown_path: Path to the markdown file
        metadata: Dict with metadata fields
        field_names: Optional mapping to customized field names
    Returns True if succesful, False if unsuccesful"""
    field_names = field_names or {}
    tags_field = field_names.get('tags', 'tags')
    
    try:
        
        # Strip HTML and fix encoding in description/notes before writing to YAML
        metadata = dict(metadata)  # Never mutate the original
        for _key in ('description', 'notes'):
            if metadata.get(_key):
                metadata[_key] = clean_description(metadata[_key])

        # Cover file detection: inject cover if not already present in metadata
        if ebook_path is not None: # Just to make sure
            cover_field = field_names.get('cover', 'cover') # Get customized cover field name
            #print(f"DEBUG cover field('{cover_field}') -> searches for '{cover_field}'")
            if not metadata.get(cover_field) and not metadata.get('cover'): # If cover still empty
                cover_filename = find_cover_for_ebook(ebook_path)
                if cover_filename:
                    metadata[cover_field] = cover_filename

        # Read existing content
        if markdown_path.exists():
            content = markdown_path.read_text(encoding='utf-8', errors='replace')
            content = content.replace('\r\n', '\n').replace('\r', '\n')
        else:
            content = ''

        if not content.startswith('---'): # No frontmatter - add it
            frontmatter_lines = ['---']
            for key, value in metadata.items():
                field_name = field_names.get(key, key)
                if key == 'tags' and isinstance(value, list):
                    frontmatter_lines.extend(_format_tags_for_yaml(value, tags_field))
                elif key == 'tags' and isinstance(value, str):
                    tag_list = [t.strip() for t in value.split(',') if t.strip()]
                    frontmatter_lines.extend(_format_tags_for_yaml(tag_list, tags_field))
                elif key in ('description', 'notes') and value and '\n' in str(value):
                    frontmatter_lines.append(f"{field_name}: |")
                    for line in str(value).split('\n'):
                        frontmatter_lines.append(f"  {line}")
                else:
                    frontmatter_lines.append(f"{field_name}: {value if value is not None else ''}")
            frontmatter_lines.append('---')
            frontmatter_lines.append('')
            markdown_path.write_text('\n'.join(frontmatter_lines) + content, encoding='utf-8')
            return True

        second_dash = content.find('---', 3)
        if second_dash == -1:
            return False  # Invalid frontmatter

        frontmatter = content[3:second_dash].strip()
        body = content[second_dash + 3:]

        # Update existing frontmatter
        new_lines = []
        updated_fields = set()
        skip_block_items = False

        for line in frontmatter.split('\n'):
            if skip_block_items:
                if re.match(r'^\s+-\s+', line):
                    continue
                else:
                    skip_block_items = False

            updated = False
            for key, value in metadata.items():
                field_name = field_names.get(key, key)
                if re.match(rf'^{re.escape(field_name)}:\s*', line, re.IGNORECASE):
                    # Always write, even if value is empty
                    if key == 'tags' and isinstance(value, list):
                        new_lines.extend(_format_tags_for_yaml(value, tags_field))
                        skip_block_items = True
                    elif key == 'tags' and isinstance(value, str):
                        tag_list = [t.strip() for t in value.split(',') if t.strip()]
                        new_lines.extend(_format_tags_for_yaml(tag_list, tags_field))
                        skip_block_items = True
                    elif key in ('description', 'notes') and value and '\n' in str(value):
                        new_lines.append(f"{field_name}: |")
                        for l in str(value).split('\n'):
                            new_lines.append(f"  {l}")
                    else:
                        new_lines.append(f"{field_name}: {value if value is not None else ''}")
                    updated_fields.add(key)
                    updated = True
                    break
            if not updated:
                new_lines.append(line)

        # Add new fields (even if they're empty)
        for key, value in metadata.items():
            if key not in updated_fields:
                field_name = field_names.get(key, key)
                if key == 'tags' and isinstance(value, list):
                    new_lines.extend(_format_tags_for_yaml(value, tags_field))
                elif key == 'tags' and isinstance(value, str):
                    tag_list = [t.strip() for t in value.split(',') if t.strip()]
                    new_lines.extend(_format_tags_for_yaml(tag_list, tags_field))
                elif key in ('description', 'notes') and value and '\n' in str(value):
                    new_lines.append(f"{field_name}: |")
                    for l in str(value).split('\n'):
                        new_lines.append(f"  {l}")
                else:
                    new_lines.append(f"{field_name}: {value if value is not None else ''}")

        result = '---\n' + '\n'.join(new_lines) + '\n---' + body
        markdown_path.write_text(result, encoding='utf-8')
        
        return True

    except Exception as e:
        print(f"Error writing markdown metadata to {markdown_path}: {e}")
        return False

def modify_markdown_tags(ebook_path: Path, markdown_path: Path, tags_to_remove: set, tags_to_add: set, field_names: dict = None) -> bool:
    """Modify tags in a Markdown file. Supports multi-tag maintenance
    Args:
        markdown_path: Path to the markdown file
        tags_to_remove: case-sensitive
        tags_to_add: case-sensitive
    Returns True when edits have been made, False otherwise"""
    # Read current metadata 
    current_meta = MetadataExtractor().read_markdown_metadata(markdown_path)
    current_tags = current_meta.tags if current_meta else []

    # Edit tags - remove tags (case-sensitive)
    new_tags = [t for t in current_tags if t not in tags_to_remove]
    removed_count = len(current_tags) - len(new_tags)

    # Add all new tags (case-sensitive)
    tags_added = []
    for tag_to_add in sorted(tags_to_add):  # Sort for consistent sequence
        if tag_to_add not in new_tags:
            new_tags.append(tag_to_add)
            tags_added.append(tag_to_add)

    # Check for mutations
    if removed_count == 0 and not tags_added:
        return False

    # Build new metadata - keep existing fields
    new_metadata = {}
    if current_meta:
        # Copy all filled fields
        if current_meta.booktitle:
            new_metadata['booktitle'] = current_meta.booktitle
        if current_meta.authors:
            new_metadata['author'] = ', '.join(current_meta.authors)
        if current_meta.author_sort:
            new_metadata['author_sort'] = current_meta.author_sort
        if current_meta.isbn:
            new_metadata['isbn'] = current_meta.isbn
        if current_meta.rating is not None:
            new_metadata['rating'] = current_meta.rating
        if current_meta.publisher:
            new_metadata['publisher'] = current_meta.publisher
        if current_meta.publication_date:
            new_metadata['publication_date'] = current_meta.publication_date
        if current_meta.language:
            new_metadata['language'] = current_meta.language
        if current_meta.pages:
            new_metadata['pages'] = current_meta.pages
        if current_meta.series:
            new_metadata['series'] = current_meta.series
        if current_meta.series_index is not None:
            new_metadata['series_index'] = current_meta.series_index
        if current_meta.translator:
            new_metadata['translator'] = current_meta.translator
        if current_meta.illustrator:
            new_metadata['illustrator'] = current_meta.illustrator
        if current_meta.description:
            new_metadata['description'] = current_meta.description
        if current_meta.notes:
            new_metadata['notes'] = current_meta.notes

    # Update tags
    new_metadata['tags'] = new_tags

    # Write to sidecar
    return modify_markdown_metadata(ebook_path, markdown_path, new_metadata, field_names)

def _modify_epub_metadata(ebook_path: Path, metadata: dict) -> bool:
    """Updates the OPF metadata inside the EPUB
       Uses lxml for correct namespace handling (ElementTree verliest namespace prefixes)"""
    import zipfile
    import os
    import tempfile
    from lxml import etree

    nsmap = {'dc': DC_NS, 'opf': OPF_NS} # Namespace map for lxml queries

    try:
        # Read EPUB and find OPF
        opf_path = None
        opf_content = None

        with zipfile.ZipFile(ebook_path, 'r') as zf:
            # Find OPF via container.xml
            try:
                container_xml = zf.read('META-INF/container.xml')
                container = etree.fromstring(container_xml)
                rootfile = container.find('.//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile')
                if rootfile is not None:
                    opf_path = rootfile.get('full-path')
            except Exception:
                pass

            if not opf_path:
                opf_files = [n for n in zf.namelist() if n.endswith('.opf')]
                if opf_files:
                    opf_path = opf_files[0]

            if not opf_path:
                raise ValueError("No OPF file found in EPUB")

            opf_content = zf.read(opf_path)

        # Parse OPF with lxml (to keep namespaces correct)
        parser = etree.XMLParser(remove_blank_text=False)
        opf = etree.fromstring(opf_content, parser)

        # Find metadata element
        metadata_elem = opf.find('opf:metadata', nsmap)
        if metadata_elem is None:
            metadata_elem = opf.find('{%s}metadata' % OPF_NS)
        if metadata_elem is None:
            metadata_elem = opf.find('metadata')
        if metadata_elem is None:
            raise ValueError("No metadata element in OPF")
        
        # Update metadata fields
        # Dublin Core elements for standard metadata
        field_mapping = {
            'booktitle': 'title',
            'author': 'creator',
            'publisher': 'publisher',
            'language': 'language',
            'description': 'description',
        }
        

        def find_dc_elem(tag_name): # Helper to find DC element (with or without namespace)
            # find_dc_elem tries 3 variants:
            # With dc: namespace prefix via nsmap
            # With Clark notatie {http://...}title
            # Without namespace
            elem = metadata_elem.find(f'dc:{tag_name}', nsmap)
            if elem is not None:
                return elem
            elem = metadata_elem.find('{%s}%s' % (DC_NS, tag_name))
            if elem is not None:
                return elem
            return metadata_elem.find(tag_name)

        # Update Dublin Core fields
        for key, dc_tag in field_mapping.items():
            if key in metadata and metadata[key]:
                # tag_name = dc_tag.split(':')[1]  # 'dc:title' -> 'title'. This is no longer needed, because it was already done at the very beginning
                elem = find_dc_elem(dc_tag)
                if elem is None: # If not found, make new element with correct namespace
                    elem = etree.SubElement(metadata_elem, '{%s}%s' % (DC_NS, dc_tag))
                elem.text = metadata[key]

        # Treat ISBN differently - look specifically for identifier with ISBN scheme
        if 'isbn' in metadata and metadata['isbn']:
            isbn_value = metadata['isbn']
            isbn_elem = None
            # Look for identifier with opf:scheme="ISBN" or id that contains isbn
            # Check both namespace variants for scheme attribute
            for identifier in metadata_elem.findall('dc:identifier', nsmap):
                scheme = identifier.get('{%s}scheme' % OPF_NS, '') or identifier.get('scheme', '')
                elem_id = identifier.get('id', '').lower()
                if scheme.upper() == 'ISBN' or 'isbn' in elem_id:
                    isbn_elem = identifier
                    break
            if isbn_elem is None: # If no ISBN-specific identifier found
                identifiers = metadata_elem.findall('dc:identifier', nsmap)
                if identifiers and identifiers[0].text and 'urn:uuid:' not in identifiers[0].text:
                    isbn_elem = identifiers[0]
                else:
                    isbn_elem = etree.SubElement(metadata_elem, '{%s}identifier' % DC_NS)
                    isbn_elem.set('{%s}scheme' % OPF_NS, 'ISBN')
                    
            isbn_elem.text = isbn_value

        # Tags (dc:subject) - delete existing and add new
        if 'tags' in metadata:
            for subject in metadata_elem.findall('dc:subject', nsmap):
                metadata_elem.remove(subject)
            for tag in metadata['tags']:
                if tag:
                    subj = etree.SubElement(metadata_elem, '{%s}subject' % DC_NS)
                    subj.text = tag

        def set_meta(name, value): # Helper function to find or create meta element
            """Finds or creates <meta name="name" content="value"/>
            Find namespaced as well as non-namespaced meta elements
            Calibre-generated EPUBs often use {OPF_NS}meta elements, while other tools use simple <meta> elements. If you would not look for both, you would create duplicates"""
            all_metas = list(metadata_elem.findall('meta'))
            all_metas.extend(metadata_elem.findall('{%s}meta' % OPF_NS))
            for m in all_metas:
                if m.get('name') == name:
                    if value:
                        m.set('content', value)
                    else:
                        metadata_elem.remove(m)
                    return
            if value:
                new_meta = etree.SubElement(metadata_elem, 'meta')
                new_meta.set('name', name)
                new_meta.set('content', value)

        if 'series' in metadata: # Calibre compatible)
            set_meta('calibre:series', metadata['series'])
        if 'series_index' in metadata: # Calibre compatible)
            set_meta('calibre:series_index', str(metadata['series_index']))
        if 'rating' in metadata and metadata['rating']: # (Calibre uses scale 0-10 internally, we use 0-5)
            try:
                calibre_rating = str(int(float(metadata['rating']) * 2))
                set_meta('calibre:rating', calibre_rating)
            except (ValueError, TypeError):
                pass
        if 'notes' in metadata: # (custom meta element)
            set_meta('calibre:user_notes', metadata['notes'])
        if 'pages' in metadata and metadata['pages']: # Uses rendition:page-count (EPUB3 standard) and calibre:pages as backup
            set_meta('rendition:page-count', metadata['pages'])
            set_meta('calibre:pages', metadata['pages'])
        if 'author_sort' in metadata and metadata['author_sort']: # Author sort: opf:file-as attribute on dc:creator element
            creator_elem = find_dc_elem('creator')
            if creator_elem is not None:
                creator_elem.set('{%s}file-as' % OPF_NS, metadata['author_sort'])
        if 'publication_date' in metadata and metadata['publication_date']: # Publication date: use dc:date for full date
            date_elem = find_dc_elem('date')
            if date_elem is None:
                date_elem = etree.SubElement(metadata_elem, '{%s}date' % DC_NS)
            date_elem.text = metadata['publication_date']

        def get_role(elem):  # Helper to read role attribute (robust for various namespace variants)
            # Try with complete OPF namespace (Clark notation)
            role = elem.get(f'{{{OPF_NS}}}role')
            if role:
                return role.lower()
            # Try without namespace (some EPUBs)
            role = elem.get('role')
            if role:
                return role.lower()
            # Search through all attributes for something that ends with 'role'
            for attr_name, attr_val in elem.attrib.items():
                if attr_name.endswith('role') or attr_name.endswith('}role'):
                    return attr_val.lower()
            return ''

        for contrib_key, role_code in [('translator', 'trl'), ('illustrator', 'ill')]:
            if contrib_key in metadata:
                for contrib in metadata_elem.findall('dc:contributor', nsmap) + metadata_elem.findall('contributor'):
                    if get_role(contrib) == role_code:
                        metadata_elem.remove(contrib) # Delete the old values
                if metadata[contrib_key]:
                    elem = etree.SubElement(metadata_elem, '{%s}contributor' % DC_NS)
                    elem.text = metadata[contrib_key]
                    elem.set('{%s}role' % OPF_NS, role_code)

            # Write back to EPUB with lxml (keeps namespaces correct)
            # Beware: lxml needs bytes encoding for xml_declaration=True
        new_opf_content = etree.tostring(opf, encoding='UTF-8', xml_declaration=True).decode('utf-8')

        fd, temp_path = tempfile.mkstemp(suffix='.epub')
        os.close(fd)

        try:
            all_files = []
            with zipfile.ZipFile(ebook_path, 'r') as zf_in:
                for item in zf_in.infolist():
                    if item.filename == opf_path:
                        all_files.append((item, new_opf_content.encode('utf-8'), True))
                    else:
                        all_files.append((item, zf_in.read(item.filename), False))

            with zipfile.ZipFile(temp_path, 'w') as zf_out:
                for item, data, is_opf in all_files:
                    compress = zipfile.ZIP_DEFLATED if is_opf else item.compress_type
                    zf_out.writestr(item, data, compress_type=compress)

            import gc, time, shutil
            gc.collect()
            for attempt in range(5):
                try:
                    os.replace(temp_path, ebook_path)
                    break
                except PermissionError:
                    if attempt < 4:
                        time.sleep(0.1)
                        gc.collect()
                    else:
                        shutil.copy2(temp_path, ebook_path)
                        os.unlink(temp_path)
        except Exception as e:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise

        return True

    except Exception as e:
        print(f"Error saving EPUB metadata: {e}")
        return False

def modify_epub_tags(path: Path, tags_to_remove: set, tags_to_add: set) -> bool:
    """Modify tags (dc:subject) in an EPUB file
    Supports adding ar deleting multiple tags at once
    Two step approach for maximum speed:
    1. FAST ATTEMPT: ZIP append mode - add only changed OPF
       This is ~50x faster because we do not rewrite the entire EPUB
    2. FALLBACK: If append fails (file locking), rewrite the entire EPUB

    Because:
    - Append mode works for most files
    - Only for file locking (Windows) fallback is needed
    - The slow method is still reliable as backup

    Args:
        path: Path to the EPUB file
        tags_to_remove: Set of tags to delete
        tags_to_add: Set of tags to add (lowercase, empty set = nothing to add)

    Returns True if file has been changed, False otherwise"""
    import zipfile
    import xml.etree.ElementTree as ET
    import os
    import shutil

    # Register namespaces so they are kept at serialisation
    # This prevents adding prefixes in the ElementTree ns0:, ns1:
    ET.register_namespace('dc', DC_NS)
    ET.register_namespace('opf', OPF_NS)
    ET.register_namespace('', OPF_NS)  # default namespace

    try:
        # Check if file is editable (Windows file locking workaround)
        import stat
        file_stat = os.stat(path)
        if not (file_stat.st_mode & stat.S_IWRITE):
            os.chmod(path, file_stat.st_mode | stat.S_IWRITE)

        # Step 1: Open EPUB and find OPF file
        # Backup not needed: we first write to a temp file, original is only replaced in case of succes
        opf_path = None
        opf_content = None

        with zipfile.ZipFile(path, 'r') as zf:
            # Find OPF via container.xml
            try:
                container_xml = zf.read('META-INF/container.xml')
                container = ET.fromstring(container_xml)
                ns = {'c': 'urn:oasis:names:tc:opendocument:xmlns:container'}
                rootfile = container.find('.//c:rootfile', ns)
                if rootfile is None:
                    rootfile = container.find('.//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile')
                if rootfile is not None:
                    opf_path = rootfile.get('full-path')
            except Exception:
                pass

            # Fallback: search for .opf file
            if not opf_path:
                opf_files = [n for n in zf.namelist() if n.endswith('.opf')]
                if opf_files:
                    opf_path = opf_files[0]

            if not opf_path:
                print(f"No OPF file found in {path}")
                return False

            # Read OPF content
            opf_content = zf.read(opf_path).decode('utf-8')

        # Stap 3: Parse OPF XML
        # Save original XML declaration and whitespace as much as possible
        opf = ET.fromstring(opf_content)

        # Find metadata element
        metadata = opf.find(f'{{{OPF_NS}}}metadata')
        if metadata is None:
            metadata = opf.find('metadata')
        if metadata is None:
            print(f"No metadata element found in OPF of {path}")
            return False

        # Stap 4: Collect current tags and adjust
        current_tags = []
        subjects_to_remove = []

        for subject in metadata.findall(f'{{{DC_NS}}}subject'):
            if subject.text:
                tag_text = subject.text.strip()
                if tag_text in tags_to_remove:
                    # Mark for removal
                    subjects_to_remove.append(subject)
                else:
                    current_tags.append(tag_text)

        # Remove marked subjects
        for subject in subjects_to_remove:
            metadata.remove(subject)

        # Add any tags that do not exist yet
        tags_added = []
        for tag_to_add in sorted(tags_to_add):  # Sort for consistent order
            if tag_to_add not in current_tags:
                # At first dc:subject: make sure dc namespace is declared. This is neccesary because ElementTree loses the namespace declaration if there are no existing dc: elementens
                if not current_tags and not tags_added:
                    # Find an existing dc: element to keep the namespace
                    # (f.e. dc:title, dc:creator) - If there is one, dc namespace is OK
                    existing_dc = metadata.find(f'{{{DC_NS}}}title')
                    if existing_dc is None:
                        existing_dc = metadata.find(f'{{{DC_NS}}}creator')
                    if existing_dc is None:
                        # No existing dc: elements - add xmlns:dc to  metadata
                        # ElementTree doesn't support this directly, so we use attrib
                        # Beware: this only works if the namespace isn't declared yet!
                        metadata.set(f'{{http://www.w3.org/2000/xmlns/}}dc', DC_NS)

                # Create new dc:subject element
                new_subject = ET.SubElement(metadata, f'{{{DC_NS}}}subject')
                new_subject.text = tag_to_add
                tags_added.append(tag_to_add)

        # Check if there are changes
        if not subjects_to_remove and not tags_added:
            return False

        # Step 5: Write changed OPF back to EPUB
        # Serialise the XML with correct encoding
        new_opf_content = ET.tostring(opf, encoding='unicode', xml_declaration=True)

        import tempfile

        # Make temporary file
        fd, temp_path = tempfile.mkstemp(suffix='.epub')
        os.close(fd)

        try:
            # Read all files in memory first to release file handles. This prevents file locking problems on Windows
            all_files = []
            with zipfile.ZipFile(path, 'r') as zf_in:
                for item in zf_in.infolist():
                    if item.filename == opf_path:
                        # Use modified OPF content
                        all_files.append((item, new_opf_content.encode('utf-8'), True))
                    else:
                        data = zf_in.read(item.filename)
                        all_files.append((item, data, False))

            # Write to temp file (original is now closed)
            # NO recompression for speed - EPUB could become slightly bigger
            with zipfile.ZipFile(temp_path, 'w') as zf_out:
                for item, data, is_opf in all_files:
                    if is_opf:
                        # OPF is small, but compress for compatibility
                        zf_out.writestr(item, data, compress_type=zipfile.ZIP_DEFLATED)
                    else:
                        # Keep original compression type for compatibility
                        zf_out.writestr(item, data, compress_type=item.compress_type)

            # Force garbage collection to release file handles
            import gc
            gc.collect()

            # Replace original file by changed file
            # Windows file locking workaround: retry with little delay
            # os.replace() sometimes fails on Windows because the file handle hasn't been fully released is, even after gc.collect()
            import time
            max_retries = 5
            for attempt in range(max_retries):
                try:
                    os.replace(temp_path, path)
                    break  # Succes
                except PermissionError:
                    if attempt < max_retries - 1:
                        time.sleep(0.1)  # Wait 100ms and try again
                        gc.collect()
                    else:
                        # Last attempt: try shutil.copy + delete
                        try:
                            shutil.copy2(temp_path, path)
                            os.unlink(temp_path)
                        except Exception:
                            raise  # Transfer the original PermissionError
            return True

        except Exception as e:
            # At error: remove temp file
            if os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass
            raise e

    except Exception as e:
        print(f"Error modifying EPUB tags in {path}: {e}")
        import traceback
        traceback.print_exc()
        return False

def _modify_cbz_metadata(ebook_path: Path, metadata: dict, field_names: dict = None) -> bool:
    """Update ComicInfo.xml inside a CBZ archive"""
    import zipfile
    import xml.etree.ElementTree as ET
    import os
    import tempfile
    import shutil

    try:
        comicinfo_content = None
        comicinfo_exists = False

        with zipfile.ZipFile(ebook_path, 'r') as zf:
            for name in zf.namelist():
                if name.lower() == 'comicinfo.xml':
                    comicinfo_content = zf.read(name).decode('utf-8')
                    comicinfo_exists = True
                    break
        # if comicinfo_content:
        #     root = ET.fromstring(comicinfo_content)
        # else:
        #     root = ET.Element('ComicInfo')

        root = ET.fromstring(comicinfo_content) if comicinfo_content else ET.Element('ComicInfo')
        # ComicInfo.xml supports these standard fields:
        field_mapping = {
            'booktitle': 'Title',
            'author': 'Writer',
            'publisher': 'Publisher',
            'description': 'Summary',
            'notes': 'Notes',
            'series': 'Series',
            'series_index': 'Number',
            'language': 'LanguageISO',
            'pages': 'PageCount',
            'illustrator': 'Penciller', # Illustrator is saved as Penciller (most used artist role)
            'translator': 'Translator', # Translator is not a default ComicInfo field, maar we add it for compatibility (some readers support it)
        }

        for key, xml_field in field_mapping.items():
            if key in metadata and metadata[key]:
                elem = root.find(xml_field)
                if elem is None:
                    elem = ET.SubElement(root, xml_field)
                elem.text = str(metadata[key])
            elif key in metadata and not metadata[key]:
                elem = root.find(xml_field)
                if elem is not None: # Delete element if value is empty
                    root.remove(elem)

        if 'tags' in metadata:
            tags_elem = root.find('Tags')
            if metadata['tags']:
                if tags_elem is None:
                    tags_elem = ET.SubElement(root, 'Tags')
                tags_elem.text = ', '.join(metadata['tags'])
            elif tags_elem is not None:
                root.remove(tags_elem)

        if 'rating' in metadata:
            rating_elem = root.find('CommunityRating')
            if metadata['rating']:
                if rating_elem is None:
                    rating_elem = ET.SubElement(root, 'CommunityRating')
                rating_elem.text = str(metadata['rating'])
            elif rating_elem is not None:
                root.remove(rating_elem)

        # Extra fields not supported by ComicInfo.xml go to sidecar
        extra_fields = {f: metadata[f] for f in ['isbn', 'author_sort', 'publication_date']
                        if f in metadata and metadata[f]}
        if extra_fields:
            modify_markdown_metadata(ebook_path, get_sidecar_path(ebook_path), extra_fields, field_names)
        else:
            sidecar_path = get_sidecar_path(ebook_path)
            if sidecar_path.exists():
                try:
                    sidecar_path.unlink()
                except Exception:
                    pass

        new_comicinfo = ET.tostring(root, encoding='unicode', xml_declaration=True)

        fd, temp_path = tempfile.mkstemp(suffix='.cbz')
        os.close(fd)

        try:
            with zipfile.ZipFile(ebook_path, 'r') as zf_in:
                with zipfile.ZipFile(temp_path, 'w') as zf_out:
                    for item in zf_in.infolist():
                        if item.filename.lower() == 'comicinfo.xml':
                            zf_out.writestr(item, new_comicinfo.encode('utf-8'),
                                           compress_type=zipfile.ZIP_DEFLATED)
                        else:
                            zf_out.writestr(item, zf_in.read(item.filename),
                                           compress_type=item.compress_type)
                    if not comicinfo_exists:
                        zf_out.writestr('ComicInfo.xml', new_comicinfo.encode('utf-8'),
                                       compress_type=zipfile.ZIP_DEFLATED)

            if ebook_path.exists():
                os.unlink(ebook_path)
            shutil.move(temp_path, ebook_path)
        except Exception as e:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise

        return True

    except Exception as e:
        print(f"Error saving CBZ metadata: {e}")
        return False

def modify_cbz_tags(path: Path, tags_to_remove: set, tags_to_add: set) -> bool:
    """Modify tags in a comic archive
    Supports adding or removing multiple tags at once
    Args:
        path: Path to the comic archive
        tags_to_remove: Set of tags to remove (case-sensitive)
        tags_to_add: Set van tags to add (case-sensitive)
    Returns True if file is changed, False otherwise"""
    file_type = path.suffix.lower()

    # Write to ComicInfo.xml archive
    import zipfile
    import xml.etree.ElementTree as ET
    import os
    import tempfile
    import shutil
  
    try:
        # Open archive and find ComicInfo.xml (case-insensitive)
        comicinfo_content = None
        comicinfo_exists = False

        with zipfile.ZipFile(path, 'r') as zf:
            for name in zf.namelist():
                if name.lower() == 'comicinfo.xml':
                    comicinfo_content = zf.read(name).decode('utf-8')
                    comicinfo_exists = True
                    break

        # Parse or create ComicInfo.xml
        if comicinfo_content:
            root = ET.fromstring(comicinfo_content)
        else:
            root = ET.Element('ComicInfo')

        # Get current tags
        tags_elem = root.find('Tags')
        current_tags = []
        if tags_elem is not None and tags_elem.text:
            current_tags = [t.strip() for t in tags_elem.text.split(',') if t.strip()]

        # Adjust tags - remove first (case-sensitive)
        new_tags = [t for t in current_tags if t not in tags_to_remove]
        removed_count = len(current_tags) - len(new_tags)

        # Add all tags that do not exist yet (case-sensitive)
        tags_added = []
        for tag_to_add in sorted(tags_to_add):  # Sort for consistent order
            if tag_to_add not in new_tags:
                new_tags.append(tag_to_add)
                tags_added.append(tag_to_add)

        # Check for changes
        if removed_count == 0 and not tags_added:
            return False

        # Update ComicInfo.xml
        if tags_elem is None:
            tags_elem = ET.SubElement(root, 'Tags')
        tags_elem.text = ', '.join(new_tags) if new_tags else ''

        new_comicinfo = ET.tostring(root, encoding='unicode', xml_declaration=True)

        # Write back to archive via temp file
        fd, temp_path = tempfile.mkstemp(suffix='.cbz')
        os.close(fd)

        try:
            with zipfile.ZipFile(path, 'r') as zf_in:
                with zipfile.ZipFile(temp_path, 'w') as zf_out:
                    for item in zf_in.infolist():
                        if item.filename.lower() == 'comicinfo.xml':
                            # Write changed ComicInfo.xml
                            zf_out.writestr(item, new_comicinfo.encode('utf-8'), compress_type=zipfile.ZIP_DEFLATED)
                        else:
                            data = zf_in.read(item.filename)
                            zf_out.writestr(item, data, compress_type=item.compress_type)

                    # Add ComicInfo.xml if it didn't exist yet
                    if not comicinfo_exists:
                        zf_out.writestr('ComicInfo.xml', new_comicinfo.encode('utf-8'), compress_type=zipfile.ZIP_DEFLATED)

            # Replace original
            if path.exists():
                os.unlink(path)
            shutil.move(temp_path, path)
            return True

        except Exception as e:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise e

    except Exception as e:
        print(f"Error modifying comic tags in {path}: {e}")
        return False

def save_full_metadata(ebook_path: Path,
                       metadata: dict = None, # Dict with all metadata fields
                       use_sidecar: bool = False,
                       field_names: dict = None,
                       opf_metadata: dict = None) -> bool:
    """Merge metadata from all sources and save to the appropriate location
    Remove OPF and MD sidecars that are no longer needed
    If metadata is provided, it is used as-is (from UI editor in main.py)
    If metadata is None, metadata is merged from all available sources:
        1. Native book metadata (lowest priority)
        2. OPF sidecar (auto-detected next to book, or passed via opf_metadata)
        3. Markdown sidecar (highest priority, user-edited data)

    Routing:
    - .md/.markdown: update YAML frontmatter, preserve body
    - .epub: write to internal OPF (unless use_sidecar=True)
    - .cbz: write to ComicInfo.xml (unless use_sidecar=True)
    - all other cases: always write to sidecar
    Cleanup if use_sidecar is False. For each ebook with a sidecar:
    - EPUB: merge sidecar into EPUB internal OPF, then delete sidecar
    - CBZ: merge sidecar into ComicInfo.xml, keep sidecar only if
           isbn/author_sort/publication_date are filled
    - Other formats: leave sidecar as-is (always needed)
    
    Args:
        ebook_path: Path to the ebook file
        metadata: Optional. Dict with metadata to save directly (from UI editor).
                  If None, metadata is merged from all available sources.
        use_sidecar: If True, force sidecar (even for epub/cbz)
        field_names: Optional. Configured field names
        opf_metadata: Optional. Pre-parsed OPF dict (Calibre2Libiry passes this explicitly)
        If None and no metadata provided: merge from all sources"""
    if metadata is None:
        try:
            extractor = MetadataExtractor()
            metadata = extractor.extract(ebook_path)
        except Exception as e:
            print(f"Could not read native metadata from {ebook_path}: {e}")

        """Check if a markdown sidecar is still needed for this ebook
        For EPUB: never needed (EPUB can store all fields natively)
        For CBZ: needed if isbn, author_sort or publication_date are filled
        For all other formats: always needed when fields are still filled (and when cover is not identical to cover sidecar image)"""

    # Init 
    file_type = ebook_path.suffix.lower()
    mdsidecar_ok = True # Init MD sidecar written successfully
    delete_md_sidecar = False  # Flipped True when MD sidecar is redundant
    if file_type in ('.md', '.markdown'):
        sidecar_path = ebook_path
    else:
        sidecar_path = get_sidecar_path(ebook_path)

    if file_type in ('.md', '.markdown'):
        result = modify_markdown_metadata(ebook_path, sidecar_path, metadata, field_names)

    elif file_type == '.epub' and not use_sidecar:
        result = _modify_epub_metadata(ebook_path, metadata)
        if result:
            needs_sidecar = any(metadata.get(field_names.get(f, f)) 
                               for f in ['isbn', 'author_sort', 'publication_date'])
            if needs_sidecar:
                mdsidecar_ok = modify_markdown_metadata(ebook_path, sidecar_path, metadata, field_names)
            else: # Sidecar is redundant - delete it
                delete_md_sidecar = True

    elif file_type == '.cbz' and not use_sidecar:
        result = _modify_cbz_metadata(ebook_path, metadata, field_names)
        if result:
            needs_sidecar = any(metadata.get(field_names.get(f, f)) 
                               for f in ['isbn', 'author_sort', 'publication_date'])
            if needs_sidecar:
                mdsidecar_ok = modify_markdown_metadata(ebook_path, sidecar_path, metadata, field_names)
            else: # Sidecar is redundant - delete it
                delete_md_sidecar = True

    else:
        result = modify_markdown_metadata(ebook_path, sidecar_path, metadata, field_names)
        mdsidecar_ok = result

        opfsidecar_ok = result and mdsidecar_ok

    # If metadata have succesfully been written, delete any MD and OPF sidecars that have now become redundant
    if result and mdsidecar_ok:
        if delete_md_sidecar: # MD sidecar is redundant - delete it
           if sidecar_path.exists():
               try:
                   sidecar_path.unlink()
               except Exception as e:
                   print(f"Could not remove sidecar: {e}")

        opf_path = ebook_path.parent / 'metadata.opf'
        if opf_path.exists():
            try:
                opf_path.unlink()
            except Exception as e:
                print(f"Could not remove OPF: {e}")

    return result   

def get_sidecar_path(ebook_path: Path) -> Path:
    """Get the path to the Markdown sidecar file for an ebook
    Args: ebook_path: Path to the ebook file
    Returns: Path to the correspondering sidecar file (original name + .md extension) F.e. book.mobi -> book.mobi.md
    This way there are no conflicts if you have book.pdf and book.mobi in the same folder"""
    
    # Add .md to the filename
    # book.mobi -> book.mobi.md (so not book.md)
    return ebook_path.parent / (ebook_path.name + '.md')

def _format_tags_for_yaml(tags: List[str], field_name: str = 'tags') -> List[str]:
    """Formats tags for YAML output as list format
    Returns a list of formatted rules for YAML block list format:
        tags:
          - fiction
          - sci-fi
    Tags that contain special YAML characters get quotes
    Examples:
        ['fiction', 'sci-fi'] -> ['tags:', '  - fiction', '  - sci-fi']
        ['fiction', 'Brando, Marlon'] -> ['tags:', '  - fiction', '  - "Brando, Marlon"']"""
    if not tags:
        return []

    _YAML_RESERVED = {'true', 'false', 'null', 'yes', 'no', 'on', 'off', '~'}
    lines = [f'{field_name}:']
    for tag in tags:
        # Tags that contain special characters, that will lead to YAML issues, get quotes
        tag_str = str(tag)
        needs_quote = (
            any(c in tag_str for c in ':#[]{}|>&*!,\r\n\'') or
            re.match(r'^[-+]?[\d.]+$', tag_str) or # pure number → YAML integer without quotes
            tag_str.strip().lower() in _YAML_RESERVED or
            tag_str != tag_str.strip()                     # leading/trailing whitespace
        )
        if needs_quote:
            escaped = (tag_str
                       .replace('\\', '\\\\')
                       .replace('"', '\\"')
                       .replace('\r\n', '\\n')
                       .replace('\r', '\\n')
                       .replace('\n', '\\n'))
            lines.append(f'  - "{escaped}"')
        else:
            lines.append(f'  - {tag_str}')
            
    return lines

# =============================================================================
# Legacy OPF Reading Support
# =============================================================================

def extract_opf(ebook_path: Path) -> Optional[BookMetadata]:
    """Extract metadata from opf sidecar file
    Similar to read_markdown_metadata
    Reads: booktitle, author, isbn, publisher, language, description, publication_date, tags, series, series_index, rating, notes, author_sort, pages, translator, illustrator
    Args: ebook_path: Path to the e-book file (so not to the OPF itself)
    Returns: BookMetadata object with all found fields, or None if OPF doesn't exist"""
    import xml.etree.ElementTree as ET

    opf_path = ebook_path.parent / 'metadata.opf'
    if not opf_path.exists():
        return None

    try:
        tree = ET.parse(opf_path)
        root = tree.getroot()

        meta = BookMetadata()

        # Find metadata element - try different variants
        metadata_elem = root.find(f'.//{{{OPF_NS}}}metadata')
        if metadata_elem is None:
            metadata_elem = root.find('.//metadata')
        if metadata_elem is None:
            # Maybe root itself is the metadata element or package
            if root.tag.endswith('metadata'):
                metadata_elem = root
            else:
                metadata_elem = root  # Search in root

        # Helper to find DC element (tries with and without namespace)
        # Robust version that also works when namespaces do not match exactly
        def find_dc_text(tag):
            # Try with complete DC namespace (Clark notation)
            elem = metadata_elem.find(f'{{{DC_NS}}}{tag}')
            if elem is not None and elem.text:
                return elem.text.strip()
            # Try without namespace
            elem = metadata_elem.find(tag)
            if elem is not None and elem.text:
                return elem.text.strip()
            # Search all children - check }tag and :tag patterns
            # This handles namespace variations (f.e. {ns}tag of prefix:tag)
            for e in metadata_elem:
                # Check if tag ends on }localname (Clark notation) or :localname (prefix)
                if e.tag.endswith(f'}}{tag}') or e.tag.endswith(f':{tag}') or e.tag == tag:
                    if e.text:
                        return e.text.strip()
            # Extra fallback: also search in nested element (some OPF structures)
            for e in metadata_elem.iter():
                if e.tag.endswith(f'}}{tag}') or e.tag.endswith(f':{tag}') or e.tag == tag:
                    if e.text:
                        return e.text.strip()
            return ''

        meta.booktitle = find_dc_text('title') #field name booktitle is also used in venv

        # Authors (one or more dc:creator entries)
        authors = []
        for creator in metadata_elem.findall(f'{{{DC_NS}}}creator'):
            if creator.text:
                authors.append(creator.text.strip())
        if not authors:
            for creator in metadata_elem.findall('creator'):
                if creator.text:
                    authors.append(creator.text.strip())
        if not authors:
            # Search in all children
            for e in metadata_elem:
                if e.tag.endswith('creator') and e.text:
                    authors.append(e.text.strip())
        meta.authors = authors

        # ISBN - first look for <dc:identifier opf:scheme="ISBN">, then fallback to first identifier
        isbn_found = False
        first_identifier = None

        # Search all dc:identifier elements
        for identifier_elem in metadata_elem.findall(f'{{{DC_NS}}}identifier'):

            if not identifier_elem.text:
                continue
            ident_text = identifier_elem.text.strip()

            # Skip Calibre and UUID values
            scheme = (identifier_elem.get(f'{{{OPF_NS}}}scheme')
                      or identifier_elem.get('opf:scheme') or '')
            if scheme.upper() in ('CALIBRE', 'UUID'):
                continue

            # Check for opf:scheme="ISBN" attribute (preferred)
            scheme = identifier_elem.get(f'{{{OPF_NS}}}scheme') or identifier_elem.get('opf:scheme') or ''
            if scheme.upper() == 'ISBN':
                # Clean ISBN value
                isbn_match = re.search(r'(\d{10}|\d{13})', ident_text)
                if isbn_match:
                    meta.isbn = isbn_match.group(1)
                else:
                    meta.isbn = ident_text
                isbn_found = True
                break

            # Store first non-UUID identifier as fallback
            if first_identifier is None:
                first_identifier = ident_text

        # Fallback: use first identifier if no ISBN scheme found
        if not isbn_found and first_identifier:
            isbn_match = re.search(r'(\d{10}|\d{13})', first_identifier)
            if isbn_match:
                meta.isbn = isbn_match.group(1)  
        
        meta.publisher = find_dc_text('publisher')
        meta.language = find_dc_text('language')
        meta.description = find_dc_text('description')

        # Tags from dc:subject
        tags = []
        for subject in metadata_elem.findall(f'{{{DC_NS}}}subject'):
            if subject.text:
                tags.append(subject.text.strip())
        if not tags:
            for subject in metadata_elem.findall('subject'):
                if subject.text:
                    tags.append(subject.text.strip())
        if tags:
            meta.tags = tags

        # Translator and Illustrator from dc:contributor
        for contributor in metadata_elem.findall(f'{{{DC_NS}}}contributor'):
            if contributor.text:
                name_text = contributor.text.strip()
                role = contributor.get(f'{{{OPF_NS}}}role') or contributor.get('opf:role') or ''
                role = role.lower()
                if role == 'trl' and 'translator' not in metadata:
                    meta.translator = name_text
                elif role == 'ill' and 'illustrator' not in metadata:
                    meta.illustrator = name_text

        # Calibre-style meta elements - search with and without namespace
        # Must be done BEFORE year lookup, because calibre:year is a meta element
        meta_elements = list(metadata_elem.findall(f'{{{OPF_NS}}}meta'))
        meta_elements.extend(metadata_elem.findall('meta'))

        # Process other meta elements (series, rating, notes, pages, etc.)
        for m in meta_elements:
            name = m.get('name', '')
            content = m.get('content', '')

            if name == 'calibre:series' and content:
                meta.series = content
            elif name == 'calibre:series_index' and content:
                try:
                    meta.series_index = float(content)
                except (ValueError, TypeError):
                    pass
            elif name == 'calibre:rating' and content:
                # Use central conversion (with quarter stars)
                rating = convert_calibre_rating(content)
                if rating is not None:
                    meta.rating = rating
            elif name == 'calibre:user_notes' and content:
                meta.notes = content
            # Pages can be stored in various meta elements
            elif name in ('rendition:page-count', 'calibre:pages') and content:
                meta.pages = content
            # Author sort as meta element
            elif name == 'calibre:author_sort' and content:
                meta.author_sort = content

        # Author sort: opf:file-as attribute on dc:creator (primary method)
        for creator in metadata_elem.findall(f'{{{DC_NS}}}creator'):
            file_as = creator.get(f'{{{OPF_NS}}}file-as') or creator.get('opf:file-as')
            if file_as and not meta.author_sort: 
                meta.author_sort = file_as.strip() 
                break

        # Publication date: first from dc:date
        meta.publication_date = find_dc_text('date') 
        if not meta.publication_date: 
            meta.publication_date = find_dc_text('calibre:year')

        # Translator and Illustrator: dc:contributor with opf:role
        for contributor in metadata_elem.findall(f'{{{DC_NS}}}contributor'):
            if contributor.text:
                name_text = contributor.text.strip()
                role = contributor.get(f'{{{OPF_NS}}}role') or contributor.get('opf:role') or ''
                role = role.lower()
                if role == 'trl' and not meta.translator:
                    meta.translator = name_text
                elif role == 'ill' and not meta.illustrator:
                    meta.illustrator = name_text

        return meta

    except Exception as e:
        print(f"Error reading legacy OPF metadata from {opf_path}: {e}")
        import traceback
        traceback.print_exc()
        return None