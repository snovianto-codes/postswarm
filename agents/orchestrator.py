"""Orchestrator — port 8080
Serves PostSwarm.html at / and runs the agent pipeline via SSE at /run.
No CORS needed — frontend and backend share the same origin.
"""
import os, json, time, re, queue, threading, sqlite3
from pathlib import Path
from datetime import date
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, request, Response, stream_with_context, send_file, abort, jsonify
import requests as http
from dotenv import load_dotenv

URL_RE = re.compile(r'https?://\S+', re.I)

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

app = Flask(__name__)

HTML_PATH       = Path(__file__).parent.parent / 'PostSwarm.html'
DATA_DIR        = Path(__file__).parent.parent / 'data'
RESEARCH_URL    = 'http://localhost:5001/run'
PERSPECTIVE_URL = 'http://localhost:5005/run'
HOOK_URL        = 'http://localhost:5006/run'
WRITER_URL      = 'http://localhost:5007/run'
FEED_URL        = 'http://localhost:5008'
EDITOR_URL      = 'http://localhost:5009/rank'
TIMEOUT         = 60

ALLOWED_MODELS = {
    'gemini-2.5-pro', 'gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-1.5-flash',
}
MAX_TOPIC_LEN = 2000
MAX_TAKE_LEN  = 500
MAX_ROLE_LEN  = 100

AGENT_PORTS = {
    'web':         5002,
    'fact':        5003,
    'devil':       5004,
    'perspective': 5005,
    'hook':        5006,
    'writer':      5007,
    'research':    5001,
    'feed':        5008,
    'editor':      5009,
}


def ts():
    return time.strftime('%H:%M:%S')


def banner(msg):
    print(f"\n{'─'*60}\n  {msg}\n{'─'*60}")


def sse(obj):
    return f"data: {json.dumps(obj)}\n\n"


# ── Routes ────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_file(HTML_PATH)


@app.route('/PostSwarm.html')
def html_file():
    return send_file(HTML_PATH)


@app.route('/health')
def health():
    agent_status = {}
    for name, port in AGENT_PORTS.items():
        try:
            r = http.get(f'http://localhost:{port}/health', timeout=1)
            agent_status[name] = 'ok' if r.ok else 'error'
        except Exception:
            agent_status[name] = 'offline'
    all_ok = all(v == 'ok' for v in agent_status.values())
    print(f"[{ts()}] [Orchestrator] /health → {'ALL OK' if all_ok else 'PARTIAL'} | {agent_status}")
    return {'status': 'ok', 'agents': agent_status, 'all_ready': all_ok}


# ── Digest (Today's Brief) ────────────────────────────────────────────

def _recent_posted_titles():
    """Return titles already posted, for editor dedup."""
    db_path = DATA_DIR / 'seen.db'
    if not db_path.exists():
        return []
    try:
        c = sqlite3.connect(str(db_path))
        rows = c.execute(
            "SELECT title FROM seen WHERE posted=1 ORDER BY ts DESC LIMIT 20"
        ).fetchall()
        return [r[0] for r in rows]
    except Exception:
        return []


def _run_digest():
    DATA_DIR.mkdir(exist_ok=True)
    # 1. Fetch items from feed agent
    r1 = http.get(f'{FEED_URL}/fetch', timeout=45)
    r1.raise_for_status()
    items = r1.json().get('items', [])
    if not items:
        return {'picks': [], 'refreshed_at': int(time.time()), 'items_scanned': 0}

    # 2. Rank with editor agent
    r2 = http.post(EDITOR_URL, json={
        'items': items,
        'role': 'People Manager',
        'recent_posted': _recent_posted_titles(),
        'model': 'gemini-2.5-flash',
    }, timeout=90)
    r2.raise_for_status()
    picks = r2.json().get('picks', [])

    result = {
        'picks': picks,
        'refreshed_at': int(time.time()),
        'items_scanned': len(items),
    }

    # 3. Cache for the day
    cache_file = DATA_DIR / f'digest_{date.today()}.json'
    cache_file.write_text(json.dumps(result))
    print(f"[{ts()}] [Orchestrator] /digest ✓ {len(picks)} picks from {len(items)} items")
    return result


@app.route('/digest')
def digest():
    cache_file = DATA_DIR / f'digest_{date.today()}.json'
    if cache_file.exists():
        data = json.loads(cache_file.read_text())
        data['cached'] = True
        return jsonify(data)
    try:
        return jsonify(_run_digest())
    except Exception as e:
        print(f"[{ts()}] [Orchestrator] /digest ERROR: {e}")
        return jsonify(picks=[], error=str(e), items_scanned=0), 500


@app.route('/digest/refresh', methods=['POST'])
def digest_refresh():
    # Delete today's cache and force a fresh run
    cache_file = DATA_DIR / f'digest_{date.today()}.json'
    if cache_file.exists():
        cache_file.unlink()
    try:
        return jsonify(_run_digest())
    except Exception as e:
        print(f"[{ts()}] [Orchestrator] /digest/refresh ERROR: {e}")
        return jsonify(picks=[], error=str(e)), 500


@app.route('/feed/dismiss', methods=['POST'])
def feed_dismiss():
    try:
        r = http.post(f'{FEED_URL}/dismiss', json=request.json or {}, timeout=5)
        return jsonify(r.json())
    except Exception:
        return jsonify(ok=False)


@app.route('/feed/mark_posted', methods=['POST'])
def feed_mark_posted():
    try:
        r = http.post(f'{FEED_URL}/mark_posted', json=request.json or {}, timeout=5)
        return jsonify(r.json())
    except Exception:
        return jsonify(ok=False)


@app.route('/feed/inspiration', methods=['POST'])
def feed_inspiration():
    try:
        r = http.post(f'{FEED_URL}/inspiration', json=request.json or {}, timeout=5)
        return jsonify(r.json())
    except Exception:
        return jsonify(ok=False)


@app.route('/feed/sources')
def feed_sources():
    try:
        r = http.get(f'{FEED_URL}/sources', timeout=5)
        return jsonify(r.json())
    except Exception:
        return jsonify(sources=[])


@app.route('/feed/stream')
def feed_stream():
    """Proxy the feed agent's SSE progress stream to the frontend."""
    def generate():
        with http.get(f'{FEED_URL}/fetch/stream', stream=True, timeout=120) as r:
            for line in r.iter_lines():
                if line:
                    yield line.decode('utf-8') + '\n\n'
    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


# ── Write pipeline ────────────────────────────────────────────────────

@app.route('/run')
def run():
    topic     = request.args.get('topic',     '')[:MAX_TOPIC_LEN]
    take      = request.args.get('take',      '')[:MAX_TAKE_LEN]
    tone      = request.args.get('tone',      'Skeptical')[:50]
    model     = request.args.get('model',     'gemini-2.5-flash')
    role      = request.args.get('role',      'People Manager')[:MAX_ROLE_LEN]
    post_type = request.args.get('post_type', 'opinion')[:20]

    if model not in ALLOWED_MODELS:
        abort(400, f"Unknown model. Allowed: {', '.join(sorted(ALLOWED_MODELS))}")

    ALLOWED_TONES = {'Skeptical', 'Curious', 'Excited', 'Provocative', 'Balanced'}
    if tone not in ALLOWED_TONES:
        tone = 'Skeptical'  # silently default rather than hard error

    banner(f"NEW REQUEST\n  topic : {topic[:55]}\n  take  : {take[:45]}\n  tone  : {tone}\n  model : {model}\n  role  : {role}")

    def generate():
        try:
            yield from make_pipeline(topic, take, tone, model, role, post_type)
        except Exception as e:
            print(f"[{ts()}] [Orchestrator] [ERROR] Pipeline crashed: {e}")
            yield sse({'type': 'error', 'message': str(e)})

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


# ── Pipeline ──────────────────────────────────────────────────────────

def make_pipeline(topic, take, tone, model='gemini-2.5-flash', role='People Manager', post_type='opinion'):

    # ── 1. Research ─────────────────────────────────────────────────
    print(f"[{ts()}] [Orchestrator] ▶  STAGE 1 — Research Agent")
    yield sse({'type': 'agent_visible', 'agent': 'research'})
    yield sse({'type': 'agent_status',  'agent': 'research', 'status': 'RUNNING',
               'log': 'Coordinating research pipeline…'})

    # Show all sub-agents as RUNNING before the HTTP call so the UI shows
    # activity during the actual processing time (not after it returns).
    urls = URL_RE.findall(topic)
    if urls:
        yield sse({'type': 'agent_visible', 'agent': 'web'})
        yield sse({'type': 'agent_status',  'agent': 'web', 'status': 'RUNNING',
                   'log': f'Fetching article: {urls[0][:50]}…'})
    else:
        yield sse({'type': 'agent_visible', 'agent': 'web'})
        yield sse({'type': 'agent_status',  'agent': 'web', 'status': 'RUNNING',
                   'log': 'Searching for research points…'})

    yield sse({'type': 'agent_visible', 'agent': 'fact'})
    yield sse({'type': 'agent_status',  'agent': 'fact', 'status': 'RUNNING',
               'log': 'Waiting for data to verify…'})
    yield sse({'type': 'agent_visible', 'agent': 'devil'})
    yield sse({'type': 'agent_status',  'agent': 'devil', 'status': 'RUNNING',
               'log': 'Preparing counter-arguments…'})

    # Run the research HTTP call in a thread so we can stream heartbeat logs
    # into the SSE while it processes.
    event_q  = queue.Queue()
    research  = {}
    exc_box   = [None]

    def do_research():
        try:
            print(f"[{ts()}] [Orchestrator]    → POST {RESEARCH_URL}")
            r = http.post(RESEARCH_URL,
                          json={'topic': topic, 'take': take, 'tone': tone,
                                'model': model, 'role': role},
                          timeout=TIMEOUT)
            r.raise_for_status()
            research.update(r.json())
        except Exception as e:
            exc_box[0] = e
        finally:
            event_q.put('__done__')

    thread = threading.Thread(target=do_research, daemon=True)
    thread.start()

    # Heartbeat log messages while research runs
    WEB_LOGS   = ['Scanning sources…', 'Extracting key facts…', 'Summarising findings…']
    FACT_LOGS  = ['Received data points…', 'Cross-referencing claims…', 'Verifying stats…']
    DEVIL_LOGS = ['Analysing thesis…', 'Stress-testing assumptions…', 'Building counter-case…']
    tick = 0
    t0 = time.time()

    while True:
        try:
            msg = event_q.get(timeout=2.5)
            if msg == '__done__':
                break
        except queue.Empty:
            # emit a rolling log to each sub-agent every 2.5 s
            idx = tick % len(WEB_LOGS)
            yield sse({'type': 'agent_status', 'agent': 'web',   'status': 'RUNNING', 'log': WEB_LOGS[idx]})
            yield sse({'type': 'agent_status', 'agent': 'fact',  'status': 'RUNNING', 'log': FACT_LOGS[idx]})
            yield sse({'type': 'agent_status', 'agent': 'devil', 'status': 'RUNNING', 'log': DEVIL_LOGS[idx]})
            tick += 1

    elapsed = int((time.time() - t0) * 1000)

    if exc_box[0]:
        print(f"[{ts()}] [Orchestrator]    ✗ Research FAILED: {exc_box[0]}")
        for a in ('web', 'fact', 'devil', 'research'):
            yield sse({'type': 'agent_status', 'agent': a, 'status': 'FAILED'})
    else:
        # Mark each sub-agent DONE with staggered realistic times
        web_ms   = int(elapsed * 0.55)
        fact_ms  = int(elapsed * 0.75)
        devil_ms = int(elapsed * 0.80)
        yield sse({'type': 'agent_status', 'agent': 'web',   'status': 'DONE', 'elapsed': web_ms})
        yield sse({'type': 'agent_status', 'agent': 'fact',  'status': 'RUNNING', 'log': 'Flagging weak claims…'})
        yield sse({'type': 'agent_status', 'agent': 'devil', 'status': 'RUNNING', 'log': 'Finalising counter-points…'})
        yield sse({'type': 'agent_status', 'agent': 'fact',  'status': 'DONE', 'elapsed': fact_ms})
        yield sse({'type': 'agent_status', 'agent': 'devil', 'status': 'DONE', 'elapsed': devil_ms})
        yield sse({'type': 'agent_status', 'agent': 'research', 'status': 'DONE', 'elapsed': elapsed})
        # Emit detail payloads so the UI can show what each sub-agent found
        print(f"[{ts()}] [Orchestrator]    ▶ Emitting agent_detail events (web/fact/devil)…")
        yield sse({'type': 'agent_detail', 'agent': 'web', 'data': {
            'research_points': research.get('data_points', []),
            'source_url': research.get('source_url'),
        }})
        yield sse({'type': 'agent_detail', 'agent': 'fact', 'data': {
            'verified': research.get('verified', []),
        }})
        yield sse({'type': 'agent_detail', 'agent': 'devil', 'data': {
            'counter_points': research.get('counter_points', []),
        }})
        print(f"[{ts()}] [Orchestrator]    ✓ Research DONE ({elapsed}ms) — "
              f"{len(research.get('verified',[]))} facts, "
              f"{len(research.get('counter_points',[]))} counters")

    # ── 2. Hook + Perspective (parallel) ────────────────────────────
    print(f"[{ts()}] [Orchestrator] ▶  STAGE 2 — Hook + Perspective (parallel)")
    for agent_id in ('hook', 'perspective'):
        yield sse({'type': 'agent_visible', 'agent': agent_id})
        yield sse({'type': 'agent_status',  'agent': agent_id, 'status': 'RUNNING'})

    yield sse({'type': 'agent_status', 'agent': 'hook',        'status': 'RUNNING', 'log': 'Generating 5 hook variants…'})
    yield sse({'type': 'agent_status', 'agent': 'perspective', 'status': 'RUNNING', 'log': 'Mapping SEA business angle…'})

    hooks = []
    insights = []

    def fetch_hooks():
        print(f"[{ts()}] [Orchestrator]    → POST {HOOK_URL}")
        r = http.post(HOOK_URL, json={'topic': topic, 'take': take, 'model': model, 'role': role},
                      timeout=TIMEOUT)
        r.raise_for_status()
        result = r.json().get('hooks', [])
        print(f"[{ts()}] [Orchestrator]    ✓ Hook Agent — {len(result)} hooks returned")
        return result

    def fetch_perspective():
        print(f"[{ts()}] [Orchestrator]    → POST {PERSPECTIVE_URL}")
        r = http.post(PERSPECTIVE_URL,
                      json={'topic': topic, 'research': research, 'model': model, 'role': role},
                      timeout=TIMEOUT)
        r.raise_for_status()
        result = r.json().get('insights', [])
        print(f"[{ts()}] [Orchestrator]    ✓ Perspective Agent — {len(result)} insights returned")
        return result

    t1 = time.time()
    with ThreadPoolExecutor(max_workers=2) as ex:
        fut_h = ex.submit(fetch_hooks)
        fut_p = ex.submit(fetch_perspective)
        for fut, label in ((fut_h, 'hook'), (fut_p, 'perspective')):
            try:
                result  = fut.result(timeout=TIMEOUT + 5)
                elapsed = int((time.time() - t1) * 1000)
                if label == 'hook':
                    hooks = result
                    yield sse({'type': 'agent_status', 'agent': label, 'status': 'DONE', 'elapsed': elapsed})
                    yield sse({'type': 'agent_detail', 'agent': 'hook', 'data': {'hooks': hooks}})
                else:
                    insights = result
                    yield sse({'type': 'agent_status', 'agent': label, 'status': 'DONE', 'elapsed': elapsed})
                    yield sse({'type': 'agent_detail', 'agent': 'perspective', 'data': {'insights': insights}})
            except Exception as e:
                print(f"[{ts()}] [Orchestrator]    ✗ {label} FAILED: {e}")
                yield sse({'type': 'agent_status', 'agent': label, 'status': 'FAILED'})

    # ── 3. Writer ────────────────────────────────────────────────────
    print(f"[{ts()}] [Orchestrator] ▶  STAGE 3 — Writer Agent")
    yield sse({'type': 'agent_visible', 'agent': 'writer'})
    yield sse({'type': 'agent_status',  'agent': 'writer', 'status': 'RUNNING'})
    yield sse({'type': 'agent_status',  'agent': 'writer', 'status': 'RUNNING', 'log': 'Drafting post…'})

    final_post = ''
    t2 = time.time()
    try:
        print(f"[{ts()}] [Orchestrator]    → POST {WRITER_URL}")
        r = http.post(WRITER_URL,
                      json={'topic': topic, 'take': take, 'tone': tone,
                            'research': research, 'hooks': hooks, 'insights': insights,
                            'model': model, 'role': role, 'post_type': post_type},
                      timeout=TIMEOUT)
        r.raise_for_status()
        writer_resp = r.json()
        final_post  = writer_resp.get('post', '')
        model_used  = writer_resp.get('model_used', model)
        elapsed = int((time.time() - t2) * 1000)
        yield sse({'type': 'agent_status', 'agent': 'writer', 'status': 'RUNNING', 'log': 'Applying voice and tone…'})
        yield sse({'type': 'agent_status', 'agent': 'writer', 'status': 'DONE', 'elapsed': elapsed})
        yield sse({'type': 'agent_detail', 'agent': 'writer', 'data': {
            'word_count': len(final_post.split()),
            'model_used': model_used,
        }})
        print(f"[{ts()}] [Orchestrator]    ✓ Writer DONE ({elapsed}ms) — {len(final_post.split())} words via {model_used}")
    except Exception as e:
        print(f"[{ts()}] [Orchestrator]    ✗ Writer FAILED: {e}")
        yield sse({'type': 'agent_status', 'agent': 'writer', 'status': 'FAILED'})
        final_post = f"[Writer failed]\n\nTopic: {topic}"

    total = int((time.time() - t0) * 1000)
    print(f"\n[{ts()}] [Orchestrator] ✅ PIPELINE COMPLETE — {total/1000:.1f}s total")
    print(f"\n{'═'*60}\nFINAL POST:\n{'─'*60}\n{final_post}\n{'═'*60}\n")
    yield sse({'type': 'done', 'post': final_post})


if __name__ == '__main__':
    banner(f"PostSwarm Orchestrator\n  http://localhost:8080  ←  open this in your browser")
    app.run(host='0.0.0.0', port=8080, debug=False, threaded=True)
