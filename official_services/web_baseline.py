"""
Web baseline service module.
Provides baseline implementations for web-related capabilities.
"""

import urllib.request
import urllib.error
import re
from html.parser import HTMLParser

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
        url (str): The URL to fetch.
    
    Returns:
        dict: {"content": str, "status": int}
    """
    try:
        # Add User-Agent to avoid being blocked
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            content = response.read().decode('utf-8', errors='ignore')
            return {"content": content, "status": 200}
    except Exception as e:
        return {"content": f"Error fetching URL: {str(e)}", "status": 500}

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