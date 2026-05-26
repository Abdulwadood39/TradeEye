"""
config/vetoes.py — Veto gate thresholds.

Veto gates run AFTER the 5 signals score a trend.
A single failed veto cancels the alert, killing false positives.

Set `enabled = False` to bypass all vetos (useful for debugging).
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class VetoConfig:
    # ── Master switch ──────────────────────────────────────────────────────────
    # False = all veto gates are disabled. Useful when debugging signals.
    enabled: bool = True

    # ── R² Linearity (full window) ─────────────────────────────────────────────
    # Measures how closely the full price series follows a straight line.
    # Range 0–1. Higher = stricter (more linear trend required).
    min_r2: float = 0.75

    # ── Rolling R² (recent candles only) ──────────────────────────────────────
    # Same as min_r2 but applied only to the most recent `rolling_r2_window`
    # candles. Catches assets that were trending but have recently broken down.
    rolling_r2_window: int = 100
    rolling_r2_min: float = 0.65

    # ── ATR Efficiency ────────────────────────────────────────────────────────
    # net_move / (ATR × candles). Filters sideways chop where candles cancel.
    atr_efficiency: float = 0.035

    # ── Kaufman Efficiency Ratio ──────────────────────────────────────────────
    # |net_move| / Σ|bar_moves|
    # ER ≈ 1.0 = straight-line trend.  ER ≈ 0.0 = random walk / zigzag.
    kaufman_er_min: float = 0.10

    # ── Body Ratio ────────────────────────────────────────────────────────────
    # Median candle body / candle range across recent candles.
    # Low values = mostly doji / spinning tops = indecisive / sideways market.
    body_ratio: float = 0.35

    # ── EMA Alignment ─────────────────────────────────────────────────────────
    # Price must be above both EMAs for uptrend, below both for downtrend.
    ema_fast: int = 50
    ema_slow: int = 200
