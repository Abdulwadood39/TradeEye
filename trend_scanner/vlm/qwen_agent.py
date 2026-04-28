"""
qwen_agent.py — Optional Qwen2.5-VL visual verification layer.

Sends a rendered chart image to a local Ollama Qwen2.5-VL model
for a plain-English second opinion on the detected trend.

Requires:
  - Ollama running locally
  - qwen2.5vl:7b model pulled (ollama pull qwen2.5vl:7b)
  - pip install ollama
"""
from __future__ import annotations

import base64
import json
import re
from typing import Optional, Tuple

from trend_scanner.config import CFG


# ─────────────────────────────────────────────────────────────────────────────
# STRUCTURED PROMPT — forces JSON output
# ─────────────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a professional financial chart analyst. You will be shown a candlestick \
chart with technical overlays. Respond ONLY with valid JSON. \
Do not add markdown code fences or extra text."""

_USER_PROMPT = """\
Analyze this candlestick chart carefully. Look at:
1. The overall price direction from left to right
2. The regression trendlines and channel lines
3. Whether the market is making higher highs and higher lows, or lower highs and lower lows

Respond with ONLY this exact JSON structure:
{
  "trend": "uptrend",
  "confidence": 0.85,
  "reasoning": "Price is making consistently higher highs and higher lows with a positive regression channel"
}

Where:
- "trend" must be exactly one of: "uptrend", "downtrend", "sideways"
- "confidence" is a float from 0.0 to 1.0
- "reasoning" is 1-2 sentences max

IMPORTANT: Return JSON only, no other text."""


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

def verify_chart(chart_path: str) -> Tuple[Optional[str], Optional[float], Optional[str]]:
    """
    Send a chart image to local Qwen2.5-VL and get trend verification.

    Parameters
    ----------
    chart_path : Absolute path to the chart PNG

    Returns
    -------
    (verdict, confidence, reasoning)
    - verdict    : 'uptrend' | 'downtrend' | 'sideways' | None (on failure)
    - confidence : float 0.0–1.0 | None
    - reasoning  : str | None
    """
    cfg = CFG.vlm
    if not cfg.enabled:
        return None, None, None

    try:
        import ollama
    except ImportError:
        print("  [WARN] VLM: ollama not installed. Run: pip install ollama")
        return None, None, None

    # Read + base64-encode the image
    try:
        with open(chart_path, "rb") as f:
            img_bytes = f.read()
        img_b64 = base64.b64encode(img_bytes).decode("utf-8")
    except Exception as e:
        print(f"  [WARN] VLM: Could not read chart image: {e}")
        return None, None, None

    # Call Ollama
    try:
        response = ollama.chat(
            model=cfg.model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": _USER_PROMPT,
                    "images": [img_b64],
                },
            ],
            options={"temperature": 0.1},   # low temp for consistent structured output
        )
    except Exception as e:
        print(f"  [WARN] VLM: Ollama call failed: {e}")
        print("         Is Ollama running? Try: ollama serve")
        print(f"         Is model available? Try: ollama pull {cfg.model}")
        return None, None, None

    # Parse JSON response
    raw_text = response.get("message", {}).get("content", "")
    return _parse_response(raw_text)


# ─────────────────────────────────────────────────────────────────────────────
# RESPONSE PARSER
# ─────────────────────────────────────────────────────────────────────────────

def _parse_response(text: str) -> Tuple[Optional[str], Optional[float], Optional[str]]:
    """
    Robustly extract JSON from the model's response.
    Handles cases where the model wraps JSON in markdown fences.
    """
    # Strip markdown fences if present
    stripped = re.sub(r"```(?:json)?", "", text).strip()

    # Try to find JSON block
    json_match = re.search(r"\{.*\}", stripped, re.DOTALL)
    if not json_match:
        print(f"  [WARN] VLM: No JSON found in response: {text[:200]}")
        return None, None, None

    try:
        data = json.loads(json_match.group(0))
    except json.JSONDecodeError as e:
        print(f"  [WARN] VLM: JSON parse error: {e}  raw={text[:200]}")
        return None, None, None

    trend = data.get("trend", "").lower().strip()
    if trend not in ("uptrend", "downtrend", "sideways"):
        trend = None

    conf_raw = data.get("confidence")
    try:
        confidence = float(conf_raw) if conf_raw is not None else None
    except (TypeError, ValueError):
        confidence = None

    reasoning = str(data.get("reasoning", "")).strip() or None

    return trend, confidence, reasoning


# ─────────────────────────────────────────────────────────────────────────────
# HELPER — check if model is available
# ─────────────────────────────────────────────────────────────----------------------------------------------------------------

def check_vlm_available(model: str = None) -> bool:
    """
    Return True if the Ollama VLM model is available locally.
    Useful for pre-flight checks before a scan run.
    """
    model = model or CFG.vlm.model
    try:
        import ollama
        models = ollama.list()
        names = [m.get("model", "") for m in models.get("models", [])]
        return any(model in n for n in names)
    except Exception:
        return False
