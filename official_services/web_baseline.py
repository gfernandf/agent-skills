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


_META_CHARSET_RE = re.compile(
    rb'''<meta[^>]+charset\s*=\s*["']?\s*([A-Za-z0-9_-]+)''', re.IGNORECASE
)
_META_HTTP_EQUIV_RE = re.compile(
    rb'''<meta[^>]+http-equiv\s*=\s*["']?Content-Type[^>]+charset\s*=\s*([A-Za-z0-9_-]+)''',
    re.IGNORECASE,
)


def _detect_charset(raw: bytes, content_type: str) -> str:
    """Detect charset from Content-Type header, HTML meta tag, or heuristic."""
    # 1. Content-Type header
    if "charset=" in content_type:
        charset = content_type.split("charset=")[-1].split(";")[0].strip().strip('"\'')
        if charset:
            return charset

    # 2. HTML <meta charset="..."> or <meta http-equiv="Content-Type" ...>
    head = raw[:4096]
    m = _META_CHARSET_RE.search(head) or _META_HTTP_EQUIV_RE.search(head)
    if m:
        return m.group(1).decode("ascii", errors="ignore")

    # 3. Try utf-8 strict first — if it decodes cleanly, it's very likely utf-8
    try:
        raw[:2048].decode("utf-8", errors="strict")
        return "utf-8"
    except UnicodeDecodeError:
        pass

    # 4. Fallback to cp1252 (common for European pages without declared charset)
    return "cp1252"


def _repair_mojibake(text: str) -> str:
    """Repair common mojibake patterns caused by encoding mismatches.

    Handles two strategies:
    1. Full-text reversal: re-encode as latin-1/cp1252 and decode as UTF-8.
       Works when the entire text was UTF-8 bytes misread as a single-byte encoding.
    2. Curated replacement table for patterns that survive valid UTF-8 decoding
       but represent garbled characters (e.g. server-side double-encoding).
    """
    # Quick bail: pure ASCII needs no repair
    if text.isascii():
        return text

    # Strategy 1: try full-text latin-1→UTF-8 round-trip
    for codec in ("latin-1", "cp1252"):
        try:
            candidate = text.encode(codec).decode("utf-8")
            if candidate != text:
                return candidate
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass

    # Strategy 2: curated table (sorted longest-first to avoid partial matches)
    _REPAIRS = [
        ("Ôé¼",  "\u20ac"),   # € (non-standard double-encoding)
        ("â\u0082\u00ac", "\u20ac"),  # € (UTF-8 through cp1252)
        ("\u00e2\u0080\u0099", "\u2019"),  # ' right single quote
        ("\u00e2\u0080\u0098", "\u2018"),  # ' left single quote
        ("\u00e2\u0080\u009c", "\u201c"),  # " left double quote
        ("\u00e2\u0080\u009d", "\u201d"),  # " right double quote
        ("\u00e2\u0080\u0094", "\u2014"),  # — em dash
        ("\u00e2\u0080\u0093", "\u2013"),  # – en dash
        ("\u00e2\u0080\u00a2", "\u2022"),  # • bullet
        ("\u00e2\u0080\u00a6", "\u2026"),  # … ellipsis
        ("\u00c3\u00a9", "\u00e9"),  # é
        ("\u00c3\u00a8", "\u00e8"),  # è
        ("\u00c3\u00a1", "\u00e1"),  # á
        ("\u00c3\u00a0", "\u00e0"),  # à
        ("\u00c3\u00b3", "\u00f3"),  # ó
        ("\u00c3\u00b2", "\u00f2"),  # ò
        ("\u00c3\u00b1", "\u00f1"),  # ñ
        ("\u00c3\u00bc", "\u00fc"),  # ü
        ("\u00c3\u00b6", "\u00f6"),  # ö
        ("\u00c3\u00a4", "\u00e4"),  # ä
        ("\u00c3\u00a2", "\u00e2"),  # â
        ("\u00c3\u00ae", "\u00ee"),  # î
        ("\u00c3\u00a7", "\u00e7"),  # ç
        ("\u00c3\u00ba", "\u00fa"),  # ú
        ("\u00c3\u00ad", "\u00ed"),  # í
    ]
    for bad, good in _REPAIRS:
        if bad in text:
            text = text.replace(bad, good)

    return text


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
            # Reject binary content types (PDFs, images, etc.)
            ct = response.headers.get("Content-Type", "")
            ct_lower = ct.lower()
            if any(t in ct_lower for t in ("application/pdf", "image/", "audio/", "video/", "application/octet-stream", "application/zip")):
                return _finish({"content": f"Binary content type not supported: {ct}", "status": 415}, "rejected")
            raw = response.read(_MAX_RESPONSE_BYTES)
            charset = _detect_charset(raw, ct)
            try:
                content = raw.decode(charset, errors="replace")
            except (LookupError, UnicodeDecodeError):
                content = raw.decode("utf-8", errors="replace")
            content = _repair_mojibake(content)
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


def _parse_ddg_results(html, limit):
    """Parse DuckDuckGo HTML search results into structured items."""
    results = []
    # DuckDuckGo result blocks: <a rel="nofollow" class="result__a" href="...">
    link_pattern = re.compile(
        r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
        re.DOTALL,
    )
    snippet_pattern = re.compile(
        r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
        re.DOTALL,
    )

    links = link_pattern.findall(html)
    snippets = snippet_pattern.findall(html)

    for idx, (raw_href, raw_title) in enumerate(links[:limit]):
        # Resolve DDG redirect URL → actual URL
        url = raw_href
        uddg_match = re.search(r'[?&]uddg=([^&]+)', raw_href)
        if uddg_match:
            url = urllib.parse.unquote(uddg_match.group(1))

        title = re.sub(r'<[^>]+>', '', raw_title).strip()
        snippet = ""
        if idx < len(snippets):
            snippet = re.sub(r'<[^>]+>', '', snippets[idx]).strip()

        parsed_url = urllib.parse.urlparse(url)
        domain = parsed_url.netloc or ""

        results.append({
            "url": url,
            "title": title or f"Result {idx + 1}",
            "snippet": snippet,
            "rank": idx + 1,
            "domain": domain,
        })

    return results


def _synthetic_results(query, limit):
    """Fallback: generate synthetic results when live search is unavailable."""
    tokens = [t for t in (query or "").split() if len(t) > 2]
    if not tokens:
        tokens = ["topic"]
    results = []
    for i in range(limit):
        word = tokens[i % len(tokens)]
        results.append({
            "url": f"https://example.com/{word.lower()}-{i + 1}",
            "title": f"{word.title()} — Result {i + 1} for '{query}'",
            "snippet": (
                f"Synthetic result {i + 1} for '{query}'. "
                f"Live search unavailable; this placeholder mentions {word}."
            ),
            "rank": i + 1,
            "domain": "example.com",
        })
    return results


def search_web(query, limit=None):
    """
    Search the web using DuckDuckGo (no API key required).

    Falls back to synthetic results if the network request fails.

    Args:
        query (str): The search query.
        limit (int, optional): Maximum number of results (default 5, max 20).

    Returns:
        dict: {"results": list} — each item has url, title, snippet, rank, domain.
    """
    if limit is None:
        limit = 5
    limit = max(1, min(limit, 20))

    if not query or not query.strip():
        return {"results": _synthetic_results(query, limit)}

    t0 = time.time()
    try:
        data = urllib.parse.urlencode({"q": query}).encode("utf-8")
        req = urllib.request.Request(
            "https://html.duckduckgo.com/html/",
            data=data,
            headers={"User-Agent": "AgentSkills/1.0 (capability=web.source.search)"},
        )
        with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT_SECONDS) as resp:
            html = resp.read(_MAX_RESPONSE_BYTES).decode("utf-8", errors="ignore")

        results = _parse_ddg_results(html, limit)
        if results:
            log_event("web.source.search.live",
                      provider="duckduckgo",
                      result_count=len(results),
                      duration_ms=elapsed_ms(t0))
            return {"results": results}
    except Exception:
        pass  # fall through to synthetic

    log_event("web.source.search.fallback",
              reason="live_search_unavailable",
              duration_ms=elapsed_ms(t0))
    return {"results": _synthetic_results(query, limit)}


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


def normalize_search_results(results, mode=None):
    """
    Normalize web search results into corpus item format.

    Args:
        results (list): Search result objects, each with url (required),
            and optionally title, snippet, rank, domain, date.
        mode (str): "quick" (default) uses snippets as content;
            "deep" leaves content empty for downstream resolution.

    Returns:
        dict: {"items": list} — normalized corpus items.
    """
    mode = (mode or "quick").lower()
    items = []

    for idx, result in enumerate(results or []):
        if not isinstance(result, dict):
            continue

        url = result.get("url", "")
        title = result.get("title", "")
        snippet = result.get("snippet", "")

        item = {
            "id": f"src_{idx + 1}",
            "title": title or f"Source {idx + 1}",
            "type": "web_page",
            "source": url,
            "source_ref": {
                "type": "url",
                "location": url,
            },
            "metadata": {
                "snippet": snippet,
                "rank": result.get("rank", idx + 1),
                "domain": result.get("domain", ""),
                "date": result.get("date", ""),
            },
        }

        if mode == "quick":
            item["content"] = snippet or title or ""
        else:
            # Deep mode: leave content empty for research.source.retrieve
            item["content"] = ""

        items.append(item)

    return {"items": items}