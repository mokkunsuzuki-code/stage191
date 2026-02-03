# MIT License © 2025 Motohiro Suzuki
"""
tests/test_attack_rekey_reuse.py

Stage178-B Attack A-05: rekey reuse / replay

Contract:
- A REKEY must only be accepted once per epoch transition (N -> N+1).
- Replaying/reusing a previous REKEY (same target epoch) must fail-closed.
"""

import pytest

from qsp.minicore import MiniCore, ProtocolViolation


def test_rekey_reuse_replay_is_rejected():
    c = MiniCore()
    c.accept_frame({"type": "HANDSHAKE_DONE", "session_id": 5050, "epoch": 1, "payload": b""})

    # first rekey to epoch=2 OK
    c.accept_frame({"type": "REKEY", "session_id": 5050, "epoch": 2, "payload": b"rekey_payload"})

    # replay/reuse same target epoch must fail
    with pytest.raises(ProtocolViolation) as e:
        c.accept_frame({"type": "REKEY", "session_id": 5050, "epoch": 2, "payload": b"rekey_payload"})

    assert "bad rekey epoch" in str(e.value)
