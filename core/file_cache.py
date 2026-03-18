"""
Persistente file metadata cache op SQLite basis.

Deze module biedt een cache voor bestandsmetadata die overleeft tussen app-sessies.
Elk bestand = één entry met flat metadata (geen multi-book ondersteuning).

De bestanden blijven de source of truth - de cache is alleen voor snel lezen.
Bij wijzigingen (Edit popup) wordt eerst het bestand geüpdatet, daarna de cache.

Design beslissingen:
- SQLite i.p.v. JSON: betere performance bij grote aantallen bestanden, ACID guarantees
- Flat metadata per bestand: simpel en betrouwbaar
- mtime check: cache entry wordt automatisch invalid bij bestandswijziging
- Graceful degradation: bij cache fouten valt de app terug op directe file extractie
"""

import json
import sqlite3
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, List, Dict, Any
import threading


@dataclass
class CachedFileMetadata:
    """Cache entry voor een bestand.

    Bevat alle metadata velden die in de Edit popup gemuteerd kunnen worden.
    Eén entry per bestand - geen multi-book ondersteuning.
    """
    file_path: str = ""
    mtime: float = 0.0
    cover_url: str = ""
    booktitle: str = ""
    authors: List[str] = field(default_factory=list)
    author_sort: str = ""
    isbn: str = ""
    rating: Optional[float] = None
    publisher: str = ""
    year: str = ""
    publication_date: str = ""
    language: str = ""
    pages: str = ""
    tags: List[str] = field(default_factory=list)
    series: str = ""
    series_index: Optional[float] = None
    translator: str = ""
    illustrator: str = ""
    description: str = ""
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CachedFileMetadata':
        """Create instance from dictionary."""
        # Filter alleen bekende velden om KeyError te voorkomen
        known_fields = {
            'file_path', 'mtime', 'cover_url', 'booktitle', 'authors',
            'author_sort', 'isbn', 'rating', 'publisher', 'year',
            'publication_date', 'language', 'pages', 'tags', 'series',
            'series_index', 'translator', 'illustrator', 'description', 'notes'
        }
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)

    @classmethod
    def from_book_metadata(cls, book_meta, file_path: str = "", mtime: float = 0.0) -> 'CachedFileMetadata':
        """Create instance from BookMetadata object.

        Args:
            book_meta: BookMetadata instance van metadata_extractor
            file_path: Pad naar het bestand
            mtime: Modification time van het bestand
        """
        return cls(
            file_path=file_path,
            mtime=mtime,
            cover_url=book_meta.cover_url or "",
            booktitle=book_meta.booktitle or "",
            authors=list(book_meta.authors) if book_meta.authors else [],
            author_sort=book_meta.author_sort or "",
            isbn=book_meta.isbn or "",
            rating=book_meta.rating,
            publisher=book_meta.publisher or "",
            year=book_meta.year or "",
            publication_date=book_meta.publication_date or "",
            language=book_meta.language or "",
            pages=book_meta.pages or "",
            tags=list(book_meta.tags) if book_meta.tags else [],
            series=book_meta.series or "",
            series_index=book_meta.series_index,
            translator=book_meta.translator or "",
            illustrator=book_meta.illustrator or "",
            description=book_meta.description or "",
            notes=book_meta.notes or "",
        )


class FileCache:
    """Persistente cache voor bestandsmetadata.

    Slaat metadata op in SQLite database voor snelle toegang.
    Thread-safe via connection per thread.

    Gebruik:
        cache = FileCache(cache_dir)

        # Haal cached data op of extract uit bestand
        file_meta = cache.get_or_extract(path, extractor)

        # Na bestandswijziging
        cache.set(path, metadata)

        # Bij move
        cache.update_path(old_path, new_path)

        # Bij delete
        cache.invalidate(path)
    """

    # Database schema versie - increment bij schema wijzigingen
    # Versie 2: vereenvoudigd schema zonder multi-book support
    SCHEMA_VERSION = 2

    def __init__(self, cache_dir: Path):
        """Initialize cache.

        Args:
            cache_dir: Directory voor cache bestanden (bijv. ~/.libiry/cache)
        """
        self.cache_dir = Path(cache_dir)
        self.db_path = self.cache_dir / "files.db"

        # Thread-local storage voor connections
        # SQLite connections zijn niet thread-safe
        self._local = threading.local()

        # Zorg dat cache directory bestaat
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"FileCache: Could not create cache dir: {e}")

        # Initialize database
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Get SQLite connection for current thread.

        Elke thread krijgt eigen connection voor thread-safety.
        """
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            try:
                # WAL mode voor betere concurrent access
                conn = sqlite3.connect(str(self.db_path), timeout=10.0)
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")
                conn.row_factory = sqlite3.Row
                self._local.connection = conn
            except Exception as e:
                print(f"FileCache: Database connection error: {e}")
                return None
        return self._local.connection

    def _init_db(self):
        """Initialize database schema.

        Maakt tabellen aan als ze niet bestaan.
        Migreert schema bij versie-upgrade.
        """
        conn = self._get_connection()
        if conn is None:
            return

        try:
            cursor = conn.cursor()

            # Schema versie tabel
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schema_info (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)

            # Check huidige versie
            cursor.execute("SELECT value FROM schema_info WHERE key = 'version'")
            row = cursor.fetchone()
            current_version = int(row['value']) if row else 0

            if current_version < self.SCHEMA_VERSION:
                # Nieuwe of oude database - maak (opnieuw) aan
                cursor.execute("DROP TABLE IF EXISTS file_metadata")

                # Hoofd metadata tabel - flat structuur, één entry per bestand
                cursor.execute("""
                    CREATE TABLE file_metadata (
                        file_path TEXT PRIMARY KEY,
                        mtime REAL NOT NULL,
                        metadata_json TEXT NOT NULL
                    )
                """)

                # Index voor snelle mtime checks
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_mtime
                    ON file_metadata(mtime)
                """)

                # Update schema versie
                cursor.execute("""
                    INSERT OR REPLACE INTO schema_info (key, value)
                    VALUES ('version', ?)
                """, (str(self.SCHEMA_VERSION),))

                conn.commit()

        except Exception as e:
            print(f"FileCache: Database init error: {e}")

    def get(self, path: Path) -> Optional[CachedFileMetadata]:
        """Haal cached metadata op voor een bestand.

        Returns:
            CachedFileMetadata als cache geldig is, anders None
        """
        conn = self._get_connection()
        if conn is None:
            return None

        try:
            file_path = str(path.resolve())

            # Haal cache entry op
            cursor = conn.cursor()
            cursor.execute(
                "SELECT mtime, metadata_json FROM file_metadata WHERE file_path = ?",
                (file_path,)
            )
            row = cursor.fetchone()

            if row is None:
                return None

            # Check of bestand nog bestaat en niet gewijzigd is
            # mtime check zorgt dat cache automatisch invalid wordt bij wijziging
            try:
                current_mtime = path.stat().st_mtime
                if abs(row['mtime'] - current_mtime) > 0.001:  # Float vergelijking tolerantie
                    # Bestand gewijzigd, cache is stale
                    return None
            except FileNotFoundError:
                # Bestand verwijderd
                self.invalidate(path)
                return None
            except Exception:
                # Bij stat errors, gebruik cache voorzichtig
                pass

            # Parse JSON metadata
            try:
                data = json.loads(row['metadata_json'])
                data['file_path'] = file_path
                data['mtime'] = row['mtime']
                return CachedFileMetadata.from_dict(data)
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                print(f"FileCache: JSON parse error for {path}: {e}")
                # Corrupte cache entry, verwijder
                self.invalidate(path)
                return None

        except Exception as e:
            print(f"FileCache: Get error for {path}: {e}")
            return None

    def set(self, path: Path, metadata: CachedFileMetadata) -> bool:
        """Sla metadata op in cache.

        Args:
            path: Pad naar bestand
            metadata: CachedFileMetadata object

        Returns:
            True bij succes, False bij fout
        """
        conn = self._get_connection()
        if conn is None:
            return False

        try:
            file_path = str(path.resolve())

            # Haal huidige mtime op
            try:
                mtime = path.stat().st_mtime
            except Exception:
                mtime = 0.0

            # Serialize naar JSON (exclusief file_path en mtime)
            data = metadata.to_dict()
            del data['file_path']
            del data['mtime']
            metadata_json = json.dumps(data, ensure_ascii=False)

            # Insert of update
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO file_metadata
                (file_path, mtime, metadata_json)
                VALUES (?, ?, ?)
            """, (file_path, mtime, metadata_json))

            conn.commit()
            return True

        except Exception as e:
            print(f"FileCache: Set error for {path}: {e}")
            return False

    def get_or_extract(self, path: Path, extractor) -> Optional[CachedFileMetadata]:
        """Haal metadata uit cache of extract uit bestand.

        Dit is de primaire interface voor grid opbouw.
        Checked eerst cache, bij miss wordt metadata geëxtraheerd en gecached.

        Args:
            path: Pad naar bestand
            extractor: MetadataExtractor instance

        Returns:
            CachedFileMetadata of None bij fout
        """
        # Probeer eerst cache
        cached = self.get(path)
        if cached is not None:
            return cached

        # Cache miss - extract metadata
        try:
            # Simpele extractie - geen multi-book logica meer
            meta = extractor.extract(path)
            if meta:
                # Haal mtime op
                try:
                    mtime = path.stat().st_mtime
                except Exception:
                    mtime = 0.0

                file_path = str(path.resolve())
                cached_meta = CachedFileMetadata.from_book_metadata(meta, file_path, mtime)

                # Sla op in cache
                self.set(path, cached_meta)
                return cached_meta

        except Exception as e:
            print(f"FileCache: Extract error for {path}: {e}")

        return None

    def invalidate(self, path: Path) -> bool:
        """Verwijder cache entry voor een bestand.

        Gebruik bij delete operaties.

        Returns:
            True bij succes, False bij fout
        """
        conn = self._get_connection()
        if conn is None:
            return False

        try:
            file_path = str(path.resolve())
            cursor = conn.cursor()
            cursor.execute("DELETE FROM file_metadata WHERE file_path = ?", (file_path,))
            conn.commit()
            return True
        except Exception as e:
            print(f"FileCache: Invalidate error for {path}: {e}")
            return False

    def update_path(self, old_path: Path, new_path: Path) -> bool:
        """Update cache entry na move operatie.

        Verplaatst cache entry naar nieuw pad en update mtime.

        Returns:
            True bij succes, False bij fout
        """
        conn = self._get_connection()
        if conn is None:
            return False

        try:
            old_file_path = str(old_path.resolve())
            new_file_path = str(new_path.resolve())

            # Haal nieuwe mtime op
            try:
                new_mtime = new_path.stat().st_mtime
            except Exception:
                new_mtime = 0.0

            cursor = conn.cursor()
            cursor.execute("""
                UPDATE file_metadata
                SET file_path = ?, mtime = ?
                WHERE file_path = ?
            """, (new_file_path, new_mtime, old_file_path))

            conn.commit()
            return cursor.rowcount > 0

        except Exception as e:
            print(f"FileCache: Update path error: {e}")
            return False

    def prefetch(self, paths: List[Path]) -> Dict[str, CachedFileMetadata]:
        """Batch load metadata voor meerdere bestanden.

        Optimaliseert database access door één query voor alle bestanden.
        Handig voor folder loading.

        Args:
            paths: Lijst met paden om te laden

        Returns:
            Dict van path string naar CachedFileMetadata
        """
        conn = self._get_connection()
        if conn is None:
            return {}

        result = {}

        try:
            # Resolve alle paden
            path_map = {str(p.resolve()): p for p in paths}
            file_paths = list(path_map.keys())

            if not file_paths:
                return {}

            # Batch query - SQLite IN clause
            placeholders = ','.join('?' * len(file_paths))
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT file_path, mtime, metadata_json
                FROM file_metadata
                WHERE file_path IN ({placeholders})
            """, file_paths)

            rows = cursor.fetchall()

            for row in rows:
                file_path = row['file_path']
                path = path_map.get(file_path)

                if path is None:
                    continue

                # Check mtime validity
                try:
                    current_mtime = path.stat().st_mtime
                    if abs(row['mtime'] - current_mtime) > 0.001:
                        continue  # Stale cache
                except Exception:
                    continue

                # Parse JSON
                try:
                    data = json.loads(row['metadata_json'])
                    data['file_path'] = file_path
                    data['mtime'] = row['mtime']
                    result[file_path] = CachedFileMetadata.from_dict(data)
                except Exception:
                    pass

        except Exception as e:
            print(f"FileCache: Prefetch error: {e}")

        return result

    def clear(self) -> bool:
        """Leeg de volledige cache.

        Returns:
            True bij succes, False bij fout
        """
        conn = self._get_connection()
        if conn is None:
            return False

        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM file_metadata")
            conn.commit()
            return True
        except Exception as e:
            print(f"FileCache: Clear error: {e}")
            return False

    def close(self):
        """Sluit database connection voor huidige thread."""
        if hasattr(self._local, 'connection') and self._local.connection:
            try:
                self._local.connection.close()
            except Exception:
                pass
            self._local.connection = None
