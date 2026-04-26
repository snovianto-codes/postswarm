"""Research Agent — port 5001
Called by Orchestrator. Calls Web, Fact Checker, and Devil's Advocate in parallel.
"""
import os, json, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests as http
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

app = Flask(__name__)
CORS(app)

WEB_URL     = 'http://localhost:5002/run'
FACT_URL    = 'http://localhost:5003/run'
DEVIL_URL   = 'http://localhost:5004/run'
TIMEOUT     = 30


def call_web(topic):
    print(f"[Research Agent] → Calling Web Agent at {WEB_URL}")
    r = http.post(WEB_URL, json={'topic': topic}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json().get('data_points', [])


def call_fact_checker(topic, data_points):
    print(f"[Research Agent] → Calling Fact Checker at {FACT_URL}")
    r = http.post(FACT_URL, json={'topic': topic, 'data_points': data_points}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json().get('verified', data_points)


def call_devil(topic):
    print(f"[Research Agent] → Calling Devil's Advocate at {DEVIL_URL}")
    r = http.post(DEVIL_URL, json={'topic': topic}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json().get('counter_points', [])


@app.route('/health')
def health():
    return jsonify(status='ok')


@app.route('/run', methods=['POST'])
def run():
    data  = request.json or {}
    topic = data.get('topic', '')
    take  = data.get('take', '')
    tone  = data.get('tone', '')
    print(f"[Research Agent] ← Received | Orchestrating research for: {topic[:60]}...")

    # Step 1: call Web Agent first to get raw data
    data_points = []
    try:
        data_points = call_web(topic)
        print(f"[Research Agent] Web Agent returned {len(data_points)} points")
    except Exception as e:
        print(f"[Research Agent] [ERROR] Web Agent failed: {e}")

    # Step 2: call Fact Checker + Devil's Advocate in parallel
    verified      = data_points
    counter_points = []

    with ThreadPoolExecutor(max_workers=2) as ex:
        futures = {}
        if data_points:
            futures['fact'] = ex.submit(call_fact_checker, topic, data_points)
        futures['devil'] = ex.submit(call_devil, topic)

        for key, fut in futures.items():
            try:
                result = fut.result(timeout=TIMEOUT + 5)
                if key == 'fact':
                    verified = result
                    print(f"[Research Agent] Fact Checker returned {len(verified)} verified points")
                elif key == 'devil':
                    counter_points = result
                    print(f"[Research Agent] Devil's Advocate returned {len(counter_points)} counter-points")
            except Exception as e:
                print(f"[Research Agent] [ERROR] {key} agent failed: {e}")

    package = {
        'topic':          topic,
        'take':           take,
        'tone':           tone,
        'data_points':    data_points,
        'verified':       verified,
        'counter_points': counter_points,
    }
    print(f"[Research Agent] ✓ Research package assembled")
    return jsonify(package)


if __name__ == '__main__':
    print("[Research Agent] Starting on port 5001...")
    app.run(port=5001, debug=False)
