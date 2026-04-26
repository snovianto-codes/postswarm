"""Web Agent — port 5002
Called by Research Agent. If topic contains a URL, fetches and reads it first.
Otherwise generates grounded research points from Gemini.
"""
import os, re, json, traceback, ipaddress
from html.parser import HTMLParser
from urllib.parse import urlparse
import urllib.request
from flask import Flask, request, jsonify
from flask_cors import CORS
from google import genai
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
_client = genai.Client(api_key=os.environ['GEMINI_API_KEY'])

app = Flask(__name__)
CORS(app, resources={r"/run": {"origins": ["http://localhost:5001","http://127.0.0.1:5001","http://localhost:8080","http://127.0.0.1:8080"]}, r"/health": {"origins": "*"}})

DEFAULT_MODEL = 'gemini-2.5-flash'
URL_RE  = re.compile(r'https?://\S+', re.I)
MAX_CHARS = 8000


# ── HTML → plain text ────────────────────────────────────────────────

class _Stripper(HTMLParser):
    # Tags whose full subtree we discard
    SKIP = {'script', 'style', 'nav', 'footer', 'header', 'aside',
            'noscript', 'figure', 'figcaption', 'button', 'form',
            'iframe', 'svg', 'menu'}
    # Tags that signal article body — we prefer content inside these
    ARTICLE = {'article', 'main', 'section'}

    def __init__(self):
        super().__init__()
        self._skip    = 0
        self._article = 0
        self.chunks   = []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        if tag in self.ARTICLE:
            self._article += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        if tag in self.ARTICLE and self._article:
            self._article -= 1

    def handle_data(self, data):
        if self._skip:
            return
        t = data.strip()
        # Skip short fragments (menus, labels, timestamps, share counts)
        if t and len(t) > 25:
            self.chunks.append(t)

    def text(self):
        return '\n'.join(self.chunks)


def _validate_url(url: str) -> None:
    """Raise ValueError for URLs that could enable SSRF attacks."""
    parsed = urlparse(url)
    if parsed.scheme not in ('https', 'http'):
        raise ValueError(f"Scheme '{parsed.scheme}' not allowed — only http/https")
    hostname = parsed.hostname or ''
    # Block IP-based access to private/loopback ranges
    try:
        addr = ipaddress.ip_address(hostname)
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
            raise ValueError(f"Private/reserved IP not allowed: {hostname}")
    except ValueError as e:
        if 'not allowed' in str(e):
            raise
        # hostname is a domain name, not an IP — that's fine
    # Block localhost by name
    if hostname.lower() in ('localhost', 'metadata.google.internal'):
        raise ValueError(f"Blocked hostname: {hostname}")


def fetch_url(url: str) -> str:
    """Fetch a URL and return stripped plain text (capped at MAX_CHARS)."""
    _validate_url(url)
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        # Guard against huge responses
        html = resp.read(MAX_CHARS * 10).decode('utf-8', errors='replace')
    stripper = _Stripper()
    stripper.feed(html)
    text = stripper.text()
    return text[:MAX_CHARS]


# ── Routes ────────────────────────────────────────────────────────────

@app.route('/health')
def health():
    return jsonify(status='ok')


@app.route('/run', methods=['POST'])
def run():
    data  = request.json or {}
    topic = data.get('topic', '')
    model = data.get('model', DEFAULT_MODEL)

    urls   = URL_RE.findall(topic)
    article_text = ''

    if urls:
        url = urls[0]
        print(f"[Web Agent] ← URL detected: {url}")
        print(f"[Web Agent] Fetching article…")
        try:
            article_text = fetch_url(url)
            print(f"[Web Agent] ✓ Fetched {len(article_text)} chars from {url}")
        except Exception as e:
            print(f"[Web Agent] [ERROR] Could not fetch URL: {e}")
    else:
        print(f"[Web Agent] ← Received from Research Agent | Searching: {topic[:60]}...")

    # Build the Gemini prompt
    if article_text:
        prompt = f"""You have been given the full text of an article. Extract exactly 5 key research points from it.

Article URL: {urls[0]}
Article text:
{article_text}

Requirements:
- Each point must be a concrete fact, finding, or insight from this specific article
- Quote or closely paraphrase the article — do not invent
- Keep each point under 50 words
- Focus on what matters for a LinkedIn post about the topic

Return as a JSON array of 5 strings. Example:
["point 1", "point 2", "point 3", "point 4", "point 5"]

Return ONLY the JSON array, no other text."""
    else:
        prompt = f"""You are a research assistant. Generate exactly 5 grounded, specific research points about this topic:

Topic: {topic}

Requirements:
- Each point must be a concrete fact, statistic, or insight (not vague)
- Include source context where possible (e.g. "According to McKinsey...", "A 2024 study found...")
- Keep each point under 40 words
- Focus on business impact, adoption rates, and practical realities
- Be specific, not generic

Return as a JSON array of strings. Example:
["point 1", "point 2", "point 3", "point 4", "point 5"]

Return ONLY the JSON array, no other text."""

    try:
        response = _client.models.generate_content(model=model, contents=prompt)
        text = response.text.strip()
        if text.startswith('```'):
            text = text.split('```')[1]
            if text.startswith('json'):
                text = text[4:]
        data_points = json.loads(text.strip())
        source = f"from article" if article_text else "from topic"
        print(f"[Web Agent] ✓ Generated {len(data_points)} research points ({source})")
        return jsonify(data_points=data_points, source_url=urls[0] if urls else None)
    except Exception as e:
        print(f"[Web Agent] [ERROR] {type(e).__name__}: {e}")
        print(traceback.format_exc())
        if article_text:
            # fallback: return raw sentences from article as points
            sentences = [s.strip() for s in article_text.split('.') if len(s.strip()) > 40][:5]
            return jsonify(data_points=sentences or [article_text[:200]], source_url=urls[0] if urls else None)
        return jsonify(data_points=[], source_url=None)


if __name__ == '__main__':
    print("[Web Agent] Starting on port 5002...")
    app.run(port=5002, debug=False)
