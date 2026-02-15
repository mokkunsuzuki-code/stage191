# MIT License © 2025 Motohiro Suzuki
"""
tests/test_attack_wrong_session_id.py

Stage178-B Attack A-03: wrong session_id injection

MiniCore contract:
- After handshake, any frame with session_id != established session_id
  must fail-closed (ProtocolViolation("session mismatch")).
"""

import pytest

from qsp.minicore import MiniCore, ProtocolViolation


def test_close_on_wrong_session_id_app_data():
    c = MiniCore()
    c.accept_frame({"type": "HANDSHAKE_DONE", "session_id": 1234, "epoch": 1, "payload": b""})

    with pytest.raises(ProtocolViolation) as e:
        c.accept_frame({"type": "APP_DATA", "session_id": 9999, "epoch": 1, "payload": b"hi"})

    assert "session mismatch" in str(e.value)


def test_close_on_wrong_session_id_rekey():
    c = MiniCore()
    c.accept_frame({"type": "HANDSHAKE_DONE", "session_id": 1234, "epoch": 1, "payload": b""})

    with pytest.raises(ProtocolViolation) as e:
        c.accept_frame({"type": "REKEY", "session_id": 9999, "epoch": 2, "payload": b"x"})

    assert "session mismatch" in str(e.value)
