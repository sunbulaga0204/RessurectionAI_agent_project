"""
OpenITI Client — handles fetching and parsing mARkdown texts from OpenITI raw URLs.
Transforms the structured repository files into clean documents for the ingestion pipeline.
"""

import re
import urllib.request
import urllib.error

def fetch_openiti_text(url: str) -> str:
    """Download the raw text from an OpenITI GitHub URL."""
    try:
        # User might provide the github.com URL instead of raw.githubusercontent
        if "github.com" in url and "blob" in url:
            url = url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
            
        req = urllib.request.Request(url, headers={'User-Agent': 'ResurrectionAgent/1.0'})
        with urllib.request.urlopen(req) as response:
            return response.read().decode('utf-8')
    except urllib.error.URLError as e:
        raise ConnectionError(f"Failed to fetch OpenITI text from {url}. Error: {e}")

def parse_openiti(raw_text: str, source_url: str) -> list[dict]:
    """
    Parse OpenITI mARkdown format.
    Extracts metadata from the header and cleans the text body of structural tags.
    Returns a list containing a single Document dict (chunking happens later).
    """
    if not raw_text:
        return []

    lines = raw_text.split('\n')
    metadata = {
        "book_name": "Unknown OpenITI Text",
        "chapter": "",
        "section": "",
        "volume": "",
        "page_number": "",
        "source_file": source_url.split("/")[-1]
    }
    
    text_lines = []
    in_metadata_block = False
    
    for line in lines:
        stripped = line.strip()
        
        # Check for OpenITI header start
        if stripped.startswith("######OpenITI#"):
            in_metadata_block = True
            continue
            
        # Extract metadata from META tags
        if stripped.startswith("#META#"):
            # Try to grab the title if it's the standard header block
            if "Title:" in stripped:
                metadata["book_name"] = stripped.split("Title:", 1)[1].strip()
            # If META header ends, we enter the body text
            if "HeaderEnds" in stripped or "Header Ends" in stripped:
                in_metadata_block = False
            continue
            
        # Skip if we are still reading random metadata lines
        if in_metadata_block:
            continue
            
        # Skip purely structural/empty lines
        if not stripped or stripped.startswith("### |"):
            continue
            
        # Clean inline mARkdown tags
        # E.g., Page tags: PageV01P001, paragraph markers #, milestone markers ~~
        clean_line = re.sub(r'PageV\d+P\d+', '', stripped)
        clean_line = re.sub(r'ms\d+', '', clean_line) # Manuscript tags
        clean_line = re.sub(r'~~', '', clean_line)
        clean_line = re.sub(r'#+', '', clean_line)
        clean_line = clean_line.strip()
        
        if clean_line:
            text_lines.append(clean_line)

    clean_text = "\n".join(text_lines)
    
    if not clean_text:
        return []
        
    return [{
        "text": clean_text,
        "metadata": metadata
    }]
