"""Perspective Agent — port 5005
Called by Orchestrator. Generates SEA/business-leader insights.
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
    topic    = data.get('topic', '')
    research = data.get('research', {})
    role     = data.get('role', 'People Manager')
    print(f"[Perspective Agent] ← Received | Analyzing for SEA context ({role}): {topic[:50]}...")

    verified_points = research.get('verified', [])
    research_summary = '\n'.join(f"- {p}" for p in verified_points[:3]) if verified_points else "No research provided."

    prompt = f"""You are a {role} and AI adoption leader based in Singapore, working across Southeast Asia.

Topic: {topic}

Research context:
{research_summary}

Generate 2-3 practical insights specifically for a {role} in Southeast Asia who is:
- Navigating AI adoption from the perspective of a {role}
- Dealing with real adoption friction (not just buying tools)
- Accountable for productivity and growth outcomes
- Working in a mixed-seniority team with varying AI literacy

Requirements:
- Make insights specific to SEA context (talent market, team dynamics, regulatory environment)
- Focus on what actually happens when you try to implement this, not the theory
- Be honest about what works and what doesn't
- Keep each insight under 40 words
- No corporate speak

Return as a JSON array of strings:
["insight 1", "insight 2", "insight 3"]

Return ONLY the JSON array, no other text."""

    try:
        resp = call_model('perspective', prompt)
        text = resp.text.strip()
        if text.startswith('```'):
            text = text.split('```')[1]
            if text.startswith('json'):
                text = text[4:]
        insights = json.loads(text.strip())
        print(f"[Perspective Agent] ✓ Generated {len(insights)} SEA insights via {resp.provider}/{resp.model}")
        return jsonify(insights=insights)
    except Exception as e:
        print(f"[Perspective Agent] [ERROR] {type(e).__name__}: {e}")
        print(traceback.format_exc())
        return jsonify(insights=[])


if __name__ == '__main__':
    print("[Perspective Agent] Starting on port 5005...")
    app.run(port=5005, debug=False)
