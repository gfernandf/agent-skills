"""
Web baseline service module.
Provides baseline implementations for web-related capabilities.
"""

import urllib.request
import urllib.error
import urllib.parse
import re
import time
from html.parser import HTMLParser

from runtime.observability import elapsed_ms, log_event

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
    start_time = time.perf_counter()
    parsed_url = urllib.parse.urlparse(url) if isinstance(url, str) and url.strip() else None

    def _finish(payload, status):
        log_event(
            "service.web.fetch",
            status=status,
            http_status=payload.get("status"),
            scheme=(parsed_url.scheme if parsed_url else None),
            host=(parsed_url.netloc if parsed_url else None),
            duration_ms=elapsed_ms(start_time),
        )
        return payload

    log_event(
        "service.web.fetch.start",
        url=url,
        scheme=(parsed_url.scheme if parsed_url else None),
        host=(parsed_url.netloc if parsed_url else None),
    )

    ok, err = _validate_url(url)
    if not ok:
        return _finish({"content": err, "status": 400}, "rejected")

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "AgentSkills/1.0 (capability=web.fetch)"}
        )
        with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT_SECONDS) as response:
            raw = response.read(_MAX_RESPONSE_BYTES)
            content = raw.decode("utf-8", errors="ignore")
            return _finish({"content": content, "status": response.status}, "completed")
    except urllib.error.HTTPError as e:
        return _finish({"content": f"HTTP error: {e.code} {e.reason}", "status": e.code}, "failed")
    except urllib.error.URLError as e:
        return _finish({"content": f"URL error: {e.reason}", "status": 502}, "failed")
    except TimeoutError:
        return _finish({"content": f"Request timed out after {_FETCH_TIMEOUT_SECONDS}s.", "status": 504}, "failed")
    except Exception as e:
        return _finish({"content": f"Unexpected error: {type(e).__name__}: {e}", "status": 500}, "failed")

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


def verify_source(url):
    """
    Verify trust signals for a source URL.

    Args:
        url (str): URL to verify.

    Returns:
        dict: {"trusted": bool, "reason": str, "normalized_source": dict}
    """
    ok, err = _validate_url(url)
    if not ok:
        return {
            "trusted": False,
            "reason": err,
            "normalized_source": {},
        }

    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower()

    untrusted_patterns = ("localhost", "127.0.0.1", "0.0.0.0")
    trusted = not any(pattern in host for pattern in untrusted_patterns)
    reason = "trusted_domain" if trusted else "local_or_private_host"

    return {
        "trusted": trusted,
        "reason": reason,
        "normalized_source": {
            "scheme": parsed.scheme.lower(),
            "host": host,
            "path": parsed.path or "/",
        },
    }