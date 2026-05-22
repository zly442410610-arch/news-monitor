#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================"
echo "  Aerospace News Monitor - Setup"
echo "========================================"

# 1. Install Python dependencies
echo ""
echo "[1/4] Installing Python dependencies..."
pip3 install --quiet -r requirements.txt 2>&1 | tail -1
echo "  Done."

# 2. Create data directories
echo ""
echo "[2/4] Creating data directories..."
mkdir -p data snapshots
echo "  Done."

# 3. Configure Telegram (optional)
echo ""
echo "[3/4] Notification setup (optional)"
echo "  To enable Telegram notifications, set environment variables:"
echo "    export TG_BOT_TOKEN=your_bot_token"
echo "    export TG_CHAT_ID=your_chat_id"
echo ""
echo "  Or add them to /etc/environment or ~/.bashrc for persistence."
echo ""

# 4. Setup cron job
echo "[4/4] Setting up cron job..."
# Log rotation: keep last 10MB by rotating at ~5MB
CRON_TRUNCATE="0 3 * * 0 truncate -s 0 $SCRIPT_DIR/data/cron.log 2>/dev/null || true"
CRON_POLL="*/30 * * * * cd $SCRIPT_DIR && python3 main.py poll >> data/cron.log 2>&1"
CRON_PATENT="27 */2 * * * cd $SCRIPT_DIR && python3 main.py patent >> data/cron.log 2>&1"
(crontab -l 2>/dev/null | grep -v "news-monitor" ; echo "$CRON_TRUNCATE" ; echo "$CRON_POLL" ; echo "$CRON_PATENT") | crontab -
echo "  Cron jobs added (poll every 30min, patents every 2h, log truncated weekly)."

echo ""
echo "========================================"
echo "  Setup complete!"
echo ""
echo "  Quick start:"
echo "    python3 main.py poll     # Run one poll cycle"
echo "    python3 main.py serve    # Start web dashboard on :8080"
echo "    python3 main.py daemon   # Continuous polling mode"
echo "    python3 main.py stats    # View statistics"
echo ""
echo "  Web dashboard: http://$(hostname -I 2>/dev/null | awk '{print $1}'):8080"
echo "========================================"
