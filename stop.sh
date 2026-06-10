#!/bin/bash
echo "🛑 Stopping all PostSwarm agents..."
# Match only this project's agent scripts — not every python process with "agents/" in its path
pkill -f "agents/(web_agent|factchecker_agent|devils_advocate_agent|perspective_agent|hook_agent|writer_agent|research_agent|feed_agent|editor_agent|orchestrator)\.py" 2>/dev/null || true
echo "✅ All agents stopped"
