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

    Extra velden (EPUB/Calibre):
    - author_sort: sorteer naam auteur (opf:file-as)
    - translator: vertaler (dc:contributor met role="trl")
    - illustrator: illustrator (dc:contributor met role="ill")
    - publication_date: volledige publicatiedatum
    - pages: aantal pagina's (Calibre custom of EPUB meta)

    Velden voor gebruikersinvoer:
    - notes: persoonlijke notities
    - cover_url: URL naar cover afbeelding
    """
    # Volgorde: Goodreads CSV export + extra velden
    cover_url: str = ""                              # UI: cover afbeelding
    booktitle: str = ""                              # Goodreads: Title
    authors: List[str] = field(default_factory=list) # Goodreads: Author
    author_sort: str = ""                            # Sorteer naam auteur (opf:file-as)
    isbn: str = ""                                   # ISBN
    rating: Optional[float] = None                   # Goodreads: My Rating (0-10 Calibre, 0-5 getoond)
    publisher: str = ""                              # Goodreads: Publisher
    year: str = ""                                   # Goodreads: Year Published
    publication_date: str = ""                       # Volledige publicatiedatum (YYYY-MM-DD)
    language: str = ""                               # Taal
    pages: str = ""                                  # Aantal pagina's
    tags: List[str] = field(default_factory=list)    # Goodreads: Bookshelves
    series: str = ""                                 # Serie naam
    series_index: Optional[float] = None             # Serie volgnummer
    translator: str = ""                             # Vertaler (dc:contributor role="trl")
    illustrator: str = ""                            # Illustrator (dc:contributor role="ill")
    description: str = ""                            # Goodreads: My Review
    notes: str = ""                                  # Goodreads: Private Notes


# Centrale imports - geen dubbele code!
from core.libiry_style import (
    DEFAULT_FIELD_NAMES,
    convert_calibre_rating,
    normalize_rating,
)


# =============================================================================
# XML/OPF Namespace Constants (voor hergebruik)
# =============================================================================

DC_NS = 'http://purl.org/dc/elements/1.1/'
OPF_NS = 'http://www.idpf.org/2007/opf'


# =============================================================================
# XML Helper Functions (centrale versie - geen dubbele code!)
# =============================================================================

def find_dc_text(metadata_elem, tag: str, dc_ns: str = DC_NS) -> str:
    """Find Dublin Core text element in XML metadata.

    Robuuste helper die werkt met verschillende namespace varianten.
    Centraal gedefinieerd om duplicatie te voorkomen.

    Args:
        metadata_elem: XML element containing metadata
        tag: DC tag name (e.g., 'title', 'creator', 'identifier')
        dc_ns: Dublin Core namespace (default: standard DC namespace)

    Returns:
        Text content of element, or empty string if not found
    """
    # Probeer met volledige DC namespace (Clark notatie)
    elem = metadata_elem.find(f'{{{dc_ns}}}{tag}')
    if elem is not None and elem.text:
        return elem.text.strip()

    # Probeer zonder namespace
    elem = metadata_elem.find(tag)
    if elem is not None and elem.text:
        return elem.text.strip()

    # Zoek in alle children - check zowel }tag als :tag patronen
    # Dit vangt namespace variaties op (bijv. {ns}tag of prefix:tag)
    for e in metadata_elem:
        if e.tag.endswith(f'}}{tag}') or e.tag.endswith(f':{tag}') or e.tag == tag:
            if e.text:
                return e.text.strip()

    # Extra fallback: zoek ook in geneste elementen (sommige OPF structuren)
    for e in metadata_elem.iter():
        if e.tag.endswith(f'}}{tag}') or e.tag.endswith(f':{tag}') or e.tag == tag:
            if e.text:
                return e.text.strip()

    return ''


def find_opf_metadata_element(root, opf_ns: str = OPF_NS):
    """Find the metadata element in an OPF XML structure.

    Args:
        root: XML root element
        opf_ns: OPF namespace (default: standard OPF namespace)

    Returns:
        metadata element, or root if not found
    """
    # Zoek metadata element - probeer verschillende varianten
    metadata_elem = root.find(f'.//{{{opf_ns}}}metadata')
    if metadata_elem is None:
        metadata_elem = root.find('.//metadata')
    if metadata_elem is None:
        # Misschien is root zelf het metadata element of package
        if root.tag.endswith('metadata'):
            metadata_elem = root
        else:
            metadata_elem = root  # Zoek in root
    return metadata_elem


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

        # Voor onbekende bestandsformaten: check sidecar voor metadata
        # Dit ondersteunt file types zoals .rtf, .mp3, .txt etc.
        # Sidecar bestanden zelf worden overgeslagen (geen sidecar voor sidecar)
        if suffix not in ('.opf', '.md'):
            meta = BookMetadata(booktitle=filepath.stem)
            # Lees metadata uit sidecar als die bestaat
            sidecar_meta = read_sidecar_metadata(filepath)
            if sidecar_meta:
                if sidecar_meta.tags:
                    meta.tags = sidecar_meta.tags
                if sidecar_meta.booktitle:
                    meta.booktitle = sidecar_meta.booktitle
                if sidecar_meta.authors:
                    meta.authors = sidecar_meta.authors
                # Kopieer alle andere velden
                for field in ['author_sort', 'isbn', 'rating', 'publisher', 'year',
                              'publication_date', 'language', 'pages', 'series',
                              'series_index', 'translator', 'illustrator',
                              'description', 'notes']:
                    val = getattr(sidecar_meta, field, None)
                    if val is not None and val != '':
                        setattr(meta, field, val)
            return meta

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

                # Extract dc:creator (authors) en author_sort (opf:file-as)
                authors = []
                author_sort = ""
                for creator in metadata.findall(f'{{{DC_NS}}}creator'):
                    if creator.text:
                        authors.append(creator.text.strip())
                        # opf:file-as attribuut bevat sorteer naam (bijv. "Achternaam, Voornaam")
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

                # Extract dc:date (publication year en volledige datum)
                date_elem = metadata.find(f'{{{DC_NS}}}date')
                if date_elem is not None and date_elem.text:
                    date_text = date_elem.text.strip()
                    # Volledige publicatiedatum bewaren
                    meta.publication_date = date_text
                    # Extract year from date (can be YYYY, YYYY-MM, YYYY-MM-DD, etc.)
                    year_match = re.match(r'^(\d{4})', date_text)
                    if year_match:
                        meta.year = year_match.group(1)
                    else:
                        # Accepteer ook andere waarden (user-ingevoerd)
                        meta.year = date_text

                # Extract dc:contributor (translator, illustrator)
                # opf:role attribuut geeft de rol aan: trl=translator, ill=illustrator
                # We moeten meerdere manieren proberen om het role attribuut te lezen
                # omdat verschillende EPUB generators het anders opslaan
                translators = []
                illustrators = []

                # Helper om role attribuut te vinden (verschillende namespace varianten)
                def get_role(elem):
                    # Probeer met volledige OPF namespace (Clark notatie)
                    role = elem.get(f'{{{OPF_NS}}}role')
                    if role:
                        return role.lower()
                    # Probeer zonder namespace (sommige EPUBs)
                    role = elem.get('role')
                    if role:
                        return role.lower()
                    # Zoek in alle attributen naar iets dat eindigt op 'role'
                    for attr_name, attr_val in elem.attrib.items():
                        if attr_name.endswith('role') or attr_name.endswith('}role'):
                            return attr_val.lower()
                    return ''

                # Zoek contributors met DC namespace
                for contributor in metadata.findall(f'{{{DC_NS}}}contributor'):
                    if contributor.text:
                        name = contributor.text.strip()
                        role = get_role(contributor)
                        if role == 'trl':
                            translators.append(name)
                        elif role == 'ill':
                            illustrators.append(name)

                # Fallback: zoek contributors zonder namespace (sommige oude EPUBs)
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

                # Extract Calibre-style metadata uit <meta> elementen
                # Zoek zowel met als zonder OPF namespace (beide komen voor)
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
                        # Gebruik centrale conversie (met kwart-sterren)
                        rating = convert_calibre_rating(content)
                        if rating is not None:
                            meta.rating = rating
                    elif name == 'calibre:user_notes' and content:
                        meta.notes = content
                    # Pages kan in verschillende Calibre custom columns zitten
                    elif name in ('calibre:user_metadata:#pages', 'calibre:pages') and content:
                        meta.pages = content

                # Zoek ook naar source/page-count in standaard meta elementen
                for meta_elem in meta_elements:
                    prop = meta_elem.get('property', '')
                    if prop == 'rendition:page-count' and meta_elem.text:
                        meta.pages = meta_elem.text.strip()

            except Exception as e:
                print(f"Error parsing OPF: {e}")

        return meta

    def _extract_mobi(self, filepath: Path) -> BookMetadata:
        """Extract metadata from MOBI/AZW3 file.

        Probeert meerdere libraries voor basis metadata:
        1. ebookmeta - voor titel, auteur etc.
        2. mobi - als fallback voor basis metadata

        Tags worden ALTIJD uit Markdown sidecar file gelezen (ebookmeta is onbetrouwbaar).
        """
        meta = BookMetadata(booktitle=filepath.stem)

        # Methode 1: ebookmeta library voor basis metadata
        try:
            from ebookmeta import get_metadata
            book_meta = get_metadata(str(filepath))

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
            # Methode 2: mobi library als fallback (geen tag support)
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
                pass
            except Exception:
                pass
        except Exception:
            pass

        # Tags en extra velden komen ALTIJD uit sidecar file (MOBI tag support is onbetrouwbaar)
        # Sidecar waarden overschrijven ebookmeta waarden zodat user edits behouden blijven
        sidecar_meta = read_sidecar_metadata(filepath)
        if sidecar_meta:
            meta.tags = sidecar_meta.tags or []
            # Basis velden: sidecar heeft prioriteit over ebookmeta (user edits)
            # BELANGRIJK: booktitle moet ook uit sidecar gelezen worden anders gaan edits verloren
            if sidecar_meta.booktitle:
                meta.booktitle = sidecar_meta.booktitle
            if sidecar_meta.authors:
                meta.authors = sidecar_meta.authors
            if sidecar_meta.publisher:
                meta.publisher = sidecar_meta.publisher
            if sidecar_meta.language:
                meta.language = sidecar_meta.language
            # Extra velden die MOBI niet native ondersteunt
            meta.isbn = sidecar_meta.isbn or meta.isbn or ''
            meta.series = sidecar_meta.series or ''
            meta.series_index = sidecar_meta.series_index
            meta.rating = sidecar_meta.rating
            meta.notes = sidecar_meta.notes or ''
            meta.year = sidecar_meta.year or ''
            meta.description = sidecar_meta.description or ''
            # Nieuwe velden
            meta.author_sort = sidecar_meta.author_sort or ''
            meta.publication_date = sidecar_meta.publication_date or ''
            meta.pages = sidecar_meta.pages or ''
            meta.translator = sidecar_meta.translator or ''
            meta.illustrator = sidecar_meta.illustrator or ''
        else:
            meta.tags = []

        return meta

    def _extract_pdf(self, filepath: Path) -> BookMetadata:
        """Extract metadata from PDF file.

        Metadata wordt gelezen uit:
        1. Markdown sidecar file als die bestaat (voor extra velden zoals isbn, series, rating)
        2. PDF native metadata (title, author, keywords/tags)

        Sidecar heeft prioriteit voor velden die PDF niet native ondersteunt.
        """
        meta = BookMetadata(booktitle=filepath.stem)

        # STAP 1: Lees native PDF metadata (heeft prioriteit)
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
                    # Split authors by unambiguous separators only
                    # Do NOT split on comma - "Last, First" is valid single author
                    authors_str = pdf_meta['author']
                    for sep in [';', '&', ' and ']:
                        if sep in authors_str:
                            meta.authors = [a.strip() for a in authors_str.split(sep)]
                            break
                    else:
                        meta.authors = [authors_str]

                # Tags: Calibre en veel ebook tools slaan tags op in het 'subject' veld.
                # Het 'keywords' veld bevat vaak irrelevante data zoals URLs of generator info.
                # Daarom: subject eerst, keywords als fallback.
                # Tags worden gescheiden door ', ' (komma-spatie) - consistent met schrijven.
                if pdf_meta.get('subject'):
                    subject = pdf_meta['subject'].strip()
                    meta.tags = [t.strip() for t in subject.split(', ') if t.strip()]
                elif pdf_meta.get('keywords'):
                    meta.tags = [pdf_meta['keywords'].strip()]

                # NB: PDF 'producer' veld is voor software die PDF maakte (bijv. "Adobe Acrobat"),
                # NIET voor de boekuitgever. Publisher komt daarom altijd uit OPF sidecar.

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
                pass
        except Exception as e:
            print(f"PDF native metadata error: {e}")

        # STAP 2: Lees sidecar voor extra velden die PDF niet ondersteunt
        # én als fallback voor lege native velden
        sidecar_meta = read_sidecar_metadata(filepath)

        if sidecar_meta:
            # Velden die PDF NIET native ondersteunt - alleen uit sidecar
            # PDF native: title, author, subject (tags)
            # PDF mist: isbn, year, language, series, series_index, rating, notes, publisher,
            #           author_sort, publication_date, pages, translator, illustrator, description
            meta.isbn = sidecar_meta.isbn or ''
            meta.series = sidecar_meta.series or ''
            meta.series_index = sidecar_meta.series_index
            meta.rating = sidecar_meta.rating
            meta.notes = sidecar_meta.notes or ''
            meta.year = sidecar_meta.year or ''
            meta.publisher = sidecar_meta.publisher or ''
            meta.language = sidecar_meta.language or ''
            # Nieuwe velden
            meta.author_sort = sidecar_meta.author_sort or ''
            meta.publication_date = sidecar_meta.publication_date or ''
            meta.pages = sidecar_meta.pages or ''
            meta.translator = sidecar_meta.translator or ''
            meta.illustrator = sidecar_meta.illustrator or ''

            # Fallback naar sidecar voor problematische PDFs waar native velden niet werken
            if not meta.booktitle or meta.booktitle == filepath.stem:
                if sidecar_meta.booktitle:
                    meta.booktitle = sidecar_meta.booktitle
            if not meta.authors and sidecar_meta.authors:
                meta.authors = sidecar_meta.authors
            if not meta.description and sidecar_meta.description:
                meta.description = sidecar_meta.description
            # Tags: sidecar heeft PRIORITEIT boven PDF keywords.
            # PDF keywords bevat vaak irrelevante data (URLs, generator info).
            # Sidecar bevat door gebruiker bewerkte tags die we willen tonen.
            if sidecar_meta.tags:
                meta.tags = sidecar_meta.tags

        return meta

    def _extract_comic(self, filepath: Path) -> BookMetadata:
        """Extract metadata from CBZ/CBR comic archive.

        CBZ: Leest ComicInfo.xml direct voor tags (kan ook schrijven).
        CBR: Tags komen uit OPF sidecar file (RAR is niet schrijfbaar).
        Gebruikt comicbox library voor andere metadata.
        """
        meta = BookMetadata(booktitle=filepath.stem)
        is_cbr = filepath.suffix.lower() == '.cbr'

        # Voor CBZ: lees ComicInfo.xml direct voor tags
        if not is_cbr:
            try:
                import zipfile
                import xml.etree.ElementTree as ET

                with zipfile.ZipFile(filepath, 'r') as zf:
                    # Case-insensitive zoeken naar ComicInfo.xml
                    comicinfo_name = None
                    for name in zf.namelist():
                        if name.lower() == 'comicinfo.xml':
                            comicinfo_name = name
                            break
                    if comicinfo_name:
                        comicinfo_content = zf.read(comicinfo_name).decode('utf-8')
                        root = ET.fromstring(comicinfo_content)

                        # Lees Tags element (komma-gescheiden)
                        tags_elem = root.find('Tags')
                        if tags_elem is not None and tags_elem.text:
                            meta.tags = [t.strip() for t in tags_elem.text.split(',') if t.strip()]

                        # Lees ook andere basis metadata uit ComicInfo.xml
                        title_elem = root.find('Title')
                        if title_elem is not None and title_elem.text:
                            meta.booktitle = title_elem.text

                        series_elem = root.find('Series')
                        if series_elem is not None and series_elem.text:
                            meta.series = series_elem.text
                            if not meta.booktitle or meta.booktitle == filepath.stem:
                                meta.booktitle = series_elem.text

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

                        # Extra velden uit ComicInfo.xml
                        year_elem = root.find('Year')
                        if year_elem is not None and year_elem.text:
                            meta.year = year_elem.text

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

                        # Illustrator uit Penciller veld
                        penciller_elem = root.find('Penciller')
                        if penciller_elem is not None and penciller_elem.text:
                            meta.illustrator = penciller_elem.text

                        # Translator (niet standaard maar we ondersteunen het)
                        translator_elem = root.find('Translator')
                        if translator_elem is not None and translator_elem.text:
                            meta.translator = translator_elem.text

                        # Extra velden uit sidecar (isbn, author_sort, publication_date)
                        sidecar_meta = read_sidecar_metadata(filepath)
                        if sidecar_meta:
                            if sidecar_meta.isbn:
                                meta.isbn = sidecar_meta.isbn
                            if sidecar_meta.author_sort:
                                meta.author_sort = sidecar_meta.author_sort
                            if sidecar_meta.publication_date:
                                meta.publication_date = sidecar_meta.publication_date

            except Exception as e:
                # Log exception voor debugging, maar ga door met fallbacks
                print(f"Error reading ComicInfo.xml from {filepath}: {e}")

        # Gebruik comicbox voor andere metadata (titel, auteur etc.)
        if not meta.booktitle or meta.booktitle == filepath.stem:
            try:
                from comicbox.comic_archive import ComicArchive
                car = ComicArchive(filepath)
                comic_meta = car.get_metadata()

                if comic_meta:
                    if hasattr(comic_meta, 'series') and comic_meta.series:
                        meta.series = comic_meta.series
                        if not meta.booktitle or meta.booktitle == filepath.stem:
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

            except ImportError:
                pass
            except Exception:
                pass

        # Voor CBR: tags en extra velden komen uit sidecar file (RAR is niet schrijfbaar)
        # ALLE velden moeten uit sidecar gelezen worden omdat RAR niet schrijfbaar is
        if is_cbr:
            sidecar_meta = read_sidecar_metadata(filepath)
            if sidecar_meta:
                meta.tags = sidecar_meta.tags or []
                # Basis velden - sidecar overschrijft comicbox waarden (user edits)
                if sidecar_meta.booktitle:
                    meta.booktitle = sidecar_meta.booktitle
                if sidecar_meta.authors:
                    meta.authors = sidecar_meta.authors
                if sidecar_meta.publisher:
                    meta.publisher = sidecar_meta.publisher
                if sidecar_meta.series:
                    meta.series = sidecar_meta.series
                if sidecar_meta.series_index is not None:
                    meta.series_index = sidecar_meta.series_index
                # Extra velden
                meta.isbn = sidecar_meta.isbn or ''
                meta.rating = sidecar_meta.rating
                meta.notes = sidecar_meta.notes or ''
                meta.year = sidecar_meta.year or ''
                meta.description = sidecar_meta.description or ''
                meta.language = sidecar_meta.language or ''
                # Nieuwe velden
                meta.author_sort = sidecar_meta.author_sort or ''
                meta.publication_date = sidecar_meta.publication_date or ''
                meta.pages = sidecar_meta.pages or ''
                meta.translator = sidecar_meta.translator or ''
                meta.illustrator = sidecar_meta.illustrator or ''

        return meta

    def _extract_isbn(self, identifier: str) -> str:
        """Extract ISBN from identifier string.

        Verwijdert bekende prefixes. Als de waarde exact 10 of 13 cijfers bevat,
        wordt een opgeschoonde versie (alleen cijfers/X) geretourneerd.
        Anders wordt de originele waarde behouden.
        UUID waarden (urn:uuid:) worden genegeerd.
        """
        import re

        if not identifier:
            return ""

        identifier = str(identifier).strip()

        # Skip UUID waarden - dit is geen ISBN
        if identifier.lower().startswith('urn:uuid:'):
            return ""

        # Remove common prefixes (case-insensitive)
        identifier_upper = identifier.upper()
        for prefix in ['ISBN:', 'ISBN-10:', 'ISBN-13:', 'URN:ISBN:']:
            if identifier_upper.startswith(prefix):
                identifier = identifier[len(prefix):].strip()
                break

        # Clean versie: alleen cijfers en X
        cleaned = re.sub(r'[^0-9X]', '', identifier.upper())

        # Als exact 10 of 13 cijfers: retourneer opgeschoonde versie
        if len(cleaned) in (10, 13):
            return cleaned

        # Anders: behoud originele waarde (na prefix verwijdering)
        return identifier

    def _extract_markdown(self, filepath: Path) -> BookMetadata:
        """
        Extract metadata from markdown file.

        Leest alleen metadata uit YAML frontmatter (tekst tussen --- en ---).
        Als er geen frontmatter is, wordt alleen de bestandsnaam als titel gebruikt.

        Args:
            filepath: Path naar het markdown bestand
        """
        meta = BookMetadata(booktitle=filepath.stem)

        try:
            content = filepath.read_text(encoding='utf-8')
            content = content.replace('\r\n', '\n').replace('\r', '\n')

            # Check for YAML frontmatter
            yaml_match = re.match(r'^---[ \t]*\n(.*?)\n---', content, re.DOTALL)

            if yaml_match:
                # YAML frontmatter exists - parse metadata from it
                yaml_content = yaml_match.group(1)
                meta = self._parse_markdown_fields(yaml_content, meta)
            # Geen frontmatter = geen metadata (bestandsnaam wordt titel)

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
        publisher_field = self.field_names.get('publisher') or 'publisher'
        year_field = self.field_names.get('year') or 'year'
        language_field = self.field_names.get('language') or 'language'
        series_field = self.field_names.get('series') or 'series'
        series_index_field = self.field_names.get('series_index') or 'series_index'
        rating_field = self.field_names.get('rating') or 'rating'
        description_field = self.field_names.get('description') or 'description'
        notes_field = self.field_names.get('notes') or 'notes'

        # Helper to find field value - NO fallback, only use configured name
        # Ondersteunt beide formaten: "field: value" en "[field]: value" (bracket notation)
        def find_field(field_name: str) -> str:
            # Probeer eerst zonder brackets (YAML style)
            pattern = rf'^{re.escape(field_name)}:\s*(.+?)$'
            match = re.search(pattern, content, re.MULTILINE | re.IGNORECASE)
            if match:
                return self._clean_field_value(match.group(1))
            # Probeer met brackets (flat/multi-book style)
            pattern_bracket = rf'^\[{re.escape(field_name)}\]:\s*(.+?)$'
            match_bracket = re.search(pattern_bracket, content, re.MULTILINE | re.IGNORECASE)
            if match_bracket:
                return self._clean_field_value(match_bracket.group(1))
            return ""

        # Extract booktitle
        title = find_field(title_field)
        if title:
            meta.booktitle = title

        # Extract author(s)
        author = find_field(author_field)
        if author:
            # Don't split on comma - "Last, First" is a valid single author name
            # Only split on semicolon which is unambiguous separator
            if ';' in author:
                meta.authors = [a.strip() for a in author.split(';')]
            else:
                meta.authors = [author]

        # Extract ISBN - voor markdown: accepteer elke waarde (geen strikte validatie)
        isbn_val = find_field(isbn_field)
        if isbn_val:
            meta.isbn = isbn_val

        # Extract cover URL for reference
        cover = find_field(cover_field)
        if cover:
            meta.cover_url = cover

        # Extract tags - ondersteunt meerdere formaten
        tags = self._parse_tags(content, tags_field)
        if tags:
            meta.tags = tags

        # Extract publisher
        publisher = find_field(publisher_field)
        if publisher:
            meta.publisher = publisher

        # Extract year
        year = find_field(year_field)
        if year:
            meta.year = year

        # Extract language
        language = find_field(language_field)
        if language:
            meta.language = language

        # Extract series
        series = find_field(series_field)
        if series:
            meta.series = series

        # Extract series_index
        series_index = find_field(series_index_field)
        if series_index:
            try:
                meta.series_index = float(series_index)
            except ValueError:
                pass

        # Extract rating
        rating = find_field(rating_field)
        if rating:
            try:
                meta.rating = float(rating)
            except ValueError:
                pass

        # Extract description
        description = find_field(description_field)
        if description:
            meta.description = description

        # Extract notes
        notes = find_field(notes_field)
        if notes:
            meta.notes = notes

        # Extract extra velden: author_sort, publication_date, pages, translator, illustrator
        author_sort_field = self.field_names.get('author_sort') or 'author_sort'
        author_sort = find_field(author_sort_field)
        if author_sort:
            meta.author_sort = author_sort

        publication_date_field = self.field_names.get('publication_date') or 'publication_date'
        publication_date = find_field(publication_date_field)
        if publication_date:
            meta.publication_date = publication_date

        pages_field = self.field_names.get('pages') or 'pages'
        pages = find_field(pages_field)
        if pages:
            meta.pages = pages

        translator_field = self.field_names.get('translator') or 'translator'
        translator = find_field(translator_field)
        if translator:
            meta.translator = translator

        illustrator_field = self.field_names.get('illustrator') or 'illustrator'
        illustrator = find_field(illustrator_field)
        if illustrator:
            meta.illustrator = illustrator

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
        4. Bracket notation: [tags]: fiction, sci-fi (flat/multi-book style)

        Tags worden genormaliseerd: getrimd, lege tags verwijderd. Case wordt behouden.
        """
        tags = []

        # Helper om beide formaten te proberen (met en zonder brackets)
        def try_patterns(base_pattern_func):
            # Probeer zonder brackets (YAML style)
            pattern = base_pattern_func(tags_field)
            match = re.search(pattern, content, re.MULTILINE | re.IGNORECASE)
            if match:
                return match
            # Probeer met brackets (flat/multi-book style)
            pattern_bracket = base_pattern_func(f'[{tags_field}]')
            match_bracket = re.search(pattern_bracket, content, re.MULTILINE | re.IGNORECASE)
            return match_bracket

        # Format 1: YAML inline array [tag1, tag2, ...]
        inline_match = try_patterns(lambda f: rf'^{re.escape(f)}:\s*\[(.*?)\]')
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
        block_match = try_patterns(lambda f: rf'^{re.escape(f)}:\s*$\n((?:\s+-\s+.+\n?)+)')
        if block_match:
            items_block = block_match.group(1)
            for line in items_block.split('\n'):
                line = line.strip()
                if line.startswith('-'):
                    tag = line[1:].strip().strip('"\'')
                    if tag:
                        tags.append(tag)
            return self._normalize_tags(tags)

        # Format 3: Simple comma-separated (ook bracket notation)
        simple_match = try_patterns(lambda f: rf'^{re.escape(f)}:\s*(.+?)$')
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
        Normaliseer tags: trim, verwijder lege en duplicaten.
        Behoudt originele volgorde (eerste occurrence) en case.
        Duplicaat-detectie is case-insensitive, maar de originele case wordt behouden.
        """
        seen = set()
        normalized = []
        for tag in tags:
            tag_stripped = tag.strip()
            # Case-sensitive: Kunst en kunst zijn verschillende tags
            if tag_stripped and tag_stripped not in seen:
                seen.add(tag_stripped)
                normalized.append(tag_stripped)
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


# =============================================================================
# Markdown Sidecar File Helpers
# =============================================================================
# Markdown sidecar files worden gebruikt voor metadata opslag bij bestands-
# formaten waar metadata niet direct in het bestand kan worden opgeslagen:
# - CBR (RAR formaat, niet schrijfbaar)
# - MOBI/AZW/AZW3 (ebookmeta library is onbetrouwbaar)
# - Problematische PDFs (sommige PDFs ondersteunen geen metadata wijzigingen)
#
# De sidecar file heeft dezelfde naam als het ebook maar met .md extensie.
# Bijvoorbeeld: book.cbr -> book.cbr.md
#
# Structuur: YAML frontmatter met alle metadata velden.
# Tags met komma's worden gequote in de file maar quotes verborgen in UI.
# =============================================================================

def find_cover_for_ebook(ebook_path: Path) -> Optional[str]:
    """Find the cover file for an ebook and return its filename.

    Looks for cover files in the same folder as the ebook with the pattern:
    {ebook_name}.{cover_ext} (e.g., book.pdf.jpg, book.epub.png)

    Args:
        ebook_path: Path to the ebook file

    Returns:
        Cover filename (e.g., "book.pdf.png") if found, None otherwise
    """
    cover_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
    folder = ebook_path.parent
    ebook_name = ebook_path.name

    # Look for cover with pattern: book.pdf.jpg, book.pdf.png, etc.
    for ext in cover_extensions:
        cover_name = ebook_name + ext
        cover_path = folder / cover_name
        if cover_path.exists():
            return cover_name

    return None


def consolidate_metadata_to_sidecar(ebook_path: Path,
                                     source_metadata: dict = None,
                                     filter_redundant: bool = True) -> dict:
    """Consolidate metadata from various sources for writing to MD sidecar.

    This is the central function for merging metadata from:
    - Source sidecar (OPF for Calibre2Libiry, existing MD for Libiry2Go)
    - Native ebook metadata (from the book file itself)

    Priority (native overrides source where both have values):
    1. Start with source_metadata as base (preserves user's notes, custom tags, etc.)
    2. Override with native ebook metadata where native has values

    Also sets the cover field to the cover filename if a cover exists next to
    the ebook (e.g., book.pdf.png). This allows Obsidian to display the cover.

    Used by:
    - Calibre2Libiry: source_metadata from read_calibre_opf()
    - Libiry2Go: source_metadata from read_sidecar_metadata()

    Args:
        ebook_path: Path to the ebook file
        source_metadata: Optional dict with metadata from source (OPF or existing MD)
        filter_redundant: If True, remove values that match native (e.g., same language)

    Returns:
        Merged metadata dict ready for write_sidecar_metadata()
    """
    from core.libiry_style import languages_equivalent

    # Start with source metadata as base (or empty dict)
    result = dict(source_metadata) if source_metadata else {}

    # Check if cover file exists next to ebook and set cover field
    cover_filename = find_cover_for_ebook(ebook_path)
    if cover_filename:
        result['cover'] = cover_filename

    # Extract native metadata from the ebook
    try:
        extractor = MetadataExtractor()
        native = extractor.extract(ebook_path)
    except Exception:
        # If extraction fails, return source metadata as-is
        return result

    # Fields where native should override source when native has a value
    # These are "authoritative" fields from the book itself
    override_fields = [
        ('booktitle', native.booktitle),
        ('author', ', '.join(native.authors) if native.authors else ''),
        ('isbn', native.isbn),
        ('publisher', native.publisher),
        ('language', native.language),
        ('year', native.year),
        ('description', native.description),
        ('series', native.series),
        ('series_index', native.series_index),
        ('pages', native.pages),
    ]

    for field, native_value in override_fields:
        if native_value:  # Native has a value
            if field == 'language':
                from core.libiry_style import is_undefined_language

                # Special handling for language:
                # - UND (undefined) should NOT override a real language from sidecar
                # - Real languages should override, unless equivalent (then remove redundant)
                source_lang = result.get('language', '')

                if is_undefined_language(native_value):
                    # Native is UND - keep sidecar language if it has one
                    # Don't override with UND
                    continue

                if filter_redundant and source_lang and languages_equivalent(source_lang, native_value):
                    # Languages are equivalent - remove redundant sidecar value
                    result.pop('language', None)
                    continue

                # Native has real language - use it
                result[field] = native_value

            elif field == 'author':
                from core.libiry_style import authors_equivalent

                # Special handling for author:
                # "Niccolò Machiavelli" and "Machiavelli, Niccolò" are equivalent
                source_author = result.get('author', '')

                if filter_redundant and source_author and authors_equivalent(source_author, native_value):
                    # Authors are equivalent - remove redundant sidecar value
                    result.pop('author', None)
                    continue

                # Native author overrides
                result[field] = native_value
            else:
                # Normal field - native overrides source
                result[field] = native_value

    # Tags: merge native tags with source tags (no duplicates)
    if native.tags:
        source_tags = result.get('tags', [])
        if isinstance(source_tags, str):
            source_tags = [t.strip() for t in source_tags.split(',') if t.strip()]
        # Merge: source tags + native tags (deduplicated, preserve order)
        merged_tags = list(source_tags)
        for tag in native.tags:
            if tag not in merged_tags:
                merged_tags.append(tag)
        if merged_tags:
            result['tags'] = merged_tags

    return result


def get_sidecar_path(ebook_path: Path) -> Path:
    """Get the path to the Markdown sidecar file for an ebook.

    Args:
        ebook_path: Path naar het ebook bestand

    Returns:
        Path naar de corresponderende sidecar file (originele naam + .md extensie)
        Bijv: book.mobi -> book.mobi.md
        Dit voorkomt conflicten als je book.pdf en book.mobi in dezelfde folder hebt.
    """
    # Voeg .md toe aan de volledige bestandsnaam (niet vervangen)
    # book.mobi -> book.mobi.md (niet book.md)
    return ebook_path.parent / (ebook_path.name + '.md')


def read_sidecar_as_dict(ebook_path: Path) -> Optional[dict]:
    """Read sidecar YAML frontmatter as a plain dict.

    Unlike read_sidecar_metadata() which returns BookMetadata, this returns
    a raw dict suitable for use with consolidate_metadata_to_sidecar().

    Args:
        ebook_path: Path to the ebook file (not the sidecar itself)

    Returns:
        Dict with metadata from sidecar, or None if sidecar doesn't exist
    """
    sidecar_path = get_sidecar_path(ebook_path)
    if not sidecar_path.exists():
        return None

    try:
        content = sidecar_path.read_text(encoding='utf-8')
        content = content.replace('\r\n', '\n').replace('\r', '\n')

        # Check for YAML frontmatter (between --- and ---)
        yaml_match = re.match(r'^---[ \t]*\n(.*?)\n---', content, re.DOTALL)
        if not yaml_match:
            return None

        yaml_content = yaml_match.group(1)
        result = {}

        # Helper to find YAML field value
        # Supports single-line values and multi-line values (with or without |)
        def find_field(field_name: str) -> str:
            # First try multi-line: field: followed by indented lines
            # This works with or without the | character
            pattern_multi = rf'^{re.escape(field_name)}:\s*[|>]?\s*\n((?:[ \t]+.+\n?)+)'
            match_multi = re.search(pattern_multi, yaml_content, re.MULTILINE | re.IGNORECASE)
            if match_multi:
                lines = match_multi.group(1).split('\n')
                min_indent = float('inf')
                for line in lines:
                    if line.strip():
                        indent = len(line) - len(line.lstrip())
                        min_indent = min(min_indent, indent)
                if min_indent == float('inf'):
                    min_indent = 0
                cleaned_lines = []
                for line in lines:
                    if len(line) >= min_indent:
                        cleaned_lines.append(line[int(min_indent):])
                    else:
                        cleaned_lines.append(line.lstrip())
                return '\n'.join(cleaned_lines).strip()

            # Fallback: try single-line (field: value on same line)
            pattern = rf'^{re.escape(field_name)}:\s*(.+?)$'
            match = re.search(pattern, yaml_content, re.MULTILINE | re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                # Remove surrounding quotes
                if (value.startswith('"') and value.endswith('"')) or \
                   (value.startswith("'") and value.endswith("'")):
                    value = value[1:-1]
                return value

            return ''

        # Parse all metadata fields
        for field in ['booktitle', 'author', 'author_sort', 'isbn', 'rating',
                      'publisher', 'year', 'publication_date', 'language',
                      'pages', 'series', 'series_index', 'translator',
                      'illustrator', 'description', 'notes', 'cover']:
            value = find_field(field)
            if value:
                result[field] = value

        # Parse tags (can be YAML list or comma-separated)
        tags_str = find_field('tags')
        if tags_str:
            if tags_str.startswith('[') and tags_str.endswith(']'):
                # YAML array
                tags = [t.strip().strip('"\'') for t in tags_str[1:-1].split(',')]
                result['tags'] = [t for t in tags if t]
            else:
                # Comma-separated
                tags = [t.strip().strip('"\'') for t in tags_str.split(',')]
                result['tags'] = [t for t in tags if t]

        return result if result else None

    except Exception:
        return None


# Backwards compatibility alias - wordt in toekomstige versie verwijderd
def get_opf_path(ebook_path: Path) -> Path:
    """DEPRECATED: Gebruik get_sidecar_path() in plaats hiervan."""
    return get_sidecar_path(ebook_path)


def _format_tags_for_yaml(tags: List[str]) -> List[str]:
    """Formatteer tags voor YAML output als list format (Obsidian-compatibel).

    Returns een lijst van geformatteerde regels voor YAML block list format:
        tags:
          - fiction
          - sci-fi

    Tags die speciale YAML karakters bevatten worden gequote.
    Dit format is compatible met Obsidian en andere YAML parsers.

    Voorbeelden:
        ['fiction', 'sci-fi'] -> ['tags:', '  - fiction', '  - sci-fi']
        ['fiction', 'Brando, Marlon'] -> ['tags:', '  - fiction', '  - "Brando, Marlon"']
    """
    if not tags:
        return []

    lines = ['tags:']
    for tag in tags:
        # Tags met speciale YAML karakters worden gequote
        # Speciale karakters: komma, dubbele punt, haakjes, etc.
        if any(c in tag for c in ':#[]{}|>&*!,'):
            # Escape eventuele quotes in de tag
            escaped = tag.replace('"', '\\"')
            lines.append(f'  - "{escaped}"')
        else:
            lines.append(f'  - {tag}')

    return lines


def _parse_tags_from_yaml(tags_str: str) -> List[str]:
    """Parse tags uit YAML string.

    Ondersteunt:
    - YAML block list: "  - fiction\\n  - sci-fi" (Obsidian-compatibel)
    - Komma-gescheiden: fiction, sci-fi
    - Gequote tags: fiction, "Brando, Marlon", sci-fi
    - YAML array: [fiction, sci-fi]

    Quotes worden verwijderd uit de output.
    """
    if not tags_str:
        return []

    tags_str = tags_str.strip()

    # Format 1: YAML block list met "- item" syntax (Obsidian-compatibel)
    # Dit is het primaire format dat we nu schrijven
    if '\n' in tags_str or tags_str.startswith('-'):
        tags = []
        for line in tags_str.split('\n'):
            line = line.strip()
            if line.startswith('-'):
                # Verwijder de "- " prefix
                tag = line[1:].strip()
                # Verwijder quotes indien aanwezig
                if (tag.startswith('"') and tag.endswith('"')) or \
                   (tag.startswith("'") and tag.endswith("'")):
                    tag = tag[1:-1]
                # Unescape quotes
                tag = tag.replace('\\"', '"').replace("\\'", "'")
                if tag:
                    tags.append(tag)
        if tags:
            return tags

    # Format 2: YAML array formaat: [tag1, tag2]
    if tags_str.startswith('[') and tags_str.endswith(']'):
        tags_str = tags_str[1:-1]

    # Format 3: Komma-gescheiden (inclusief gequote tags)
    tags = []
    current = ''
    in_quotes = False
    quote_char = None
    i = 0

    while i < len(tags_str):
        char = tags_str[i]

        if char in ('"', "'") and not in_quotes:
            # Start van quoted string
            in_quotes = True
            quote_char = char
        elif char == quote_char and in_quotes:
            # Eind van quoted string (check voor escaped quote)
            if i > 0 and tags_str[i-1] == '\\':
                # Escaped quote - voeg toe aan current
                current = current[:-1] + char  # Verwijder backslash, voeg quote toe
            else:
                in_quotes = False
                quote_char = None
        elif char == ',' and not in_quotes:
            # Separator gevonden
            tag = current.strip()
            if tag:
                tags.append(tag)
            current = ''
        else:
            current += char

        i += 1

    # Laatste tag
    tag = current.strip()
    if tag:
        tags.append(tag)

    return tags


def read_sidecar_metadata(ebook_path: Path) -> Optional[BookMetadata]:
    """Lees alle metadata uit een Markdown sidecar file (YAML frontmatter).

    Leest: booktitle, author, isbn, publisher, language, description, year,
    tags, series, series_index, rating, notes, author_sort, publication_date,
    pages, translator, illustrator.

    Args:
        ebook_path: Path naar het ebook bestand (niet de sidecar zelf)

    Returns:
        BookMetadata object met alle gevonden velden, of None als sidecar niet bestaat
    """
    sidecar_path = get_sidecar_path(ebook_path)
    if not sidecar_path.exists():
        return None

    try:
        content = sidecar_path.read_text(encoding='utf-8')
        content = content.replace('\r\n', '\n').replace('\r', '\n')

        # Check for YAML frontmatter (tussen --- en ---)
        yaml_match = re.match(r'^---[ \t]*\n(.*?)\n---', content, re.DOTALL)
        if not yaml_match:
            return None

        yaml_content = yaml_match.group(1)
        meta = BookMetadata()

        # Helper to find YAML field value
        # Supports single-line values and multi-line values (with or without |)
        def find_field(field_name: str) -> str:
            # First try multi-line: field: followed by indented lines
            # This works with or without the | character
            # Pattern: field: [optional | or >] newline, then indented content
            pattern_multi = rf'^{re.escape(field_name)}:\s*[|>]?\s*\n((?:[ \t]+.+\n?)+)'
            match_multi = re.search(pattern_multi, yaml_content, re.MULTILINE | re.IGNORECASE)
            if match_multi:
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
            pattern = rf'^{re.escape(field_name)}:\s*(.+?)$'
            match = re.search(pattern, yaml_content, re.MULTILINE | re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                # Remove surrounding quotes
                if (value.startswith('"') and value.endswith('"')) or \
                   (value.startswith("'") and value.endswith("'")):
                    value = value[1:-1]
                return value

            return ''

        # Parse velden
        meta.booktitle = find_field('booktitle')

        # Author kan string of lijst zijn
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
        meta.publisher = find_field('publisher')
        meta.language = find_field('language')
        meta.year = find_field('year')
        meta.publication_date = find_field('publication_date')
        meta.pages = find_field('pages')
        meta.series = find_field('series')
        meta.translator = find_field('translator')
        meta.illustrator = find_field('illustrator')
        meta.description = find_field('description')
        meta.notes = find_field('notes')

        # Series index
        series_index_str = find_field('series_index')
        if series_index_str:
            try:
                meta.series_index = float(series_index_str)
            except (ValueError, TypeError):
                pass

        # Rating
        rating_str = find_field('rating')
        if rating_str:
            try:
                meta.rating = float(rating_str)
            except (ValueError, TypeError):
                pass

        # Tags - ondersteun zowel YAML array als komma-gescheiden string
        tags_str = find_field('tags')
        if tags_str:
            meta.tags = _parse_tags_from_yaml(tags_str)

        return meta

    except Exception as e:
        print(f"Error reading sidecar metadata from {sidecar_path}: {e}")
        import traceback
        traceback.print_exc()
        return None


def write_sidecar_metadata(sidecar_path: Path, metadata: dict) -> bool:
    """Schrijf volledige metadata naar een Markdown sidecar file (YAML frontmatter).

    Maakt een nieuwe sidecar file aan of update een bestaande.
    Ondersteunt alle metadata velden: booktitle, author, isbn, tags,
    rating, publisher, year, language, series, series_index, description, notes,
    author_sort, publication_date, pages, translator, illustrator.

    Args:
        sidecar_path: Path naar de sidecar file (direct, niet het ebook)
        metadata: Dict met metadata velden

    Returns:
        True als succesvol, False bij fout
    """
    try:
        lines = ['---']

        # Volgorde van velden (gebaseerd op plan)
        # Single-line velden
        single_fields = [
            ('booktitle', 'booktitle'),
            ('author', 'author'),
            ('author_sort', 'author_sort'),
            ('isbn', 'isbn'),
            ('rating', 'rating'),
            ('publisher', 'publisher'),
            ('year', 'year'),
            ('publication_date', 'publication_date'),
            ('language', 'language'),
            ('pages', 'pages'),
            ('series', 'series'),
            ('series_index', 'series_index'),
            ('translator', 'translator'),
            ('illustrator', 'illustrator'),
            ('cover', 'cover'),
        ]

        for meta_key, yaml_key in single_fields:
            if meta_key in metadata and metadata[meta_key]:
                value = metadata[meta_key]
                # Strings met speciale karakters quoten
                if isinstance(value, str) and any(c in value for c in ':#[]{}|>&*!'):
                    value = f'"{value}"'
                lines.append(f'{yaml_key}: {value}')

        # Tags als YAML block list (Obsidian-compatibel format)
        if 'tags' in metadata and metadata['tags']:
            tags = metadata['tags']
            if isinstance(tags, list):
                tag_lines = _format_tags_for_yaml(tags)
                lines.extend(tag_lines)
            elif tags:
                # String: converteer naar list en formatteer
                tag_list = [t.strip() for t in str(tags).split(',') if t.strip()]
                if tag_list:
                    tag_lines = _format_tags_for_yaml(tag_list)
                    lines.extend(tag_lines)

        # Multi-line fields (description, notes)
        # Written without YAML | operator for cleaner human-readable format
        # Our read functions handle both formats (with or without |)
        for field in ['description', 'notes']:
            if field in metadata and metadata[field]:
                value = str(metadata[field])
                if '\n' in value:
                    # Multi-line: just indent continuation lines (no | needed)
                    lines.append(f'{field}:')
                    for line in value.split('\n'):
                        lines.append(f'  {line}')
                else:
                    # Single line
                    if any(c in value for c in ':#[]{}|>&*!'):
                        value = f'"{value}"'
                    lines.append(f'{field}: {value}')

        lines.append('---')
        lines.append('')  # Lege regel na frontmatter

        # Schrijf naar bestand
        sidecar_path.write_text('\n'.join(lines), encoding='utf-8')
        return True

    except Exception as e:
        print(f"Error writing sidecar metadata to {sidecar_path}: {e}")
        return False


def modify_sidecar_tags(ebook_path: Path, tags_to_remove: set, tags_to_add: set) -> bool:
    """Wijzig tags in een Markdown sidecar file.

    Ondersteunt meerdere tags tegelijk toevoegen of verwijderen.

    Args:
        ebook_path: Path naar het ebook bestand
        tags_to_remove: Set van tags om te verwijderen (case-sensitive)
        tags_to_add: Set van tags om toe te voegen (case-sensitive)

    Returns:
        True als wijzigingen gemaakt zijn, False anders
    """
    # Lees huidige metadata
    current_meta = read_sidecar_metadata(ebook_path)
    current_tags = current_meta.tags if current_meta else []

    # Pas tags aan - verwijder tags (case-sensitive)
    new_tags = [t for t in current_tags if t not in tags_to_remove]
    removed_count = len(current_tags) - len(new_tags)

    # Voeg alle nieuwe tags toe die er nog niet zijn (case-sensitive)
    tags_added = []
    for tag_to_add in sorted(tags_to_add):  # Sorteer voor consistente volgorde
        if tag_to_add not in new_tags:
            new_tags.append(tag_to_add)
            tags_added.append(tag_to_add)

    # Check of er wijzigingen zijn
    if removed_count == 0 and not tags_added:
        return False

    # Bouw nieuwe metadata - behoud bestaande velden
    sidecar_path = get_sidecar_path(ebook_path)

    new_metadata = {}
    if current_meta:
        # Kopieer alle niet-lege velden
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
        if current_meta.year:
            new_metadata['year'] = current_meta.year
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

    # Schrijf naar sidecar
    return write_sidecar_metadata(sidecar_path, new_metadata)


# =============================================================================
# Backwards Compatibility Aliases
# =============================================================================
# Deze functies roepen de nieuwe sidecar functies aan voor backward compatibility.
# Ze worden in een toekomstige versie verwijderd.
# =============================================================================

def read_opf_metadata(ebook_path: Path) -> Optional[BookMetadata]:
    """DEPRECATED: Gebruik read_sidecar_metadata() in plaats hiervan."""
    return read_sidecar_metadata(ebook_path)


def write_opf_metadata(sidecar_path: Path, metadata: dict) -> bool:
    """DEPRECATED: Gebruik write_sidecar_metadata() in plaats hiervan."""
    return write_sidecar_metadata(sidecar_path, metadata)


def modify_opf_tags(ebook_path: Path, tags_to_remove: set, tags_to_add: set) -> bool:
    """DEPRECATED: Gebruik modify_sidecar_tags() in plaats hiervan."""
    return modify_sidecar_tags(ebook_path, tags_to_remove, tags_to_add)


# =============================================================================
# VERWIJDERDE FUNCTIES (niet meer nodig met nieuwe sidecar structuur)
# =============================================================================
# read_opf_tags() en write_opf_tags() zijn verwijderd.
# Gebruik read_sidecar_metadata() en write_sidecar_metadata() met 'tags' veld.
# =============================================================================


# =============================================================================
# Legacy OPF Reading Support (voor Calibre2Libiry conversie)
# =============================================================================

def read_legacy_opf_metadata(ebook_path: Path) -> Optional[BookMetadata]:
    """Lees alle metadata uit een OPF sidecar file.

    Leest: booktitle, author, isbn, publisher, language, description, year,
    tags, series, series_index, rating, notes, author_sort, publication_date,
    pages, translator, illustrator.

    Args:
        ebook_path: Path naar het ebook bestand (niet de OPF zelf)

    Returns:
        BookMetadata object met alle gevonden velden, of None als OPF niet bestaat
    """
    import xml.etree.ElementTree as ET

    opf_path = get_opf_path(ebook_path)
    if not opf_path.exists():
        return None

    try:
        tree = ET.parse(opf_path)
        root = tree.getroot()

        # Namespaces - gebruik Clark notatie voor betrouwbare matching
        DC_NS = 'http://purl.org/dc/elements/1.1/'
        OPF_NS = 'http://www.idpf.org/2007/opf'

        meta = BookMetadata()

        # Zoek metadata element - probeer verschillende varianten
        metadata_elem = root.find(f'.//{{{OPF_NS}}}metadata')
        if metadata_elem is None:
            metadata_elem = root.find('.//metadata')
        if metadata_elem is None:
            # Misschien is root zelf het metadata element of package
            if root.tag.endswith('metadata'):
                metadata_elem = root
            else:
                metadata_elem = root  # Zoek in root

        # Helper om DC element te vinden (probeert met en zonder namespace)
        # Robuuste versie die ook werkt als namespaces niet exact matchen
        def find_dc_text(tag):
            # Probeer met volledige DC namespace (Clark notatie)
            elem = metadata_elem.find(f'{{{DC_NS}}}{tag}')
            if elem is not None and elem.text:
                return elem.text.strip()
            # Probeer zonder namespace
            elem = metadata_elem.find(tag)
            if elem is not None and elem.text:
                return elem.text.strip()
            # Zoek in alle children - check zowel }tag als :tag patronen
            # Dit vangt namespace variaties op (bijv. {ns}tag of prefix:tag)
            for e in metadata_elem:
                # Check of tag eindigt op }localname (Clark notatie) of :localname (prefix)
                if e.tag.endswith(f'}}{tag}') or e.tag.endswith(f':{tag}') or e.tag == tag:
                    if e.text:
                        return e.text.strip()
            # Extra fallback: zoek ook in geneste elementen (sommige OPF structuren)
            for e in metadata_elem.iter():
                if e.tag.endswith(f'}}{tag}') or e.tag.endswith(f':{tag}') or e.tag == tag:
                    if e.text:
                        return e.text.strip()
            return ''

        meta.booktitle = find_dc_text('title')

        # Authors (kan meerdere dc:creator zijn)
        authors = []
        for creator in metadata_elem.findall(f'{{{DC_NS}}}creator'):
            if creator.text:
                authors.append(creator.text.strip())
        if not authors:
            for creator in metadata_elem.findall('creator'):
                if creator.text:
                    authors.append(creator.text.strip())
        if not authors:
            # Zoek in alle children
            for e in metadata_elem:
                if e.tag.endswith('creator') and e.text:
                    authors.append(e.text.strip())
        meta.authors = authors

        meta.isbn = find_dc_text('identifier')
        meta.publisher = find_dc_text('publisher')
        meta.language = find_dc_text('language')
        meta.description = find_dc_text('description')

        # Calibre-style meta elementen - zoek met en zonder namespace
        # Moet VOOR year lookup staan omdat calibre:year een meta element is
        meta_elements = list(metadata_elem.findall(f'{{{OPF_NS}}}meta'))
        meta_elements.extend(metadata_elem.findall('meta'))

        # Year: eerst uit calibre:year meta element (onze eigen opslag)
        # Dan fallback naar dc:date (voor compatibiliteit met oudere OPF bestanden)
        year_found = False
        for m in meta_elements:
            name = m.get('name', '')
            content = m.get('content', '')
            if name == 'calibre:year' and content:
                meta.year = content
                year_found = True
                break

        # Fallback: year uit dc:date als calibre:year niet gevonden
        if not year_found:
            date_text = find_dc_text('date')
            if date_text:
                # Probeer eerst 4-cijferig jaar te extracten (standaard datum formaat)
                year_match = re.match(r'^(\d{4})', date_text)
                if year_match:
                    meta.year = year_match.group(1)
                else:
                    # Accepteer ook andere waarden
                    meta.year = date_text

        # Tags uit dc:subject
        tags = []
        for subject in metadata_elem.findall(f'{{{DC_NS}}}subject'):
            if subject.text:
                tags.append(subject.text.strip())
        if not tags:
            for subject in metadata_elem.findall('subject'):
                if subject.text:
                    tags.append(subject.text.strip())
        if not tags:
            for e in metadata_elem:
                if e.tag.endswith('subject') and e.text:
                    tags.append(e.text.strip())
        meta.tags = tags

        # Verwerk overige meta elementen (series, rating, notes, pages, etc.)
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
                # Gebruik centrale conversie (met kwart-sterren)
                rating = convert_calibre_rating(content)
                if rating is not None:
                    meta.rating = rating
            elif name == 'calibre:user_notes' and content:
                meta.notes = content
            # Pages kan in verschillende meta elementen zitten
            elif name in ('rendition:page-count', 'calibre:pages') and content:
                meta.pages = content
            # Author sort als meta element (fallback voor bestanden zonder dc:creator)
            elif name == 'calibre:author_sort' and content:
                if not meta.author_sort:  # Alleen als nog niet gevonden
                    meta.author_sort = content

        # Author sort: opf:file-as attribuut op dc:creator (primaire methode)
        for creator in metadata_elem.findall(f'{{{DC_NS}}}creator'):
            file_as = creator.get(f'{{{OPF_NS}}}file-as') or creator.get('opf:file-as')
            if file_as:
                meta.author_sort = file_as.strip()  # Overschrijft meta element waarde
                break

        # Publication date: volledige dc:date waarde
        date_text = find_dc_text('date')
        if date_text:
            meta.publication_date = date_text

        # Translator en Illustrator: dc:contributor met opf:role
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
