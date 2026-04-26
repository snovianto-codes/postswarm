#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "📦 Installing dependencies..."
pip install -r requirements.txt -q

mkdir -p logs

echo "🚀 Starting PostSwarm agents..."

python -u agents/web_agent.py        > logs/web.log        2>&1 &
sleep 1
python -u agents/factchecker_agent.py > logs/fact.log       2>&1 &
sleep 1
python -u agents/devils_advocate_agent.py > logs/devil.log  2>&1 &
sleep 1
python -u agents/perspective_agent.py > logs/perspective.log 2>&1 &
sleep 1
python -u agents/hook_agent.py       > logs/hook.log        2>&1 &
sleep 1
python -u agents/writer_agent.py     > logs/writer.log      2>&1 &
sleep 1
python -u agents/research_agent.py   > logs/research.log    2>&1 &
sleep 2

echo ""
echo "✅ All agents ready  (logs → logs/*.log)"
echo "   Web Agent        → http://localhost:5002"
echo "   Fact Checker     → http://localhost:5003"
echo "   Devil's Advocate → http://localhost:5004"
echo "   Perspective      → http://localhost:5005"
echo "   Hook Agent       → http://localhost:5006"
echo "   Writer Agent     → http://localhost:5007"
echo "   Research Agent   → http://localhost:5001"
echo ""
echo "🌐 Starting Orchestrator on http://localhost:8080"
echo "   Orchestrator log → logs/orchestrator.log"
echo ""

echo "✅ Open your browser at: http://localhost:8080"
echo ""

python -u agents/orchestrator.py 2>&1 | tee logs/orchestrator.log
