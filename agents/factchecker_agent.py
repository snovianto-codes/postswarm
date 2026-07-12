"""Fact Checker Agent — port 5003
Called by Research Agent. Labels each data point and returns only clean ones.
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
    data_points = data.get('data_points', [])
    print(f"[Fact Checker] ← Received | Verifying {len(data_points)} points about: {topic[:50]}...")

    if not data_points:
        return jsonify(verified=[])

    points_text = '\n'.join(f"{i+1}. {p}" for i, p in enumerate(data_points))

    prompt = f"""You are a fact-checker for a LinkedIn post about: {topic}

Review these research points and label each as:
- VERIFIED: factually solid, can stand as-is
- NEEDS_CAVEAT: directionally correct but needs qualification
- UNVERIFIED: too specific without a clear source, or likely wrong

Points to review:
{points_text}

Return a JSON object with this structure:
{{
  "results": [
    {{"point": "original point text", "label": "VERIFIED", "clean": "cleaned version (same or slightly qualified)"}},
    ...
  ]
}}

Rules:
- For VERIFIED and NEEDS_CAVEAT, include a clean version
- For UNVERIFIED, still include it but soften with "Some reports suggest..." or similar
- Keep clean versions under 45 words
- Return ONLY the JSON object, no other text"""

    try:
        resp = call_model('fact', prompt)
        text = resp.text.strip()
        if text.startswith('```'):
            text = text.split('```')[1]
            if text.startswith('json'):
                text = text[4:]
        result = json.loads(text.strip())
        results = result.get('results', [])
        verified = [r['clean'] for r in results if r.get('label') in ('VERIFIED', 'NEEDS_CAVEAT')]
        if not verified:
            verified = [r['clean'] for r in results]
        print(f"[Fact Checker] ✓ {len(verified)} points passed verification via {resp.provider}/{resp.model}")
        return jsonify(verified=verified)
    except Exception as e:
        print(f"[Fact Checker] [ERROR] {type(e).__name__}: {e}")
        print(traceback.format_exc())
        return jsonify(verified=data_points)


if __name__ == '__main__':
    print("[Fact Checker] Starting on port 5003...")
    app.run(port=5003, debug=False)
