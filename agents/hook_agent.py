"""Hook Agent — port 5006
Called by Orchestrator. Generates 5 punchy LinkedIn openers.
"""
import sys, json, traceback
from pathlib import Path
from flask import Flask, request, jsonify
from flask_cors import CORS

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.model_client import call_model

app = Flask(__name__)
CORS(app, resources={r"/run": {"origins": ["http://localhost:5001","http://127.0.0.1:5001","http://localhost:8080","http://127.0.0.1:8080"]}, r"/health": {"origins": "*"}})


@app.route('/health')
def health():
    return jsonify(status='ok')


@app.route('/run', methods=['POST'])
def run():
    data = request.json or {}
    topic = data.get('topic', '')
    take  = data.get('take', '')
    role  = data.get('role', 'People Manager')
    print(f"[Hook Agent] ← Received | Writing hooks for: {topic[:50]}...")

    prompt = f"""You are writing LinkedIn hooks for a {role} based in Singapore.

Topic: {topic}
Their take: {take if take else "Be direct and practical"}

Generate exactly 5 punchy LinkedIn opening lines (hooks) that resonate specifically with a {role} audience.

Rules:
- Each hook must be under 15 words
- Use varied approaches: contrast, bold statement, question, number, counter-intuition
- No fluff, no emojis, no hashtags
- Must make someone stop scrolling
- Direct voice — like a real person, not a marketer
- Do NOT use: "Game-changing", "Revolutionary", "Dive into", "Groundbreaking"

Return as a JSON array of 5 strings:
["hook 1", "hook 2", "hook 3", "hook 4", "hook 5"]

Return ONLY the JSON array, no other text."""

    try:
        resp = call_model('hook', prompt)
        text = resp.text.strip()
        if text.startswith('```'):
            text = text.split('```')[1]
            if text.startswith('json'):
                text = text[4:]
        hooks = json.loads(text.strip())
        # ensure we have exactly 5
        hooks = hooks[:5] if len(hooks) >= 5 else hooks
        print(f"[Hook Agent] ✓ Generated {len(hooks)} hooks via {resp.provider}/{resp.model}")
        return jsonify(hooks=hooks)
    except Exception as e:
        print(f"[Hook Agent] [ERROR] {type(e).__name__}: {e}")
        print(traceback.format_exc())
        return jsonify(hooks=[])


if __name__ == '__main__':
    print("[Hook Agent] Starting on port 5006...")
    app.run(port=5006, debug=False)
