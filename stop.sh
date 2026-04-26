#!/bin/bash
echo "🛑 Stopping all PostSwarm agents..."
pkill -f "python agents/" 2>/dev/null || true
echo "✅ All agents stopped"
