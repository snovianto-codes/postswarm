"""Writer Agent — port 5007
Called by Orchestrator. Assembles the final LinkedIn post using VOICE.md.
"""
import os, json
from pathlib import Path
from flask import Flask, request, jsonify
from flask_cors import CORS
from google import genai
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
_client = genai.Client(api_key=os.environ['GEMINI_API_KEY'])

app = Flask(__name__)
CORS(app)

VOICE_PATH = Path(__file__).parent.parent / 'VOICE.md'
PRIMARY_MODEL   = 'gemini-2.5-pro'
FALLBACK_MODEL  = 'gemini-2.5-flash'


def load_voice():
    try:
        return VOICE_PATH.read_text()
    except Exception:
        return "Direct, no fluff, short sentences. Max 200 words. End with a sharp question."


@app.route('/health')
def health():
    return jsonify(status='ok')


@app.route('/run', methods=['POST'])
def run():
    data = request.json or {}
    topic    = data.get('topic', '')
    take     = data.get('take', '')
    tone     = data.get('tone', 'Skeptical')
    research = data.get('research', {})
    hooks    = data.get('hooks', [])
    insights = data.get('insights', [])
    print(f"[Writer Agent] ← Received | Writing post for: {topic[:50]}...")

    voice = load_voice()
    verified   = research.get('verified', [])
    counters   = research.get('counter_points', [])
    source_url = research.get('source_url')

    verified_text  = '\n'.join(f"- {p}" for p in verified[:3])   if verified  else "No verified data."
    counters_text  = '\n'.join(f"- {p}" for p in counters[:2])   if counters  else "None."
    insights_text  = '\n'.join(f"- {p}" for p in insights[:2])   if insights  else "None."
    hooks_text     = '\n'.join(f"{i+1}. {h}" for i, h in enumerate(hooks[:5])) if hooks else "No hooks provided."
    source_note    = f"\nSource article: {source_url}\nUse findings from this article as the basis for the post — make it clear the post is a reaction to this specific article." if source_url else ""

    prompt = f"""You are ghostwriting a LinkedIn post for the author described in this voice profile:

---VOICE PROFILE---
{voice}
---END VOICE---

## Assignment
Topic: {topic}
Author's take: {take if take else "Be direct and honest"}
Tone: {tone}{source_note}

## Research to use
Verified facts:
{verified_text}

Counter-arguments (use 1 for balance):
{counters_text}

SEA/team insights (weave in naturally):
{insights_text}

## Hook options (pick the best one):
{hooks_text}

## Output structure
1. Best hook from the list above (pick the most arresting one for the tone)
2. 1-2 sentences of context
3. The author's real take, supported by 1-2 specific data points
4. 1 honest counter-point or friction (balanced view)
5. 1 Southeast Asia / team management angle
6. Sharp closing question (direct, invites real answers)
7. 4 relevant hashtags on the last line

## Hard rules
- Max 200 words total (count carefully)
- Short sentences throughout. No padding.
- No "In conclusion", "It's worth noting", "Game-changing", "Revolutionary", "Dive into", "Delve", "Groundbreaking"
- No excessive exclamation marks
- Use → for any lists
- One blank line between paragraphs
- Sound like a real senior leader, not a thought leader performing online

Return ONLY the post text. No preamble, no explanation."""

    for model_name in (PRIMARY_MODEL, FALLBACK_MODEL):
        try:
            response = _client.models.generate_content(model=model_name, contents=prompt)
            post = response.text.strip()
            print(f"[Writer Agent] ✓ Post written ({len(post.split())} words) using {model_name}")
            return jsonify(post=post)
        except Exception as e:
            print(f"[Writer Agent] [ERROR] {model_name} failed: {e}")
            if model_name == FALLBACK_MODEL:
                fallback_post = f"""{hooks[0] if hooks else topic}

{take if take else 'The technology is impressive. But most teams aren\'t ready.'}

{verified[0] if verified else 'AI adoption gaps remain the biggest barrier to real ROI.'}

{counters[0] if counters else 'The hard truth: buying the tool is easy. Changing how people work is not.'}

In Singapore and across SEA, I see this pattern repeat: pilot succeeds, scale fails.

What's your team actually doing to close the gap?

#AI #Leadership #SEA #FutureOfWork"""
                return jsonify(post=fallback_post)


if __name__ == '__main__':
    print("[Writer Agent] Starting on port 5007...")
    app.run(port=5007, debug=False)
