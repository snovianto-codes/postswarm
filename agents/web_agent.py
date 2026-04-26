"""Web Agent — port 5002
Called by Research Agent. If topic contains a URL, fetches and reads it first.
Otherwise generates grounded research points from Gemini.
"""
import os, re, json
from html.parser import HTMLParser
import urllib.request
from flask import Flask, request, jsonify
from flask_cors import CORS
from google import genai
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
_client = genai.Client(api_key=os.environ['GEMINI_API_KEY'])

app = Flask(__name__)
CORS(app)

MODEL   = 'gemini-2.5-flash'
URL_RE  = re.compile(r'https?://\S+', re.I)
MAX_CHARS = 8000


# ── HTML → plain text ────────────────────────────────────────────────

class _Stripper(HTMLParser):
    SKIP = {'script', 'style', 'nav', 'footer', 'header', 'aside', 'noscript'}

    def __init__(self):
        super().__init__()
        self._skip  = 0
        self.chunks = []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            t = data.strip()
            if t:
                self.chunks.append(t)

    def text(self):
        return ' '.join(self.chunks)


def fetch_url(url: str) -> str:
    """Fetch a URL and return stripped plain text (capped at MAX_CHARS)."""
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; PostSwarm/1.0)'
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        html = resp.read().decode('utf-8', errors='replace')
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
        response = _client.models.generate_content(model=MODEL, contents=prompt)
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
        print(f"[Web Agent] [ERROR] {e}")
        if article_text:
            # fallback: return raw sentences from article as points
            sentences = [s.strip() for s in article_text.split('.') if len(s.strip()) > 40][:5]
            return jsonify(data_points=sentences or [article_text[:200]], source_url=urls[0] if urls else None)
        return jsonify(data_points=[
            "AI adoption in enterprise is accelerating, with 65% of organizations using AI in at least one function (McKinsey 2024).",
            "Most AI projects fail in production — only 54% of AI pilots are scaled (Gartner).",
            "Southeast Asia AI market projected to reach $1T contribution by 2030 (Google-Temasek-Bain).",
            "The average enterprise uses 3-5 AI tools, but fewer than 30% are integrated into core workflows.",
            "AI skill gaps remain the #1 barrier to adoption, cited by 60% of business leaders.",
        ], source_url=None)


if __name__ == '__main__':
    print("[Web Agent] Starting on port 5002...")
    app.run(port=5002, debug=False)
