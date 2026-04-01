"""
TXT → JSON Converter — transforms plain .txt source files into structured JSON
with page-level metadata for RAG ingestion.

Usage:
    python txt_to_json.py --input sources/raw/ --output sources/
    python txt_to_json.py --input sources/raw/mybook.txt --output sources/ --book-name "My Book"

Supported page delimiters (configurable):
    ### PAGE N ###
    --- page N ---
    \\f (form feed character)
    [PAGE N]
"""

import argparse
import json
import os
import re
from pathlib import Path


# ── Default page delimiter patterns ──────────────────────
PAGE_PATTERNS = [
    re.compile(r'###\s*PAGE\s+(\d+)\s*###', re.IGNORECASE),
    re.compile(r'---\s*page\s+(\d+)\s*---', re.IGNORECASE),
    re.compile(r'\[PAGE\s+(\d+)\]', re.IGNORECASE),
]

# Chapter / section header patterns
CHAPTER_PATTERN = re.compile(
    r'^(?:CHAPTER|BOOK|PART|SECTION)\s+[IVXLCDM\d]+[\s—–\-:\.]+(.+)$',
    re.IGNORECASE | re.MULTILINE,
)

VOLUME_PATTERN = re.compile(
    r'^VOLUME\s+([IVXLCDM\d]+)',
    re.IGNORECASE | re.MULTILINE,
)


def _extract_book_name(text: str, filename: str) -> str:
    """Try to extract book name from the first few lines, else use filename."""
    lines = text.strip().split('\n')[:5]
    for line in lines:
        clean = line.strip()
        # Skip page markers and empty lines
        if not clean or re.match(r'###|---|\[PAGE', clean, re.IGNORECASE):
            continue
        # Skip "By Author" lines
        if clean.lower().startswith('by '):
            continue
        # The first substantive line is likely the title
        if len(clean) > 5 and not clean.startswith('#'):
            return clean
    return Path(filename).stem.replace('_', ' ').title()


def _split_by_pages(text: str) -> list[tuple[int, str]]:
    """
    Split text into (page_number, page_content) tuples.
    Tries each page pattern; falls back to form feeds; then treats as single page.
    """
    # Try regex-based page markers
    for pattern in PAGE_PATTERNS:
        matches = list(pattern.finditer(text))
        if matches:
            pages = []
            for i, match in enumerate(matches):
                page_num = int(match.group(1))
                start = match.end()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
                content = text[start:end].strip()
                if content:
                    pages.append((page_num, content))
            return pages

    # Try form feed characters
    if '\f' in text:
        parts = text.split('\f')
        pages = []
        for i, part in enumerate(parts, 1):
            content = part.strip()
            if content:
                pages.append((i, content))
        return pages

    # No page markers — treat entire text as page 1
    return [(1, text.strip())]


def _extract_chapter(text: str, current_chapter: str) -> str:
    """Extract chapter title from text block, or return current."""
    match = CHAPTER_PATTERN.search(text)
    if match:
        return match.group(1).strip()
    return current_chapter


def _extract_volume(text: str, current_volume: str) -> str:
    """Extract volume number from text block, or return current."""
    match = VOLUME_PATTERN.search(text)
    if match:
        return match.group(1).strip()
    return current_volume


def convert_file(filepath: str, book_name: str = None) -> list[dict]:
    """
    Convert a single .txt file to a list of structured page dicts.

    Args:
        filepath: Path to the .txt file
        book_name: Override book name (auto-detected if None)

    Returns:
        List of dicts with: text, page_number, volume, chapter, section,
        source_file, book_name
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        text = f.read()

    if not text.strip():
        return []

    filename = os.path.basename(filepath)
    if not book_name:
        book_name = _extract_book_name(text, filename)

    pages = _split_by_pages(text)
    entries = []
    current_chapter = ""
    current_volume = ""

    for page_num, page_text in pages:
        current_chapter = _extract_chapter(page_text, current_chapter)
        current_volume = _extract_volume(page_text, current_volume)

        entries.append({
            "text": page_text,
            "page_number": page_num,
            "volume": current_volume,
            "chapter": current_chapter,
            "section": "",
            "source_file": filename,
            "book_name": book_name,
        })

    return entries


def convert_directory(input_dir: str, output_dir: str, book_name: str = None):
    """
    Convert all .txt files in a directory to JSON files.

    Args:
        input_dir: Directory containing .txt files
        output_dir: Directory to write .json files
        book_name: Override book name (if None, auto-detected per file)
    """
    os.makedirs(output_dir, exist_ok=True)
    txt_files = sorted(Path(input_dir).glob('*.txt'))

    if not txt_files:
        print(f"  ✗ No .txt files found in {input_dir}")
        return

    for txt_path in txt_files:
        print(f"\n📄 Converting: {txt_path.name}")
        entries = convert_file(str(txt_path), book_name=book_name)

        if not entries:
            print(f"  ⚠ No content found, skipping")
            continue

        # Write JSON
        json_filename = txt_path.stem + '.json'
        json_path = os.path.join(output_dir, json_filename)

        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)

        print(f"  ✓ {len(entries)} pages → {json_filename}")


def main():
    parser = argparse.ArgumentParser(
        description="Convert .txt source files to structured JSON for RAG ingestion"
    )
    parser.add_argument(
        '--input', '-i',
        required=True,
        help='Input .txt file or directory of .txt files',
    )
    parser.add_argument(
        '--output', '-o',
        required=True,
        help='Output directory for .json files',
    )
    parser.add_argument(
        '--book-name', '-b',
        default=None,
        help='Override book name (auto-detected from file content if omitted)',
    )

    args = parser.parse_args()

    print("=" * 60)
    print("  📥  TXT → JSON Converter")
    print("=" * 60)

    if os.path.isfile(args.input):
        entries = convert_file(args.input, book_name=args.book_name)
        if entries:
            os.makedirs(args.output, exist_ok=True)
            json_filename = Path(args.input).stem + '.json'
            json_path = os.path.join(args.output, json_filename)
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(entries, f, indent=2, ensure_ascii=False)
            print(f"\n  ✓ {len(entries)} pages → {json_path}")
        else:
            print("\n  ✗ No content found in input file")
    elif os.path.isdir(args.input):
        convert_directory(args.input, args.output, book_name=args.book_name)
    else:
        print(f"\n  ✗ Input not found: {args.input}")
        return

    print("\n  Done! Run 'python ingest.py' next to embed into ChromaDB.")


if __name__ == '__main__':
    main()
