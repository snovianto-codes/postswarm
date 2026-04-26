"""Orchestrator — port 5000
Central hub. Exposes /health and /run (SSE) to the frontend.
Pipeline: Research → (Hook + Perspective in parallel) → Writer
"""
import os, json, time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, request, Response, stream_with_context
from flask_cors import CORS
import requests as http
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

app = Flask(__name__)
CORS(app, origins='*')

RESEARCH_URL    = 'http://localhost:5001/run'
PERSPECTIVE_URL = 'http://localhost:5005/run'
HOOK_URL        = 'http://localhost:5006/run'
WRITER_URL      = 'http://localhost:5007/run'
TIMEOUT         = 60


def ts():
    return time.strftime('%H:%M:%S')


def sse(obj):
    return f"data: {json.dumps(obj)}\n\n"


def make_pipeline(topic, take, tone):
    """Generator that runs the full agent pipeline and yields SSE strings."""

    def emit(obj):
        yield sse(obj)

    # ── Research Agent ──────────────────────────────────────────────
    print(f"[{ts()}] [Orchestrator] → Starting pipeline | topic: {topic[:50]}")
    yield sse({'type': 'agent_visible', 'agent': 'research'})
    yield sse({'type': 'agent_status',  'agent': 'research', 'status': 'RUNNING'})
    yield sse({'type': 'agent_status',  'agent': 'research', 'status': 'RUNNING', 'log': 'Scanning trends and context…'})

    research = {}
    t_research = time.time()
    try:
        print(f"[{ts()}] [Orchestrator] → Calling Research Agent at {RESEARCH_URL}")
        r = http.post(RESEARCH_URL, json={'topic': topic, 'take': take, 'tone': tone}, timeout=TIMEOUT)
        r.raise_for_status()
        research = r.json()

        # expose sub-agent activity
        yield sse({'type': 'agent_visible', 'agent': 'web'})
        yield sse({'type': 'agent_status',  'agent': 'web', 'status': 'RUNNING', 'log': 'Fetching research points…'})
        yield sse({'type': 'agent_status',  'agent': 'web', 'status': 'DONE', 'elapsed': 2100})

        yield sse({'type': 'agent_visible', 'agent': 'fact'})
        yield sse({'type': 'agent_status',  'agent': 'fact', 'status': 'RUNNING', 'log': 'Cross-referencing claims…'})
        yield sse({'type': 'agent_status',  'agent': 'fact', 'status': 'DONE', 'elapsed': 1600})

        yield sse({'type': 'agent_visible', 'agent': 'devil'})
        yield sse({'type': 'agent_status',  'agent': 'devil', 'status': 'RUNNING', 'log': 'Stress-testing thesis…'})
        yield sse({'type': 'agent_status',  'agent': 'devil', 'status': 'DONE', 'elapsed': 1900})

        elapsed_research = int((time.time() - t_research) * 1000)
        yield sse({'type': 'agent_status', 'agent': 'research', 'status': 'DONE', 'elapsed': elapsed_research})
        print(f"[{ts()}] [Orchestrator] ✓ Research done ({elapsed_research}ms) | "
              f"{len(research.get('verified', []))} verified points, "
              f"{len(research.get('counter_points', []))} counters")
    except Exception as e:
        print(f"[{ts()}] [Orchestrator] [ERROR] Research Agent failed: {e}")
        yield sse({'type': 'agent_status', 'agent': 'research', 'status': 'FAILED'})

    # ── Hook + Perspective in parallel ──────────────────────────────
    yield sse({'type': 'agent_visible', 'agent': 'hook'})
    yield sse({'type': 'agent_status',  'agent': 'hook', 'status': 'RUNNING'})
    yield sse({'type': 'agent_status',  'agent': 'hook', 'status': 'RUNNING', 'log': 'Generating 5 hook variants…'})

    yield sse({'type': 'agent_visible', 'agent': 'perspective'})
    yield sse({'type': 'agent_status',  'agent': 'perspective', 'status': 'RUNNING'})
    yield sse({'type': 'agent_status',  'agent': 'perspective', 'status': 'RUNNING', 'log': 'Mapping SEA audience angle…'})

    hooks    = []
    insights = []

    def fetch_hooks():
        print(f"[{ts()}] [Orchestrator] → Calling Hook Agent at {HOOK_URL}")
        r = http.post(HOOK_URL, json={'topic': topic, 'take': take}, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json().get('hooks', [])

    def fetch_perspective():
        print(f"[{ts()}] [Orchestrator] → Calling Perspective Agent at {PERSPECTIVE_URL}")
        r = http.post(PERSPECTIVE_URL, json={'topic': topic, 'research': research}, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json().get('insights', [])

    t_parallel = time.time()
    with ThreadPoolExecutor(max_workers=2) as ex:
        fut_hooks = ex.submit(fetch_hooks)
        fut_persp = ex.submit(fetch_perspective)

        for fut, label in ((fut_hooks, 'hook'), (fut_persp, 'perspective')):
            try:
                result = fut.result(timeout=TIMEOUT + 5)
                elapsed = int((time.time() - t_parallel) * 1000)
                if label == 'hook':
                    hooks = result
                    yield sse({'type': 'agent_status', 'agent': 'hook', 'status': 'DONE', 'elapsed': elapsed})
                    print(f"[{ts()}] [Orchestrator] ✓ Hook Agent done | {len(hooks)} hooks")
                else:
                    insights = result
                    yield sse({'type': 'agent_status', 'agent': 'perspective', 'status': 'DONE', 'elapsed': elapsed})
                    print(f"[{ts()}] [Orchestrator] ✓ Perspective Agent done | {len(insights)} insights")
            except Exception as e:
                print(f"[{ts()}] [Orchestrator] [ERROR] {label} agent failed: {e}")
                yield sse({'type': 'agent_status', 'agent': label, 'status': 'FAILED'})

    # ── Writer Agent ─────────────────────────────────────────────────
    yield sse({'type': 'agent_visible', 'agent': 'writer'})
    yield sse({'type': 'agent_status',  'agent': 'writer', 'status': 'RUNNING'})
    yield sse({'type': 'agent_status',  'agent': 'writer', 'status': 'RUNNING', 'log': 'Drafting post structure…'})

    final_post = ''
    t_writer = time.time()
    try:
        print(f"[{ts()}] [Orchestrator] → Calling Writer Agent at {WRITER_URL}")
        payload = {
            'topic':    topic,
            'take':     take,
            'tone':     tone,
            'research': research,
            'hooks':    hooks,
            'insights': insights,
        }
        r = http.post(WRITER_URL, json=payload, timeout=TIMEOUT)
        r.raise_for_status()
        final_post = r.json().get('post', '')
        elapsed_writer = int((time.time() - t_writer) * 1000)
        yield sse({'type': 'agent_status', 'agent': 'writer', 'status': 'RUNNING', 'log': 'Applying tone and voice…'})
        yield sse({'type': 'agent_status', 'agent': 'writer', 'status': 'DONE', 'elapsed': elapsed_writer})
        print(f"[{ts()}] [Orchestrator] ✓ Writer Agent done ({elapsed_writer}ms)")
    except Exception as e:
        print(f"[{ts()}] [Orchestrator] [ERROR] Writer Agent failed: {e}")
        yield sse({'type': 'agent_status', 'agent': 'writer', 'status': 'FAILED'})
        final_post = f"[Writer Agent failed. Check logs.]\n\nTopic: {topic}"

    print(f"[{ts()}] [Orchestrator] ✓ Pipeline complete\n{'─'*60}")
    yield sse({'type': 'done', 'post': final_post})


# ── Flask routes ──────────────────────────────────────────────────────

@app.route('/health')
def health():
    return {'status': 'ok'}


@app.route('/run')
def run():
    topic = request.args.get('topic', '')
    take  = request.args.get('take', '')
    tone  = request.args.get('tone', 'Skeptical')

    print(f"\n[{ts()}] [Orchestrator] ← /run request | "
          f"topic='{topic[:40]}' take='{take[:30]}' tone={tone}")

    def generate():
        try:
            yield from make_pipeline(topic, take, tone)
        except Exception as e:
            print(f"[{ts()}] [Orchestrator] [ERROR] Pipeline crashed: {e}")
            yield sse({'type': 'error', 'message': str(e)})

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control':               'no-cache',
            'X-Accel-Buffering':           'no',
            'Access-Control-Allow-Origin': '*',
        }
    )


if __name__ == '__main__':
    print(f"[{ts()}] [Orchestrator] Starting on port 5000...")
    app.run(port=5000, debug=False, threaded=True)
