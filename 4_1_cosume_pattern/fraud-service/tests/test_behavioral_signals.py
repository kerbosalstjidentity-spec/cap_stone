"""Tests for Layer 1: Behavioral Signals Analysis."""
from app.services.behavioral_signals import analyze_signals


class TestAnalyzeSignals:
    def test_none_signals(self):
        result = analyze_signals(None)
        assert result.risk_score == 0.0
        assert result.flags == []

    def test_empty_signals(self):
        result = analyze_signals({})
        assert result.risk_score == 0.0

    def test_bot_mouse_pattern(self):
        signals = {
            "behavioral_biometrics": {"mouse_speed_variance": 0.001},
        }
        result = analyze_signals(signals)
        assert "BOT_MOUSE_PATTERN" in result.flags
        assert result.risk_score > 0

    def test_fast_form_fill(self):
        signals = {
            "behavioral_biometrics": {"form_fill_duration_ms": 1500},
        }
        result = analyze_signals(signals)
        assert "FAST_FORM_FILL" in result.flags
        assert result.risk_score >= 0.4

    def test_tor_detected(self):
        signals = {
            "network_context": {"is_tor": True},
        }
        result = analyze_signals(signals)
        assert "TOR_DETECTED" in result.flags
        assert result.risk_score >= 0.5

    def test_vpn_detected(self):
        signals = {
            "network_context": {"is_vpn": True},
        }
        result = analyze_signals(signals)
        assert "VPN_DETECTED" in result.flags
        assert result.risk_score >= 0.2

    def test_multiple_flags(self):
        signals = {
            "behavioral_biometrics": {
                "mouse_speed_variance": 0.001,
                "form_fill_duration_ms": 1000,
                "clipboard_paste_count": 5,
            },
            "network_context": {"is_tor": True},
        }
        result = analyze_signals(signals)
        assert len(result.flags) >= 3
        assert result.risk_score == 1.0  # capped

    def test_normal_user(self):
        signals = {
            "behavioral_biometrics": {
                "mouse_speed_variance": 5.2,
                "form_fill_duration_ms": 15000,
                "clipboard_paste_count": 0,
            },
            "session_context": {
                "tab_focus_changes": 2,
                "page_dwell_time_ms": 30000,
            },
            "network_context": {
                "is_vpn": False,
                "is_tor": False,
                "is_proxy": False,
            },
        }
        result = analyze_signals(signals)
        assert result.risk_score == 0.0
        assert result.flags == []

    def test_excessive_paste(self):
        signals = {
            "behavioral_biometrics": {"clipboard_paste_count": 5},
        }
        result = analyze_signals(signals)
        assert "EXCESSIVE_PASTE" in result.flags

    def test_short_dwell(self):
        signals = {
            "session_context": {"page_dwell_time_ms": 800},
        }
        result = analyze_signals(signals)
        assert "VERY_SHORT_DWELL" in result.flags

    def test_high_tab_switching(self):
        signals = {
            "session_context": {"tab_focus_changes": 15},
        }
        result = analyze_signals(signals)
        assert "HIGH_TAB_SWITCHING" in result.flags
