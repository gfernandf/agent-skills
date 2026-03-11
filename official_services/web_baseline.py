"""
Web baseline service module.
Provides baseline implementations for web-related capabilities.
"""

import urllib.request
import urllib.error
import urllib.parse
import re
from html.parser import HTMLParser

# Limits
_FETCH_TIMEOUT_SECONDS = 10
_MAX_RESPONSE_BYTES = 2 * 1024 * 1024   # 2 MB
_ALLOWED_SCHEMES = {"http", "https"}


def _validate_url(url):
    """Return (ok, error_message). Rejects non-http/https schemes (SSRF guard)."""
    if not isinstance(url, str) or not url.strip():
        return False, "Invalid input: 'url' must be a non-empty string."
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        return False, "Invalid URL format."
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        return False, f"Scheme '{parsed.scheme}' is not allowed. Use http or https."
    if not parsed.netloc:
        return False, "URL must include a valid host."
    return True, None

class TextExtractor(HTMLParser):
    """Extract text content from HTML."""
    def __init__(self):
        super().__init__()
        self.text_parts = []
        self.in_script = False
        self.in_style = False
    
    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            if tag == 'script':
                self.in_script = True
            else:
                self.in_style = True
    
    def handle_endtag(self, tag):
        if tag == 'script':
            self.in_script = False
        elif tag == 'style':
            self.in_style = False
    
    def handle_data(self, data):
        if not self.in_script and not self.in_style:
            text = data.strip()
            if text:
                self.text_parts.append(text)
    
    def get_text(self):
        return ' '.join(self.text_parts)

def fetch_webpage(url):
    """
    Fetch the content of a webpage.

    Args:
        url (str): The URL to fetch (http/https only).

    Returns:
        dict: {"content": str, "status": int}
    """
    ok, err = _validate_url(url)
    if not ok:
        return {"content": err, "status": 400}

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "AgentSkills/1.0 (capability=web.fetch)"}
        )
        with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT_SECONDS) as response:
            raw = response.read(_MAX_RESPONSE_BYTES)
            content = raw.decode("utf-8", errors="ignore")
            return {"content": content, "status": response.status}
    except urllib.error.HTTPError as e:
        return {"content": f"HTTP error: {e.code} {e.reason}", "status": e.code}
    except urllib.error.URLError as e:
        return {"content": f"URL error: {e.reason}", "status": 502}
    except TimeoutError:
        return {"content": f"Request timed out after {_FETCH_TIMEOUT_SECONDS}s.", "status": 504}
    except Exception as e:
        return {"content": f"Unexpected error: {type(e).__name__}: {e}", "status": 500}

def extract_webpage(url):
    """
    Extract structured data from a webpage.
    
    Args:
        url (str): The URL to extract from.
    
    Returns:
        dict: {"title": str, "text": str}
    """
    try:
        # Fetch the webpage
        fetch_result = fetch_webpage(url)
        html_content = fetch_result["content"]
        
        # Extract title
        title_match = re.search(r'<title[^>]*>([^<]+)</title>', html_content, re.IGNORECASE)
        title = title_match.group(1).strip() if title_match else "Unknown Title"
        
        # Extract text
        extractor = TextExtractor()
        extractor.feed(html_content)
        text = extractor.get_text()
        
        # Limit text to first 5000 characters to avoid huge responses
        if len(text) > 5000:
            text = text[:5000] + "..."
        
        return {"title": title, "text": text}
    except Exception as e:
        return {"title": "Error", "text": f"Error extracting webpage: {str(e)}"}

def search_web(query):
    """
    Search the web for a query.
    
    Args:
        query (str): The search query.
    
    Returns:
        dict: {"results": list}
    """
    # Baseline implementation: empty results
    return {"results": []}