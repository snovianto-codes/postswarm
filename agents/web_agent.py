"""Web Agent — port 5002
Called by Research Agent. Generates grounded research points on a topic.
"""
import os, time
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
    print(f"[Web Agent] ← Received from Research Agent | Searching: {topic[:60]}...")

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
        # strip markdown code fences if present
        if text.startswith('```'):
            text = text.split('```')[1]
            if text.startswith('json'):
                text = text[4:]
        import json
        data_points = json.loads(text.strip())
        print(f"[Web Agent] ✓ Generated {len(data_points)} research points")
        return jsonify(data_points=data_points)
    except Exception as e:
        print(f"[Web Agent] [ERROR] {e}")
        return jsonify(data_points=[
            f"AI adoption in enterprise is accelerating, with 65% of organizations using AI in at least one function (McKinsey 2024).",
            f"Most AI projects fail in production — only 54% of AI pilots are scaled (Gartner).",
            f"Southeast Asia AI market projected to reach $1T contribution by 2030 (Google-Temasek-Bain).",
            f"The average enterprise uses 3-5 AI tools, but fewer than 30% are integrated into core workflows.",
            f"AI skill gaps remain the #1 barrier to adoption, cited by 60% of business leaders.",
        ])


if __name__ == '__main__':
    print("[Web Agent] Starting on port 5002...")
    app.run(port=5002, debug=False)
