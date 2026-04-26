"""Hook Agent — port 5006
Called by Orchestrator. Generates 5 punchy LinkedIn openers.
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
    take = data.get('take', '')
    print(f"[Hook Agent] ← Received | Writing hooks for: {topic[:50]}...")

    prompt = f"""You are writing LinkedIn hooks for a senior leader in Singapore.

Topic: {topic}
Their take: {take if take else "Be direct and practical"}

Generate exactly 5 punchy LinkedIn opening lines (hooks).

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
        response = _client.models.generate_content(model=MODEL, contents=prompt)
        text = response.text.strip()
        if text.startswith('```'):
            text = text.split('```')[1]
            if text.startswith('json'):
                text = text[4:]
        hooks = json.loads(text.strip())
        # ensure we have exactly 5
        hooks = hooks[:5] if len(hooks) >= 5 else hooks
        print(f"[Hook Agent] ✓ Generated {len(hooks)} hooks")
        return jsonify(hooks=hooks)
    except Exception as e:
        print(f"[Hook Agent] [ERROR] {e}")
        return jsonify(hooks=[
            "300 AI sub-agents. Most teams can't handle 3.",
            "Impressive demo. Disaster at 3am on a Tuesday.",
            "The benchmark looks great. Your team isn't ready.",
            "Everyone's talking about the launch. Nobody's asking who maintains it.",
            "New AI model dropped. Your governance hasn't caught up.",
        ])


if __name__ == '__main__':
    print("[Hook Agent] Starting on port 5006...")
    app.run(port=5006, debug=False)
