"""Persistent file metadata cache on SQLite basis
This module offers a cache for file metadata that survives between app sessions
The files remain the source of truth - the cache is only used for fast reading
For edits (Edit popup), first the files are updated, then the cache
Design decisions:
- SQLite instead of JSON: better performance for big file numbers, ACID guarantees
- Flat metadata per file: simple and reliable
- mtime check: cache entry automatically invalided at file change
- Graceful degradation: in case ofcache errors, the app falls back on direct file extraction"""

import json
import sqlite3
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, List, Dict, Any
import threading

@dataclass
class CachedFileMetadata:
    """Cache entry for a file
    Contains all metadata fields that can be edited in the Edit popup"""
    file_path: str = ""
    mtime: float = 0.0
    cover: str = ""
    booktitle: str = ""
    authors: List[str] = field(default_factory=list)
    author_sort: str = ""
    isbn: str = ""
    rating: Optional[float] = None
    publisher: str = ""
    publication_date: str = ""
    pages: str = ""
    language: str = ""
    tags: List[str] = field(default_factory=list)
    series: str = ""
    series_index: Optional[float] = None
    translator: str = ""
    illustrator: str = ""
    description: str = ""
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CachedFileMetadata':
        """Create instance from dictionary"""
        # Filter only known fields to prevent KeyError
        known_fields = {
            'file_path', 'mtime', 'cover', 'booktitle', 'authors',
            'author_sort', 'isbn', 'rating', 'publisher', 'publication_date', 'language', 'pages', 'tags', 'series',
            'series_index', 'translator', 'illustrator', 'description', 'notes'
        }
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)

    @classmethod
    def from_book_metadata(cls, book_meta, file_path: str = "", mtime: float = 0.0) -> 'CachedFileMetadata':
        """Create instance from BookMetadata object
        Args:
            book_meta: BookMetadata instance of metadata_extractor
            file_path: Path to the file
            mtime: Modification time of the file"""
        return cls(
            file_path=file_path,
            mtime=mtime,
            cover=book_meta.cover or "",
            booktitle=book_meta.booktitle or "",
            authors=list(book_meta.authors) if book_meta.authors else [],
            author_sort=book_meta.author_sort or "",
            isbn=book_meta.isbn or "",
            rating=book_meta.rating,
            publisher=book_meta.publisher or "",
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
    """Persistent cache for file metadata
    Saves metadata in SQLite database for fast access
    Thread-safe via connection per thread
    Use:
        cache = FileCache(cache_dir)
        # Retrieves cached data or file data
        file_meta = cache.get_or_extract(path, extractor)
        # After file change
        cache.set(path, metadata)
        # At move
        cache.update_path(old_path, new_path)
        # At delete
        cache.invalidate(path)"""

    # Database schema version - increment at schema changes
    SCHEMA_VERSION = 2

    def __init__(self, cache_dir: Path):
        """Initialize cache
        Args: cache_dir: Directory for cache files (f.e. ~/.libiry/cache)"""
        self.cache_dir = Path(cache_dir)
        self.db_path = self.cache_dir / "files.db"

        # Thread-local storage for connections
        # SQLite connections are not thread-safe
        self._local = threading.local()

        # Make sure cache directory exists
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"FileCache: Could not create cache dir: {e}")

        # Initialize database
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Get SQLite connection for current thread
        Every thread gets its own connection for thread-safety"""
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            try:
                # WAL mode for better concurrent access
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
        """Initialize database schema
        Makes tables if they don't exist
        Migrates schema in case of version upgrade"""
        conn = self._get_connection()
        if conn is None:
            return

        try:
            cursor = conn.cursor()

            # Schema version table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schema_info (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)

            # Check current version
            cursor.execute("SELECT value FROM schema_info WHERE key = 'version'")
            row = cursor.fetchone()
            current_version = int(row['value']) if row else 0

            if current_version < self.SCHEMA_VERSION:
                # New or old database - create (again)
                cursor.execute("DROP TABLE IF EXISTS file_metadata")

                # Head metadata table - flat structure, one entry per file
                cursor.execute("""
                    CREATE TABLE file_metadata (
                        file_path TEXT PRIMARY KEY,
                        mtime REAL NOT NULL,
                        metadata_json TEXT NOT NULL
                    )
                """)

                # Index for fast mtime checks
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_mtime
                    ON file_metadata(mtime)
                """)

                # Update schema version
                cursor.execute("""
                    INSERT OR REPLACE INTO schema_info (key, value)
                    VALUES ('version', ?)
                """, (str(self.SCHEMA_VERSION),))

                conn.commit()

        except Exception as e:
            print(f"FileCache: Database init error: {e}")

    def get(self, path: Path) -> Optional[CachedFileMetadata]:
        """Get cached metadata for a file
        Returns CachedFileMetadata if cache is valid, None otherwise"""
        conn = self._get_connection()
        if conn is None:
            return None

        try:
            file_path = str(path.resolve())

            # Get cache entry
            cursor = conn.cursor()
            cursor.execute(
                "SELECT mtime, metadata_json FROM file_metadata WHERE file_path = ?",
                (file_path,)
            )
            row = cursor.fetchone()

            if row is None:
                return None

            # Check if file still exists and has not changed
            # mtime check makes sure that cache is automatisch invalidated at change
            try:
                current_mtime = path.stat().st_mtime
                if abs(row['mtime'] - current_mtime) > 0.001:  # Float compare tolerance
                    # File changed, cache is stale
                    return None
            except FileNotFoundError:
                # File deleted
                self.invalidate(path)
                return None
            except Exception:
                # With stat errors, use cache carefully
                pass

            # Parse JSON metadata
            try:
                data = json.loads(row['metadata_json'])
                data['file_path'] = file_path
                data['mtime'] = row['mtime']
                return CachedFileMetadata.from_dict(data)
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                print(f"FileCache: JSON parse error for {path}: {e}")
                # Corrupt cache entry, delete
                self.invalidate(path)
                return None

        except Exception as e:
            print(f"FileCache: Get error for {path}: {e}")
            return None

    def set(self, path: Path, metadata: CachedFileMetadata) -> bool:
        """Save metadata in cache
        Args:
            path: Path to file
            metadata: CachedFileMetadata object
        Returns True for succes, False for failure"""
        conn = self._get_connection()
        if conn is None:
            return False

        try:
            file_path = str(path.resolve())

            # Get current mtime
            try:
                mtime = path.stat().st_mtime
            except Exception:
                mtime = 0.0

            # Serialize to JSON (exclusive file_path and mtime)
            data = metadata.to_dict()
            del data['file_path']
            del data['mtime']
            metadata_json = json.dumps(data, ensure_ascii=False)

            # Insert or update
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
        """Get metadata from cache or extract from file
        This is the primairy interface for building the grid
        Checks cache first, in case of a miss the metadata is extracted and cached
        Args:
            path: Path to file
            extractor: MetadataExtractor instance
        Returns CachedFileMetadata or None"""
        # Try cache first
        cached = self.get(path)
        if cached is not None:
            return cached

        # Cache absent - extract metadata
        try:
            meta = extractor.extract(path)
            if meta:
                # Get mtime
                try:
                    mtime = path.stat().st_mtime
                except Exception:
                    mtime = 0.0

                file_path = str(path.resolve())
                cached_meta = CachedFileMetadata.from_book_metadata(meta, file_path, mtime)

                # Save in cache
                self.set(path, cached_meta)
                return cached_meta

        except Exception as e:
            print(f"FileCache: Extract error for {path}: {e}")

        return None

    def invalidate(self, path: Path) -> bool:
        """Delete cache entry for a file
        Use for delete operations
        Returns True or False"""
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
        """Update cache entry after move operation"""
        conn = self._get_connection()
        if conn is None:
            return False

        try:
            old_file_path = str(old_path.resolve())
            new_file_path = str(new_path.resolve())

            # Get new mtime
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

    def clear(self) -> bool:
        """Clear the cache completely
        Returns True for succes, False for failure"""
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
        """Close database connection for current thread"""
        if hasattr(self._local, 'connection') and self._local.connection:
            try:
                self._local.connection.close()
            except Exception:
                pass
            self._local.connection = None