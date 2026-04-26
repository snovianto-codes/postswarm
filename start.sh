#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "📦 Installing dependencies..."
pip install -r requirements.txt -q

echo "🚀 Starting PostSwarm agents..."

python agents/web_agent.py &
sleep 1
python agents/factchecker_agent.py &
sleep 1
python agents/devils_advocate_agent.py &
sleep 1
python agents/perspective_agent.py &
sleep 1
python agents/hook_agent.py &
sleep 1
python agents/writer_agent.py &
sleep 1
python agents/research_agent.py &
sleep 2

echo ""
echo "✅ All agents ready"
echo "   Web Agent        → http://localhost:5002"
echo "   Fact Checker     → http://localhost:5003"
echo "   Devil's Advocate → http://localhost:5004"
echo "   Perspective      → http://localhost:5005"
echo "   Hook Agent       → http://localhost:5006"
echo "   Writer Agent     → http://localhost:5007"
echo "   Research Agent   → http://localhost:5001"
echo ""
echo "🌐 Starting Orchestrator on http://localhost:5000"
echo ""

echo "✅ Open your browser at: http://localhost:8080"
echo ""

python agents/orchestrator.py
