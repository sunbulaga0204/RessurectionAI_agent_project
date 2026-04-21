"""
OpenITI Client — handles fetching and parsing mARkdown texts from OpenITI raw URLs.
Transforms the structured repository files into clean documents for the ingestion pipeline.
"""

import re
import urllib.request
import urllib.error
import ssl


# ── Known book title overrides ────────────────────────────────────────────
# Keyed by lowercase fragment that may appear in the OpenITI filename or Title header.
# Add entries here as you ingest more works.
KNOWN_TITLE_MAP = {
    "tahafut": "Tahāfut al-falāsifa (The Incoherence of the Philosophers)",
    "munqidh": "Al-Munqidh min al-dalāl (Deliverance from Error)",
    "ihya": "Iḥyāʾ ʿulūm al-dīn (Revival of the Religious Sciences)",
    "maqasid": "Maqāṣid al-falāsifa (Aims of the Philosophers)",
    "iqtisad": "Al-Iqtiṣād fī l-iʿtiqād (The Middle Path in Theology)",
    "mishkat": "Mishkāt al-anwār (The Niche of Lights)",
    "faysal": "Fayṣal al-tafriqa (The Decisive Criterion)",
    "maarij": "Maʿārij al-quds (Ascents of the Spirit)",
    "kimiya": "Kīmiyāʾ al-saʿāda (The Alchemy of Happiness)",
    "bidaya": "Bidāyat al-hidāya (Beginning of Guidance)",
    "ayyuha": "Ayyuhā al-walad (O Young Man)",
}


def _resolve_book_title(raw_title: str, filename: str) -> str:
    """
    Resolve a human-readable book title from raw OpenITI metadata.

    Priority:
    1. Match against KNOWN_TITLE_MAP (by lowercase fragment).
    2. Use the raw_title from the header if it looks valid.
    3. Derive a readable name from the filename.
    """
    combined = (raw_title + " " + filename).lower()
    for fragment, canonical in KNOWN_TITLE_MAP.items():
        if fragment in combined:
            return canonical

    # Use raw title if it was actually extracted and is non-trivial
    if raw_title and raw_title not in ("Unknown OpenITI Text", ""):
        return raw_title.strip()

    # Last resort: clean up the filename into something readable.
    # Example: "0505Ghazali.Tahafut.Al.Falasifa.Shamela1234" → "Tahafut Al Falasifa"
    name = filename.replace("-", " ").replace("_", " ")
    # Drop leading YYYYAUTHOR prefix (e.g. "0505Ghazali.")
    name = re.sub(r"^\d{4}[A-Za-z]+\.", "", name)
    # Split on dots; drop known library-tag trailing segments
    parts = [
        p for p in name.split(".")
        if p.strip() and not re.match(r"^(Shamela|Voll|Shia|JK)\d*$", p, re.I)
    ]
    readable = " — ".join(p.strip() for p in parts if p.strip())
    return readable or filename


def fetch_openiti_text(url: str) -> str:
    """Download the raw text from an OpenITI GitHub URL."""
    try:
        if "github.com" in url and "blob" in url:
            url = url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")

        req = urllib.request.Request(url, headers={"User-Agent": "ResurrectionAgent/1.0"})
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        with urllib.request.urlopen(req, context=ctx) as response:
            return response.read().decode("utf-8")
    except urllib.error.URLError as e:
        raise ConnectionError(f"Failed to fetch OpenITI text from {url}. Error: {e}")


def parse_openiti(raw_text: str, source_url: str) -> list[dict]:
    """
    Parse OpenITI mARkdown format.

    - Scans multiple possible META header fields for the book title.
    - Tracks running page numbers (PageVxxPyyy) and annotates each line.
    - Cleans structural mARkdown tags from body text.

    Returns a list containing a single Document dict (chunking happens later).
    """
    if not raw_text:
        return []

    filename = source_url.split("/")[-1]
    lines = raw_text.split("\n")

    raw_title = ""
    metadata = {
        "book_name": "",      # resolved at the end
        "chapter": "",
        "section": "",
        "volume": "",
        "page_number": "",
        "source_file": filename,
    }

    text_lines = []
    in_metadata_block = False
    current_page = ""
    current_vol = ""

    for line in lines:
        stripped = line.strip()

        # ── OpenITI header start ─────────────────────────────────────
        if stripped.startswith("######OpenITI#"):
            in_metadata_block = True
            continue

        # ── META tags — extract known fields ─────────────────────────
        if stripped.startswith("#META#"):
            meta_body = stripped[len("#META#"):].strip()

            # Several field variants used across different OpenITI repos
            for title_key in ("BookTitle", "Title", "TitleAr", "الكتاب", "Kitaab"):
                sep = None
                if f"{title_key}##" in meta_body:
                    sep = "##"
                elif f"{title_key}:" in meta_body:
                    sep = ":"
                if sep:
                    candidate = meta_body.split(sep, 1)[1].strip()
                    if candidate and len(candidate) > 2:
                        raw_title = candidate
                    break

            if any(marker in stripped for marker in ["HeaderEnds", "Header Ends", "Header#End", "#META#End"]):
                in_metadata_block = False
            continue

        if in_metadata_block:
            continue

        # Skip purely structural/empty lines
        if not stripped or stripped.startswith("### |"):
            continue

        # ── Extract inline page/volume tags BEFORE stripping ─────────
        page_match = re.search(r"PageV(\d+)P(\d+)", stripped)
        if page_match:
            current_vol = page_match.group(1).lstrip("0") or "1"
            current_page = page_match.group(2).lstrip("0") or "1"

        # ── Clean inline mARkdown tags ────────────────────────────────
        clean_line = re.sub(r"PageV\d+P\d+", "", stripped)
        clean_line = re.sub(r"ms\d+", "", clean_line)     # manuscript tags
        clean_line = re.sub(r"~~", "", clean_line)
        clean_line = re.sub(r"#+", "", clean_line)
        clean_line = clean_line.strip()

        if clean_line:
            # Annotate each line with the running page number so the chunker
            # can surface it in metadata for accurate citation.
            page_tag = f"[p.{current_page}]" if current_page else ""
            text_lines.append(f"{clean_line} {page_tag}".strip())

    clean_text = "\n".join(text_lines)

    if not clean_text:
        return []

    # Resolve the best available book title
    metadata["book_name"] = _resolve_book_title(raw_title, filename)
    print(f"  ✓ OpenITI book identified as: '{metadata['book_name']}'")

    return [{"text": clean_text, "metadata": metadata}]
