"""SQLite-backed thumbnail cache for fast grid loading."""

from pathlib import Path
import sqlite3
import hashlib
from PIL import Image, ImageDraw, ImageFont
from typing import Optional
import os


class CoverCache:
    """
    SQLite-backed thumbnail cache for fast grid loading.

    Stores thumbnails on disk and tracks file modification times
    to invalidate cache when source files change.
    """

    THUMB_SIZE = (200, 300)
    BLANK_COLOR = (240, 240, 240)
    TEXT_COLOR = (100, 100, 100)

    def __init__(self, cache_dir: Path):
        """
        Initialize cover cache.

        Args:
            cache_dir: Directory to store cache database and thumbnails
        """
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.thumbs_dir = cache_dir / "thumbs"
        self.thumbs_dir.mkdir(exist_ok=True)
        self.db_path = cache_dir / "covers.db"
        self._init_db()

    def _init_db(self):
        """Initialize SQLite database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS covers (
                    file_path TEXT PRIMARY KEY,
                    mtime REAL,
                    thumb_path TEXT,
                    has_cover INTEGER
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_mtime ON covers(mtime)
            """)

    def get_cover(self, filepath: Path, extractor) -> Path:
        """
        Get cached thumbnail path, extracting and caching if needed.

        Args:
            filepath: Path to the ebook file
            extractor: CoverExtractor instance

        Returns:
            Path to the thumbnail image
        """
        try:
            mtime = filepath.stat().st_mtime
        except OSError:
            return self._get_blank_cover_path(filepath.stem)

        # Check cache
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT mtime, thumb_path, has_cover FROM covers WHERE file_path = ?",
                (str(filepath),)
            ).fetchone()

            if row and row[0] == mtime:
                thumb_path = Path(row[1])
                if thumb_path.exists():
                    return thumb_path

        # Cache miss or stale - extract cover
        cover = extractor.extract(filepath)

        thumb_path = self._save_thumbnail(filepath, cover)
        has_cover = 1 if cover else 0

        # Update cache
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO covers VALUES (?, ?, ?, ?)",
                (str(filepath), mtime, str(thumb_path), has_cover)
            )

        return thumb_path

    def _save_thumbnail(self, filepath: Path, cover: Optional[Image.Image]) -> Path:
        """
        Save thumbnail to disk.

        Args:
            filepath: Original file path (used for hash)
            cover: PIL Image or None for blank cover

        Returns:
            Path to saved thumbnail
        """
        path_hash = hashlib.md5(str(filepath).encode()).hexdigest()
        thumb_path = self.thumbs_dir / f"{path_hash}.png"

        if cover:
            # Save cover directly without gray background - Kivy will stretch it
            cover = cover.copy()
            # Convert to RGB if needed (remove alpha to avoid issues)
            if cover.mode == 'RGBA':
                bg = Image.new('RGB', cover.size, (255, 255, 255))
                bg.paste(cover, mask=cover.split()[3])
                cover = bg
            elif cover.mode != 'RGB':
                cover = cover.convert('RGB')
            # Resize to thumbnail size
            cover = cover.resize(self.THUMB_SIZE, Image.Resampling.LANCZOS)
            cover.save(thumb_path, 'PNG')
        else:
            # No cover - don't create blank, let main.py handle fallback to book.png
            self._create_blank_cover(filepath.stem, thumb_path)

        return thumb_path

    def _create_blank_cover(self, title: str, save_path: Path):
        """Create a blank cover with the title text."""
        img = Image.new('RGB', self.THUMB_SIZE, self.BLANK_COLOR)
        draw = ImageDraw.Draw(img)

        try:
            for font_name in ['segoeui.ttf', 'arial.ttf', 'calibri.ttf', 'DejaVuSans.ttf', 'Roboto-Regular.ttf']:
                try:
                    font = ImageFont.truetype(font_name, 14)
                    break
                except OSError:
                    continue
            else:
                font = ImageFont.load_default()
        except Exception:
            font = ImageFont.load_default()

        words = title.split()
        lines = []
        current_line = []
        max_width = self.THUMB_SIZE[0] - 20

        for word in words:
            current_line.append(word)
            test_line = ' '.join(current_line)
            bbox = draw.textbbox((0, 0), test_line, font=font)
            if bbox[2] > max_width:
                if len(current_line) > 1:
                    current_line.pop()
                    lines.append(' '.join(current_line))
                    current_line = [word]
                else:
                    lines.append(word[:20] + '...')
                    current_line = []

        if current_line:
            lines.append(' '.join(current_line))

        if len(lines) > 8:
            lines = lines[:7] + ['...']

        total_height = len(lines) * 18
        y = (self.THUMB_SIZE[1] - total_height) // 2

        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            text_width = bbox[2] - bbox[0]
            x = (self.THUMB_SIZE[0] - text_width) // 2
            draw.text((x, y), line, fill=self.TEXT_COLOR, font=font)
            y += 18

        draw.rectangle(
            [2, 2, self.THUMB_SIZE[0] - 3, self.THUMB_SIZE[1] - 3],
            outline=(200, 200, 200),
            width=1
        )

        img.save(save_path, 'PNG')

    def _get_blank_cover_path(self, title: str) -> Path:
        """Get path to a blank cover, creating if needed."""
        path_hash = hashlib.md5(f"blank_{title}".encode()).hexdigest()
        thumb_path = self.thumbs_dir / f"{path_hash}.png"
        if not thumb_path.exists():
            self._create_blank_cover(title, thumb_path)
        return thumb_path

    def clear_cache(self):
        """Clear all cached thumbnails."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM covers")

        for thumb in self.thumbs_dir.glob("*.png"):
            try:
                thumb.unlink()
            except OSError:
                pass

    def has_real_cover(self, filepath: Path) -> bool:
        """Check if a file has a real cover (not a placeholder)."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT has_cover FROM covers WHERE file_path = ?",
                (str(filepath),)
            ).fetchone()
            return bool(row and row[0])

    def get_cache_stats(self) -> dict:
        """Get cache statistics."""
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM covers").fetchone()[0]
            with_cover = conn.execute(
                "SELECT COUNT(*) FROM covers WHERE has_cover = 1"
            ).fetchone()[0]

        thumb_count = len(list(self.thumbs_dir.glob("*.png")))
        cache_size = sum(f.stat().st_size for f in self.thumbs_dir.glob("*.png"))

        return {
            'total_entries': total,
            'with_cover': with_cover,
            'without_cover': total - with_cover,
            'thumb_files': thumb_count,
            'cache_size_mb': cache_size / (1024 * 1024)
        }

    def get_cache_path(self, filepath: Path, suffix: str = "") -> Path:
        """
        Get the cache path for a file with optional suffix.

        Args:
            filepath: Original file path
            suffix: Optional suffix for multi-book files (e.g., "_book0")

        Returns:
            Path where thumbnail would be stored
        """
        path_hash = hashlib.md5(f"{filepath}{suffix}".encode()).hexdigest()
        return self.thumbs_dir / f"{path_hash}.png"
