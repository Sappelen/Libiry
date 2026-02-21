"""Library scanning and file discovery."""

from pathlib import Path
from typing import List, Tuple
from dataclasses import dataclass

# Supported ebook formats
SUPPORTED_FORMATS = {
    '.epub',
    '.mobi',
    '.azw',
    '.azw3',
    '.pdf',
    '.cbz',
    '.cbr',
    '.md',
}


@dataclass
class FolderItem:
    """Represents a folder in the library."""
    path: Path
    name: str
    item_count: int = 0


@dataclass
class BookItem:
    """Represents a book in the library."""
    path: Path
    name: str
    format: str


def scan_folder(folder_path: Path) -> Tuple[List[FolderItem], List[BookItem]]:
    """
    Scan a folder and return lists of subfolders and books.

    Args:
        folder_path: Path to scan

    Returns:
        Tuple of (folders, books) lists
    """
    folders = []
    books = []

    if not folder_path.exists() or not folder_path.is_dir():
        return folders, books

    try:
        items = sorted(folder_path.iterdir(), key=lambda x: x.name.lower())
    except PermissionError:
        return folders, books

    for item in items:
        # Skip hidden files/folders
        if item.name.startswith('.'):
            continue

        if item.is_dir():
            # Count items in subfolder
            try:
                item_count = sum(
                    1 for f in item.iterdir()
                    if f.is_dir() or f.suffix.lower() in SUPPORTED_FORMATS
                )
            except PermissionError:
                item_count = 0

            folders.append(FolderItem(
                path=item,
                name=item.name,
                item_count=item_count
            ))

        elif item.suffix.lower() in SUPPORTED_FORMATS:
            books.append(BookItem(
                path=item,
                name=item.stem,
                format=item.suffix.lower()
            ))

    return folders, books


def count_books_recursive(folder_path: Path) -> int:
    """
    Count all books in a folder recursively.

    Args:
        folder_path: Path to scan

    Returns:
        Total count of ebook files
    """
    count = 0
    try:
        for item in folder_path.rglob('*'):
            if item.is_file() and item.suffix.lower() in SUPPORTED_FORMATS:
                count += 1
    except PermissionError:
        pass
    return count


def search_books(folder_path: Path, query: str, recursive: bool = True) -> List[BookItem]:
    """
    Search for books matching a query.

    Args:
        folder_path: Root path to search
        query: Search query (matches against filename)
        recursive: Whether to search recursively

    Returns:
        List of matching BookItem objects
    """
    results = []
    query_lower = query.lower()

    if recursive:
        items = folder_path.rglob('*')
    else:
        items = folder_path.iterdir()

    for item in items:
        if item.is_file() and item.suffix.lower() in SUPPORTED_FORMATS:
            if query_lower in item.stem.lower():
                results.append(BookItem(
                    path=item,
                    name=item.stem,
                    format=item.suffix.lower()
                ))

    return sorted(results, key=lambda x: x.name.lower())
