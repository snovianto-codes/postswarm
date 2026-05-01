"""Feed Agent — port 5008
Pulls AI news from 19 RSS sources. Dedupes via SQLite.
Also handles /inspiration endpoint for bookmarklet captures.
"""
import os, json, time, hashlib, sqlite3, re, traceback
from pathlib import Path
from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
import feedparser
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": [
    "http://localhost:8080", "http://127.0.0.1:8080",
    "http://localhost:5009", "http://127.0.0.1:5009",
]}})

DATA_DIR       = Path(__file__).parent.parent / 'data'
DB_PATH        = DATA_DIR / 'seen.db'
PER_SOURCE_CAP = 8

# Wider window for lower-volume authoritative sources so we don't miss them
TIER_AGE_HOURS = {
    1: 72,   # Lab blogs (OpenAI, Google AI, DeepMind, Hugging Face) — post infrequently
    2: 48,   # Curated digests
    3: 36,   # Editorial / analysis
    4: 36,   # Community
    5: 36,   # Singapore/SEA
}

# (tier, name, rss_url)
# Tier 1 = official lab blogs, Tier 2 = curated digests,
# Tier 3 = editorial/analysis, Tier 4 = community, Tier 5 = Singapore/SEA
SOURCES = [
    (1, 'OpenAI',         'https://openai.com/news/rss.xml'),
    (1, 'Google AI',      'https://blog.google/technology/ai/rss/'),
    (1, 'Google DeepMind','https://deepmind.google/blog/rss.xml'),
    (1, 'Hugging Face',   'https://huggingface.co/blog/feed.xml'),
    (2, 'TLDR AI',        'https://tldr.tech/api/rss/ai'),
    (2, "Ben's Bites",    'https://www.bensbites.com/feed'),
    (2, 'MarkTechPost',   'https://www.marktechpost.com/feed/'),
    (3, 'MIT Tech Review','https://www.technologyreview.com/topic/artificial-intelligence/feed/'),
    (3, 'TechCrunch',     'https://techcrunch.com/feed/'),
    (3, 'TC Asia',        'https://techcrunch.com/tag/asia/feed/'),
    (3, 'Mollick',        'https://www.oneusefulthing.org/feed'),
    (3, 'Simon Willison', 'https://simonwillison.net/atom/everything/'),
    (3, 'Interconnects',  'https://www.interconnects.ai/feed'),
    (3, 'Latent Space',   'https://www.latent.space/feed'),
    (4, 'HN AI',          'https://hnrss.org/newest?q=AI+OR+LLM&points=80'),
    (5, 'e27',            'https://e27.co/feed/'),
    (5, 'Tech Wire Asia', 'https://techwireasia.com/feed/'),
    (5, 'AI Singapore',   'https://aisingapore.org/feed/'),
]

_TAG_RE = re.compile(r'<[^>]+>')


def _db():
    DATA_DIR.mkdir(exist_ok=True)
    c = sqlite3.connect(str(DB_PATH))
    c.execute("""CREATE TABLE IF NOT EXISTS seen(
        hash        TEXT PRIMARY KEY,
        title       TEXT,
        url         TEXT,
        source      TEXT,
        summary     TEXT,
        ts          INTEGER,
        tier        INTEGER,
        dismissed   INTEGER DEFAULT 0,
        posted      INTEGER DEFAULT 0
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS inspiration(
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        url         TEXT,
        title       TEXT,
        body        TEXT,
        saved_at    INTEGER
    )""")
    c.commit()
    return c


def _strip_html(text):
    return _TAG_RE.sub(' ', text or '').strip()


def _fetch_source(tier, source, url):
    """Fetch one source. Returns (items, error_or_None)."""
    cutoff = time.time() - TIER_AGE_HOURS.get(tier, 36) * 3600
    items = []
    try:
        feed = feedparser.parse(url)
        count = 0
        for e in feed.entries:
            if count >= PER_SOURCE_CAP:
                break
            pub_struct = e.get('published_parsed') or e.get('updated_parsed')
            pub = time.mktime(pub_struct) if pub_struct else time.time()
            if pub < cutoff:
                continue
            link = e.get('link', '')
            if not link:
                continue
            h       = hashlib.sha1(link.encode()).hexdigest()
            summary = _strip_html(e.get('summary') or e.get('description') or '')[:500]
            items.append({
                'hash':    h,
                'title':   e.get('title', '').strip()[:200],
                'url':     link,
                'source':  source,
                'summary': summary,
                'ts':      int(pub),
                'tier':    tier,
            })
            count += 1
        return items, None
    except Exception as err:
        return [], str(err)


def fetch_all():
    raw = []
    ok_sources   = []
    fail_sources = []

    for tier, source, url in SOURCES:
        items, err = _fetch_source(tier, source, url)
        if err:
            fail_sources.append(source)
            print(f"[Feed Agent] ✗ {source}: {err}")
        else:
            raw.extend(items)
            ok_sources.append(source)

    print(f"[Feed Agent] Pulled {len(raw)} raw items from {len(ok_sources)} sources "
          f"({len(fail_sources)} failed)")
    return _dedupe(raw)


def _dedupe(items):
    c = _db()
    fresh = []
    for i in items:
        row = c.execute(
            "SELECT dismissed, posted FROM seen WHERE hash=?", (i['hash'],)
        ).fetchone()
        if row and (row[0] or row[1]):
            continue  # skip dismissed or already-posted stories
        c.execute(
            """INSERT OR IGNORE INTO seen(hash,title,url,source,summary,ts,tier)
               VALUES(?,?,?,?,?,?,?)""",
            (i['hash'], i['title'], i['url'], i['source'], i['summary'], i['ts'], i['tier']),
        )
        fresh.append(i)
    c.commit()
    return fresh


# ── Routes ─────────────────────────────────────────────────────────────

@app.route('/health')
def health():
    return jsonify(status='ok')


@app.route('/fetch')
def fetch():
    items = fetch_all()
    print(f"[Feed Agent] → Returning {len(items)} fresh items")
    return jsonify(items=items, count=len(items))


@app.route('/fetch/stream')
def fetch_stream():
    """SSE endpoint — streams per-source progress then final item list."""
    def generate():
        raw = []
        total = len(SOURCES)
        for i, (tier, source, url) in enumerate(SOURCES):
            # notify UI: starting this source
            yield f"data: {json.dumps({'type':'source_start','source':source,'tier':tier,'index':i,'total':total})}\n\n"
            items, err = _fetch_source(tier, source, url)
            count = len(items)
            raw.extend(items)
            status = 'error' if err else ('ok' if count > 0 else 'empty')
            yield f"data: {json.dumps({'type':'source_done','source':source,'tier':tier,'count':count,'status':status,'index':i,'total':total})}\n\n"

        fresh = _dedupe(raw)
        yield f"data: {json.dumps({'type':'done','items':fresh,'count':len(fresh),'scanned':len(raw)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


@app.route('/dismiss', methods=['POST'])
def dismiss():
    data = request.json or {}
    h = data.get('hash', '')
    if h:
        c = _db()
        c.execute("UPDATE seen SET dismissed=1 WHERE hash=?", (h,))
        c.commit()
        print(f"[Feed Agent] Dismissed: {h[:8]}…")
    return jsonify(ok=True)


@app.route('/mark_posted', methods=['POST'])
def mark_posted():
    data = request.json or {}
    h = data.get('hash', '')
    if h:
        c = _db()
        c.execute("UPDATE seen SET posted=1 WHERE hash=?", (h,))
        c.commit()
        print(f"[Feed Agent] Marked posted: {h[:8]}…")
    return jsonify(ok=True)


@app.route('/inspiration', methods=['POST'])
def save_inspiration():
    data = request.json or {}
    c = _db()
    c.execute(
        "INSERT INTO inspiration(url,title,body,saved_at) VALUES(?,?,?,?)",
        (data.get('url', ''), data.get('title', ''), data.get('body', ''), int(time.time())),
    )
    c.commit()
    print(f"[Feed Agent] Saved inspiration: {data.get('title', '')[:60]}")
    return jsonify(ok=True)


@app.route('/inspiration', methods=['GET'])
def get_inspirations():
    c = _db()
    rows = c.execute(
        "SELECT id,url,title,body,saved_at FROM inspiration ORDER BY saved_at DESC LIMIT 20"
    ).fetchall()
    items = [{'id': r[0], 'url': r[1], 'title': r[2], 'body': r[3], 'saved_at': r[4]}
             for r in rows]
    return jsonify(items=items)


@app.route('/sources')
def sources():
    """Returns all configured sources and how many items each has in the DB."""
    c = _db()
    rows = c.execute(
        "SELECT source, COUNT(*) FROM seen GROUP BY source"
    ).fetchall()
    counts = {r[0]: r[1] for r in rows}
    result = [
        {'tier': tier, 'name': name, 'count': counts.get(name, 0)}
        for tier, name, _ in SOURCES
    ]
    return jsonify(sources=result)


@app.route('/recent_posted')
def recent_posted():
    """Returns titles of stories the user has already posted about — used by editor for dedup."""
    c = _db()
    rows = c.execute(
        "SELECT title FROM seen WHERE posted=1 ORDER BY ts DESC LIMIT 20"
    ).fetchall()
    return jsonify(titles=[r[0] for r in rows])


if __name__ == '__main__':
    print("[Feed Agent] Starting on port 5008…")
    app.run(port=5008, debug=False)
