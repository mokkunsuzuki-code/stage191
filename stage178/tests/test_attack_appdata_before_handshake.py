# MIT License © 2025 Motohiro Suzuki
"""
tests/test_attack_appdata_before_handshake.py

Stage178-B Attack A-04: APP_DATA before handshake

MiniCore contract:
- Before handshake completion, any APP_DATA must fail-closed
  (ProtocolViolation("before handshake")).
"""

import pytest

from qsp.minicore import MiniCore, ProtocolViolation


def test_reject_app_data_before_handshake_dict_style():
    c = MiniCore()

    with pytest.raises(ProtocolViolation) as e:
        c.accept_frame({"type": "APP_DATA", "session_id": 1, "epoch": 0, "payload": b"hello"})

    assert "before handshake" in str(e.value)


def test_reject_app_data_before_handshake_old_style():
    c = MiniCore()

    with pytest.raises(ProtocolViolation) as e:
        c.accept_frame("APP_DATA", b"hello", claimed_session_id=1, claimed_epoch=0)

    assert "before handshake" in str(e.value)
