import os
import sys

# Try to load .env file if python-dotenv is installed
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Ensure we can import from the root project directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from trend_scanner.config import CFG
from trend_scanner.engine.trend_engine import TrendResult
from trend_scanner.alerts.dispatcher import dispatch_trend_alert

def main():
    print("\n--- 🧪 Testing Telegram Alerts ---")
    
    # Force enable telegram for the test
    CFG.notifications.telegram.enabled = True
    
    # Sometimes CFG initialized before load_dotenv, let's refresh them just in case
    if not CFG.notifications.telegram.bot_token:
        CFG.notifications.telegram.bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not CFG.notifications.telegram.chat_id:
        CFG.notifications.telegram.chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    token = CFG.notifications.telegram.bot_token
    chat_id = CFG.notifications.telegram.chat_id

    if not token or not chat_id:
        print("❌ Error: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing!")
        print("Please check your .env file or export them as environment variables.")
        return

    print("✅ Configuration loaded.")
    print(f"Bot Token: {token[:10]}...{token[-4:] if len(token) > 15 else ''}")
    print(f"Chat ID:   {chat_id}\n")
    
    # Create a fake trend hit
    mock_result = TrendResult(
        ticker="TEST-ALERT",
        timeframe="1h",
        direction="up",
        score=5,
        confidence=0.99,
        candles_analyzed=1337,
        vlm_verdict="This is a test notification from your iTrade Scanner. Everything is working correctly!"
    )

    print("🚀 Dispatching test alert to Telegram...")
    dispatch_trend_alert(mock_result)
    print("🏁 Test complete. Check your Telegram app!\n")

if __name__ == "__main__":
    main()
