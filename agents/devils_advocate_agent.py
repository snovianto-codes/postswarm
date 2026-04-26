"""Devil's Advocate Agent — port 5004
Called by Research Agent. Generates sharp counter-arguments.
"""
import os, json
from flask import Flask, request, jsonify
from flask_cors import CORS
from google import genai
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
_client = genai.Client(api_key=os.environ['GEMINI_API_KEY'])

app = Flask(__name__)
CORS(app)

MODEL = 'gemini-2.5-flash'


@app.route('/health')
def health():
    return jsonify(status='ok')


@app.route('/run', methods=['POST'])
def run():
    data = request.json or {}
    topic = data.get('topic', '')
    print(f"[Devil's Advocate] ← Received | Arguing against: {topic[:60]}...")

    prompt = f"""You are a sharp devil's advocate for a LinkedIn post about: {topic}

Generate 2-3 strong counter-arguments that a skeptic or critic would make.

Requirements:
- Be specific and credible, not just cynical
- Each point should challenge the hype or assumptions around this topic
- Focus on practical failures, overlooked risks, or inconvenient truths
- Keep each under 35 words
- Make them useful for a balanced, honest post — not FUD

Return as a JSON array of strings:
["counter-argument 1", "counter-argument 2", "counter-argument 3"]

Return ONLY the JSON array, no other text."""

    try:
        response = _client.models.generate_content(model=MODEL, contents=prompt)
        text = response.text.strip()
        if text.startswith('```'):
            text = text.split('```')[1]
            if text.startswith('json'):
                text = text[4:]
        counter_points = json.loads(text.strip())
        print(f"[Devil's Advocate] ✓ Generated {len(counter_points)} counter-arguments")
        return jsonify(counter_points=counter_points)
    except Exception as e:
        print(f"[Devil's Advocate] [ERROR] {e}")
        return jsonify(counter_points=[
            "Most teams lack the observability tools to debug multi-agent failures before they hit production.",
            "Benchmarks measure capability, not reliability — enterprise teams need the latter far more.",
            "The coordination overhead of sub-agent systems often negates the speed gains they promise.",
        ])


if __name__ == '__main__':
    print("[Devil's Advocate] Starting on port 5004...")
    app.run(port=5004, debug=False)
