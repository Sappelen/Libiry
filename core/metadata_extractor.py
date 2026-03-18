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


# Default field names - kunnen aangepast worden via customize.txt
# Deze namen worden gebruikt bij het parsen en schrijven van markdown bestanden
# Volgorde gebaseerd op Goodreads CSV export voor maximale compatibiliteit
DEFAULT_FIELD_NAMES = {
    'cover': 'cover',              # UI: cover afbeelding (niet in Goodreads)
    'booktitle': 'booktitle',      # Goodreads: Title
    'author': 'author',            # Goodreads: Author
    'author_sort': 'author_sort',  # Sorteer naam auteur
    'isbn': 'isbn',                # ISBN
    'rating': 'rating',            # Goodreads: My Rating
    'publisher': 'publisher',      # Goodreads: Publisher
    'year': 'year',                # Goodreads: Year Published
    'publication_date': 'publication_date',  # Volledige publicatiedatum
    'language': 'language',        # Taal
    'pages': 'pages',              # Aantal pagina's
    'tags': 'tags',                # Goodreads: Bookshelves
    'series': 'series',            # Serie naam
    'series_index': 'series_index',# Serie volgnummer
    'translator': 'translator',    # Vertaler
    'illustrator': 'illustrator',  # Illustrator
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

        # Voor onbekende bestandsformaten: check OPF sidecar voor tags
        # Dit ondersteunt file types zoals .rtf, .mp3, .txt etc.
        # OPF bestanden zelf worden overgeslagen (geen sidecar voor sidecar)
        if suffix != '.opf':
            meta = BookMetadata(booktitle=filepath.stem)
            # Lees tags uit OPF sidecar als die bestaat
            meta.tags = read_opf_tags(filepath)
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
                        # Calibre gebruikt 0-10, wij tonen 0-5
                        try:
                            calibre_rating = float(content)
                            meta.rating = calibre_rating / 2.0
                        except (ValueError, TypeError):
                            pass
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

        Tags worden ALTIJD uit OPF sidecar file gelezen (ebookmeta is onbetrouwbaar).
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

        # Tags en extra velden komen ALTIJD uit OPF sidecar file (MOBI tag support is onbetrouwbaar)
        # OPF waarden overschrijven ebookmeta waarden zodat user edits behouden blijven
        opf_meta = read_opf_metadata(filepath)
        if opf_meta:
            meta.tags = opf_meta.tags or []
            # Basis velden: OPF heeft prioriteit over ebookmeta (user edits)
            # BELANGRIJK: booktitle moet ook uit OPF gelezen worden anders gaan edits verloren
            if opf_meta.booktitle:
                meta.booktitle = opf_meta.booktitle
            if opf_meta.authors:
                meta.authors = opf_meta.authors
            if opf_meta.publisher:
                meta.publisher = opf_meta.publisher
            if opf_meta.language:
                meta.language = opf_meta.language
            # Extra velden die MOBI niet native ondersteunt
            meta.isbn = opf_meta.isbn or meta.isbn or ''
            meta.series = opf_meta.series or ''
            meta.series_index = opf_meta.series_index
            meta.rating = opf_meta.rating
            meta.notes = opf_meta.notes or ''
            meta.year = opf_meta.year or ''
            meta.description = opf_meta.description or ''
            # Nieuwe velden
            meta.author_sort = opf_meta.author_sort or ''
            meta.publication_date = opf_meta.publication_date or ''
            meta.pages = opf_meta.pages or ''
            meta.translator = opf_meta.translator or ''
            meta.illustrator = opf_meta.illustrator or ''
        else:
            meta.tags = []

        return meta

    def _extract_pdf(self, filepath: Path) -> BookMetadata:
        """Extract metadata from PDF file.

        Metadata wordt gelezen uit:
        1. OPF sidecar file als die bestaat (voor extra velden zoals isbn, series, rating)
        2. PDF native metadata (title, author, keywords/tags)

        OPF sidecar heeft prioriteit voor velden die PDF niet native ondersteunt.
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
                    # Split authors by common separators
                    authors_str = pdf_meta['author']
                    for sep in [';', ',', '&', ' and ']:
                        if sep in authors_str:
                            meta.authors = [a.strip() for a in authors_str.split(sep)]
                            break
                    else:
                        meta.authors = [authors_str]

                # Tags uit keywords veld
                if pdf_meta.get('keywords'):
                    meta.tags = [k.strip() for k in pdf_meta['keywords'].split(',') if k.strip()]

                # Description uit subject veld
                if pdf_meta.get('subject'):
                    meta.description = pdf_meta['subject']

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

        # STAP 2: Lees OPF sidecar voor extra velden die PDF niet ondersteunt
        # én als fallback voor lege native velden
        opf_meta = read_opf_metadata(filepath)

        if opf_meta:
            # Velden die PDF NIET native ondersteunt - alleen uit OPF
            # PDF native: title, author, subject (description), keywords (tags)
            # PDF mist: isbn, year, language, series, series_index, rating, notes, publisher,
            #           author_sort, publication_date, pages, translator, illustrator
            meta.isbn = opf_meta.isbn or ''
            meta.series = opf_meta.series or ''
            meta.series_index = opf_meta.series_index
            meta.rating = opf_meta.rating
            meta.notes = opf_meta.notes or ''
            meta.year = opf_meta.year or ''
            meta.publisher = opf_meta.publisher or ''
            meta.language = opf_meta.language or ''
            # Nieuwe velden
            meta.author_sort = opf_meta.author_sort or ''
            meta.publication_date = opf_meta.publication_date or ''
            meta.pages = opf_meta.pages or ''
            meta.translator = opf_meta.translator or ''
            meta.illustrator = opf_meta.illustrator or ''

            # Fallback naar OPF voor problematische PDFs waar native velden niet werken
            if not meta.booktitle or meta.booktitle == filepath.stem:
                if opf_meta.booktitle:
                    meta.booktitle = opf_meta.booktitle
            if not meta.authors and opf_meta.authors:
                meta.authors = opf_meta.authors
            if not meta.description and opf_meta.description:
                meta.description = opf_meta.description
            if not meta.tags and opf_meta.tags:
                meta.tags = opf_meta.tags

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

                        # Extra velden uit OPF sidecar (isbn, author_sort, publication_date)
                        opf_meta = read_opf_metadata(filepath)
                        if opf_meta:
                            if opf_meta.isbn:
                                meta.isbn = opf_meta.isbn
                            if opf_meta.author_sort:
                                meta.author_sort = opf_meta.author_sort
                            if opf_meta.publication_date:
                                meta.publication_date = opf_meta.publication_date

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

        # Voor CBR: tags en extra velden komen uit OPF sidecar file (RAR is niet schrijfbaar)
        # ALLE velden moeten uit OPF gelezen worden omdat RAR niet schrijfbaar is
        if is_cbr:
            opf_meta = read_opf_metadata(filepath)
            if opf_meta:
                meta.tags = opf_meta.tags or []
                # Basis velden - OPF overschrijft comicbox waarden (user edits)
                if opf_meta.booktitle:
                    meta.booktitle = opf_meta.booktitle
                if opf_meta.authors:
                    meta.authors = opf_meta.authors
                if opf_meta.publisher:
                    meta.publisher = opf_meta.publisher
                if opf_meta.series:
                    meta.series = opf_meta.series
                if opf_meta.series_index is not None:
                    meta.series_index = opf_meta.series_index
                # Extra velden
                meta.isbn = opf_meta.isbn or ''
                meta.rating = opf_meta.rating
                meta.notes = opf_meta.notes or ''
                meta.year = opf_meta.year or ''
                meta.description = opf_meta.description or ''
                meta.language = opf_meta.language or ''
                # Nieuwe velden
                meta.author_sort = opf_meta.author_sort or ''
                meta.publication_date = opf_meta.publication_date or ''
                meta.pages = opf_meta.pages or ''
                meta.translator = opf_meta.translator or ''
                meta.illustrator = opf_meta.illustrator or ''

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
            # Handle multiple authors (comma or semicolon separated)
            if ',' in author or ';' in author:
                meta.authors = [a.strip() for a in re.split(r'[,;]', author)]
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
# OPF Sidecar File Helpers
# =============================================================================
# OPF (Open Packaging Format) sidecar files worden gebruikt als fallback voor
# bestandsformaten waar tags niet direct in het bestand kunnen worden opgeslagen:
# - CBR (RAR formaat, niet schrijfbaar)
# - MOBI/AZW/AZW3 (ebookmeta library is onbetrouwbaar)
# - Problematische PDFs (sommige PDFs ondersteunen geen metadata wijzigingen)
#
# De OPF file heeft dezelfde naam als het ebook maar met .opf extensie.
# Bijvoorbeeld: book.cbr -> book.opf
# =============================================================================

def get_opf_path(ebook_path: Path) -> Path:
    """Geef het pad naar de OPF sidecar file voor een ebook.

    Args:
        ebook_path: Path naar het ebook bestand

    Returns:
        Path naar de corresponderende OPF file (originele naam + .opf extensie)
        Bijv: book.mobi -> book.mobi.opf
        Dit voorkomt conflicten als je book.pdf en book.mobi in dezelfde folder hebt.
    """
    # Voeg .opf toe aan de volledige bestandsnaam (niet vervangen)
    # book.mobi -> book.mobi.opf (niet book.opf)
    return ebook_path.parent / (ebook_path.name + '.opf')


def read_opf_metadata(ebook_path: Path) -> Optional[BookMetadata]:
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
                try:
                    meta.rating = float(content) / 2.0  # Calibre 0-10 -> 0-5
                except (ValueError, TypeError):
                    pass
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
        print(f"Error reading OPF metadata from {opf_path}: {e}")
        import traceback
        traceback.print_exc()
        return None


def read_opf_tags(ebook_path: Path) -> List[str]:
    """Lees tags uit een OPF sidecar file.

    Args:
        ebook_path: Path naar het ebook bestand (niet de OPF zelf)

    Returns:
        Lijst met tags, of lege lijst als OPF niet bestaat/leesbaar is
    """
    import xml.etree.ElementTree as ET

    opf_path = get_opf_path(ebook_path)
    if not opf_path.exists():
        return []

    try:
        tree = ET.parse(opf_path)
        root = tree.getroot()

        # OPF namespace
        ns = {
            'opf': 'http://www.idpf.org/2007/opf',
            'dc': 'http://purl.org/dc/elements/1.1/'
        }

        tags = []

        # Zoek dc:subject elementen (met namespace)
        for subject in root.findall('.//dc:subject', ns):
            if subject.text:
                tags.append(subject.text.strip())

        # Fallback: zoek zonder namespace (sommige OPF files)
        if not tags:
            for subject in root.iter():
                if subject.tag.endswith('subject') and subject.text:
                    tags.append(subject.text.strip())

        return tags

    except Exception:
        return []


def write_opf_tags(ebook_path: Path, tags: List[str]) -> bool:
    """Schrijf tags naar een OPF sidecar file.

    Maakt een nieuwe OPF file aan of update een bestaande.
    Als tags leeg is en OPF bestaat, wordt de OPF verwijderd.

    Args:
        ebook_path: Path naar het ebook bestand (niet de OPF zelf)
        tags: Lijst met tags om op te slaan

    Returns:
        True als succesvol, False bij fout
    """
    import xml.etree.ElementTree as ET

    opf_path = get_opf_path(ebook_path)

    # Als geen tags en OPF bestaat, verwijder de OPF
    if not tags:
        if opf_path.exists():
            try:
                opf_path.unlink()
            except Exception:
                pass
        return True

    try:
        # Maak OPF XML structuur
        # Registreer namespaces om mooie output te krijgen
        ET.register_namespace('', 'http://www.idpf.org/2007/opf')
        ET.register_namespace('dc', 'http://purl.org/dc/elements/1.1/')

        root = ET.Element('{http://www.idpf.org/2007/opf}package')
        root.set('version', '2.0')

        metadata = ET.SubElement(root, '{http://www.idpf.org/2007/opf}metadata')

        # Voeg dc:subject elementen toe voor elke tag
        for tag in tags:
            subject = ET.SubElement(metadata, '{http://purl.org/dc/elements/1.1/}subject')
            subject.text = tag

        # Schrijf naar bestand
        tree = ET.ElementTree(root)

        # Python 3.8+ ondersteunt xml_declaration in write()
        with open(opf_path, 'wb') as f:
            tree.write(f, encoding='UTF-8', xml_declaration=True)

        return True

    except Exception as e:
        print(f"Error writing OPF file {opf_path}: {e}")
        return False


def write_opf_metadata(opf_path: Path, metadata: dict) -> bool:
    """Schrijf volledige metadata naar een OPF sidecar file.

    Maakt een nieuwe OPF file aan of update een bestaande.
    Ondersteunt alle metadata velden: booktitle, author, isbn, tags,
    rating, publisher, year, language, series, series_index, description, notes,
    author_sort, publication_date, pages, translator, illustrator.

    Args:
        opf_path: Path naar de OPF file (direct, niet het ebook)
        metadata: Dict met metadata velden

    Returns:
        True als succesvol, False bij fout
    """
    import xml.etree.ElementTree as ET

    DC_NS = 'http://purl.org/dc/elements/1.1/'
    OPF_NS = 'http://www.idpf.org/2007/opf'

    try:
        # Registreer namespaces
        # Let op: 'opf' prefix is nodig voor attributes zoals opf:role en opf:file-as
        # Zonder deze registratie genereert ElementTree een willekeurige prefix (ns0, ns1)
        # wat het lezen van de attributen kan verstoren
        ET.register_namespace('', OPF_NS)
        ET.register_namespace('dc', DC_NS)
        ET.register_namespace('opf', OPF_NS)

        # Maak OPF structuur
        root = ET.Element(f'{{{OPF_NS}}}package')
        root.set('version', '2.0')

        meta_elem = ET.SubElement(root, f'{{{OPF_NS}}}metadata')

        # Mapping van metadata keys naar DC elementen
        # Let op: year wordt NIET via dc:date opgeslagen omdat publication_date
        # die waarde zou overschrijven. Year krijgt een apart meta element.
        dc_mapping = {
            'booktitle': 'title',
            'author': 'creator',
            'isbn': 'identifier',
            'publisher': 'publisher',
            'language': 'language',
            'description': 'description',
            # 'year' verwijderd - wordt apart opgeslagen als meta element
        }

        # Voeg DC elementen toe
        for key, dc_name in dc_mapping.items():
            if key in metadata and metadata[key]:
                elem = ET.SubElement(meta_elem, f'{{{DC_NS}}}{dc_name}')
                elem.text = str(metadata[key])

        # Tags als dc:subject
        if 'tags' in metadata and metadata['tags']:
            for tag in metadata['tags']:
                if tag:
                    subject = ET.SubElement(meta_elem, f'{{{DC_NS}}}subject')
                    subject.text = tag

        # Extra velden als meta elementen (Calibre-compatibel)
        # Series, series_index, rating gebruiken calibre: prefix
        if 'series' in metadata and metadata['series']:
            meta = ET.SubElement(meta_elem, 'meta')
            meta.set('name', 'calibre:series')
            meta.set('content', str(metadata['series']))

        if 'series_index' in metadata and metadata['series_index']:
            meta = ET.SubElement(meta_elem, 'meta')
            meta.set('name', 'calibre:series_index')
            meta.set('content', str(metadata['series_index']))

        if 'rating' in metadata and metadata['rating']:
            meta = ET.SubElement(meta_elem, 'meta')
            meta.set('name', 'calibre:rating')
            # Converteer van 0-5 naar 0-10 (Calibre schaal)
            try:
                rating_val = float(metadata['rating'])
                calibre_rating = int(rating_val * 2)
                meta.set('content', str(calibre_rating))
            except (ValueError, TypeError):
                meta.set('content', str(metadata['rating']))

        if 'notes' in metadata and metadata['notes']:
            meta = ET.SubElement(meta_elem, 'meta')
            meta.set('name', 'calibre:user_notes')
            meta.set('content', str(metadata['notes']))

        # Year: apart meta element (niet dc:date, want die wordt door publication_date gebruikt)
        if 'year' in metadata and metadata['year']:
            meta = ET.SubElement(meta_elem, 'meta')
            meta.set('name', 'calibre:year')
            meta.set('content', str(metadata['year']))

        # Author sort: opf:file-as attribuut op dc:creator element
        # Als er geen dc:creator is, sla op als calibre:author_sort meta element
        if 'author_sort' in metadata and metadata['author_sort']:
            creator_elem = meta_elem.find(f'{{{DC_NS}}}creator')
            if creator_elem is not None:
                # Standaard Calibre methode: attribuut op dc:creator
                creator_elem.set(f'{{{OPF_NS}}}file-as', metadata['author_sort'])
            else:
                # Fallback: als meta element (voor bestanden zonder author in OPF)
                meta_as = ET.SubElement(meta_elem, 'meta')
                meta_as.set('name', 'calibre:author_sort')
                meta_as.set('content', str(metadata['author_sort']))

        # Publication date: als year al gezet is, overschrijf met volledige datum
        if 'publication_date' in metadata and metadata['publication_date']:
            date_elem = meta_elem.find(f'{{{DC_NS}}}date')
            if date_elem is not None:
                date_elem.text = metadata['publication_date']
            else:
                date_elem = ET.SubElement(meta_elem, f'{{{DC_NS}}}date')
                date_elem.text = metadata['publication_date']

        # Pages: meta element voor aantal pagina's
        if 'pages' in metadata and metadata['pages']:
            meta = ET.SubElement(meta_elem, 'meta')
            meta.set('name', 'rendition:page-count')
            meta.set('content', str(metadata['pages']))
            # Ook als calibre:pages voor compatibiliteit
            meta2 = ET.SubElement(meta_elem, 'meta')
            meta2.set('name', 'calibre:pages')
            meta2.set('content', str(metadata['pages']))

        # Translator: dc:contributor met opf:role="trl"
        if 'translator' in metadata and metadata['translator']:
            trans_elem = ET.SubElement(meta_elem, f'{{{DC_NS}}}contributor')
            trans_elem.text = metadata['translator']
            trans_elem.set(f'{{{OPF_NS}}}role', 'trl')

        # Illustrator: dc:contributor met opf:role="ill"
        if 'illustrator' in metadata and metadata['illustrator']:
            ill_elem = ET.SubElement(meta_elem, f'{{{DC_NS}}}contributor')
            ill_elem.text = metadata['illustrator']
            ill_elem.set(f'{{{OPF_NS}}}role', 'ill')

        # Schrijf naar bestand
        tree = ET.ElementTree(root)
        with open(opf_path, 'wb') as f:
            tree.write(f, encoding='UTF-8', xml_declaration=True)

        return True

    except Exception as e:
        print(f"Error writing OPF metadata to {opf_path}: {e}")
        return False


def modify_opf_tags(ebook_path: Path, tags_to_remove: set, tags_to_add: set) -> bool:
    """Wijzig tags in een OPF sidecar file.

    Ondersteunt meerdere tags tegelijk toevoegen of verwijderen.

    Args:
        ebook_path: Path naar het ebook bestand
        tags_to_remove: Set van tags om te verwijderen (lowercase)
        tags_to_add: Set van tags om toe te voegen (lowercase, lege set = niets toevoegen)

    Returns:
        True als wijzigingen gemaakt zijn, False anders
    """
    # Lees huidige tags
    current_tags = read_opf_tags(ebook_path)

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

    # Schrijf nieuwe tags
    return write_opf_tags(ebook_path, new_tags)
