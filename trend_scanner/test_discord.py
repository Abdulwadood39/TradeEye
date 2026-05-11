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
    print("\n--- 🧪 Testing Discord Alerts ---")
    
    # Force enable discord for the test
    CFG.notifications.discord.enabled = True
    
    # Sometimes CFG initialized before load_dotenv, let's refresh them just in case
    if not CFG.notifications.discord.webhook_url:
        CFG.notifications.discord.webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "")

    webhook_url = CFG.notifications.discord.webhook_url

    if not webhook_url:
        print("❌ Error: DISCORD_WEBHOOK_URL is missing!")
        print("Please check your .env file or export it as an environment variable.")
        return

    print("✅ Configuration loaded.")
    print(f"Webhook URL: {webhook_url[:20]}...{webhook_url[-10:] if len(webhook_url) > 30 else ''}\n")
    
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

    print("🚀 Dispatching test alert to Discord...")
    dispatch_trend_alert(mock_result)
    print("🏁 Test complete. Check your Discord channel!\n")

if __name__ == "__main__":
    main()
