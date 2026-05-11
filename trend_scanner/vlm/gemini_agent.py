"""
gemini_agent.py — Google Gemini visual verification layer.

Sends a rendered chart PNG to Google Gemini (gemini-1.5-flash, free tier)
for a second-opinion trend classification.

Requires:
  - pip install google-generativeai
  - GEMINI_API_KEY set in .env (free at https://aistudio.google.com/app/apikey)
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

from trend_scanner.config import CFG


# ─────────────────────────────────────────────────────────────────────────────
# STRUCTURED PROMPT
# ─────────────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a professional financial chart analyst. You will be shown a candlestick \
chart with technical overlays (regression trendline, pivot channel, signal scorecard). \
Respond ONLY with valid JSON. Do not add markdown code fences or extra text."""

_USER_PROMPT = """\
Analyze this candlestick chart carefully. Examine:
1. The overall price direction from left to right
2. The regression trendline and pivot channel slope
3. Whether the market makes higher highs + higher lows (uptrend) or lower highs + lower lows (downtrend)
4. Whether there is clear directional momentum or mostly sideways/choppy movement

Respond with ONLY this

trend: ENUM(UPTREND, DOWNTREND, SIDEWAYS)

IMPORTANT: Return JSON only, no other text."""


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

def verify_chart(chart_path: str) -> Tuple[Optional[str], Optional[float], Optional[str]]:
    """
    Send a chart image to Google Gemini and get a trend verification.

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
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        logger.warning("  [WARN] VLM: GEMINI_API_KEY not set. Skipping visual verification.")
        return None, None, None

    try:
        import google.generativeai as genai
    except ImportError:
        logger.warning("  [WARN] VLM: google-generativeai not installed. Run: pip install google-generativeai")
        return None, None, None

    # Read the chart image
    try:
        with open(chart_path, "rb") as f:
            img_bytes = f.read()
    except Exception as e:
        logger.warning(f"  [WARN] VLM: Could not read chart image: {e}")
        return None, None, None

    # Configure Gemini client
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name=CFG.vlm.model)
        image_part = {"mime_type": "image/png", "data": img_bytes}
        # Prepend system context directly in the user message for compatibility
        full_prompt = f"{_SYSTEM_PROMPT}\n\n{_USER_PROMPT}"
        response = model.generate_content(
            [full_prompt, image_part],
            generation_config={"temperature": 0.1, "max_output_tokens": 256},
        )
        raw_text = response.text
    except Exception as e:
        logger.warning(f"  [WARN] VLM: Gemini API call failed: {e}")
        return None, None, None

    return _parse_response(raw_text)


# ─────────────────────────────────────────────────────────────────────────────
# AVAILABILITY CHECK
# ─────────────────────────────────────────────────────────────────────────────

def check_vlm_available() -> bool:
    """
    Return True if the Gemini API key is set and google-generativeai is installed.
    """
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        return False
    try:
        import google.generativeai  # noqa: F401
        return True
    except ImportError:
        return False


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
        logger.warning(f"  [WARN] VLM: No JSON found in response: {text[:200]}")
        return None, None, None

    try:
        data = json.loads(json_match.group(0))
    except json.JSONDecodeError as e:
        logger.warning(f"  [WARN] VLM: JSON parse error: {e}  raw={text[:200]}")
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
