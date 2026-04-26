"""Orchestrator — port 5000
Serves PostSwarm.html at / and runs the agent pipeline via SSE at /run.
No CORS needed — frontend and backend share the same origin.
"""
import os, json, time, re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, request, Response, stream_with_context, send_file
import requests as http
from dotenv import load_dotenv

URL_RE = re.compile(r'https?://\S+', re.I)

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

app = Flask(__name__)

HTML_PATH       = Path(__file__).parent.parent / 'PostSwarm.html'
RESEARCH_URL    = 'http://localhost:5001/run'
PERSPECTIVE_URL = 'http://localhost:5005/run'
HOOK_URL        = 'http://localhost:5006/run'
WRITER_URL      = 'http://localhost:5007/run'
TIMEOUT         = 60

AGENT_PORTS = {
    'web':         5002,
    'fact':        5003,
    'devil':       5004,
    'perspective': 5005,
    'hook':        5006,
    'writer':      5007,
    'research':    5001,
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


@app.route('/run')
def run():
    topic = request.args.get('topic', '')
    take  = request.args.get('take', '')
    tone  = request.args.get('tone', 'Skeptical')

    banner(f"NEW REQUEST\n  topic : {topic[:55]}\n  take  : {take[:45]}\n  tone  : {tone}")

    def generate():
        try:
            yield from make_pipeline(topic, take, tone)
        except Exception as e:
            print(f"[{ts()}] [Orchestrator] [ERROR] Pipeline crashed: {e}")
            yield sse({'type': 'error', 'message': str(e)})

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


# ── Pipeline ──────────────────────────────────────────────────────────

def make_pipeline(topic, take, tone):

    # ── 1. Research ─────────────────────────────────────────────────
    print(f"[{ts()}] [Orchestrator] ▶  STAGE 1 — Research Agent")
    yield sse({'type': 'agent_visible', 'agent': 'research'})
    yield sse({'type': 'agent_status',  'agent': 'research', 'status': 'RUNNING'})

    urls = URL_RE.findall(topic)
    if urls:
        yield sse({'type': 'agent_status', 'agent': 'research', 'status': 'RUNNING',
                   'log': f'URL detected — fetching article…'})
        yield sse({'type': 'agent_visible', 'agent': 'web'})
        yield sse({'type': 'agent_status',  'agent': 'web', 'status': 'RUNNING',
                   'log': f'Reading: {urls[0][:55]}…'})
    else:
        yield sse({'type': 'agent_status',  'agent': 'research', 'status': 'RUNNING',
                   'log': 'Calling Web + Fact Checker + Devil\'s Advocate…'})

    research = {}
    t0 = time.time()
    try:
        print(f"[{ts()}] [Orchestrator]    → POST {RESEARCH_URL}")
        r = http.post(RESEARCH_URL,
                      json={'topic': topic, 'take': take, 'tone': tone},
                      timeout=TIMEOUT)
        r.raise_for_status()
        research = r.json()

        for agent_id, log_msg in (
            ('web',   'Fetched research points from Web Agent'),
            ('fact',  'Fact Checker verified claims'),
            ('devil', 'Devil\'s Advocate added counter-arguments'),
        ):
            yield sse({'type': 'agent_visible', 'agent': agent_id})
            yield sse({'type': 'agent_status',  'agent': agent_id, 'status': 'RUNNING', 'log': log_msg})
            yield sse({'type': 'agent_status',  'agent': agent_id, 'status': 'DONE', 'elapsed': 0})

        elapsed = int((time.time() - t0) * 1000)
        yield sse({'type': 'agent_status', 'agent': 'research', 'status': 'DONE', 'elapsed': elapsed})
        print(f"[{ts()}] [Orchestrator]    ✓ Research DONE ({elapsed}ms) — "
              f"{len(research.get('verified',[]))} facts, "
              f"{len(research.get('counter_points',[]))} counters")
    except Exception as e:
        print(f"[{ts()}] [Orchestrator]    ✗ Research FAILED: {e}")
        yield sse({'type': 'agent_status', 'agent': 'research', 'status': 'FAILED'})

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
        r = http.post(HOOK_URL, json={'topic': topic, 'take': take}, timeout=TIMEOUT)
        r.raise_for_status()
        result = r.json().get('hooks', [])
        print(f"[{ts()}] [Orchestrator]    ✓ Hook Agent — {len(result)} hooks returned")
        return result

    def fetch_perspective():
        print(f"[{ts()}] [Orchestrator]    → POST {PERSPECTIVE_URL}")
        r = http.post(PERSPECTIVE_URL, json={'topic': topic, 'research': research}, timeout=TIMEOUT)
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
                else:
                    insights = result
                yield sse({'type': 'agent_status', 'agent': label, 'status': 'DONE', 'elapsed': elapsed})
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
                            'research': research, 'hooks': hooks, 'insights': insights},
                      timeout=TIMEOUT)
        r.raise_for_status()
        final_post = r.json().get('post', '')
        elapsed = int((time.time() - t2) * 1000)
        yield sse({'type': 'agent_status', 'agent': 'writer', 'status': 'RUNNING', 'log': 'Applying voice and tone…'})
        yield sse({'type': 'agent_status', 'agent': 'writer', 'status': 'DONE', 'elapsed': elapsed})
        print(f"[{ts()}] [Orchestrator]    ✓ Writer DONE ({elapsed}ms) — {len(final_post.split())} words")
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
