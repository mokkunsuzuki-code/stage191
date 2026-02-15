# MIT License © 2025 Motohiro Suzuki
"""
tests/test_attack_rekey_race.py

Stage178-B Attack A-02: rekey race (double rekey)

MiniCore contract:
- REKEY is only allowed when epoch == current_epoch + 1.
- If a duplicate REKEY for the same target epoch is attempted,
  it must fail-closed (ProtocolViolation).
"""

import pytest

from qsp.minicore import MiniCore, ProtocolViolation


def test_rekey_double_submit_fails_closed():
    c = MiniCore()

    # handshake -> epoch=1
    r = c.accept_frame({"type": "HANDSHAKE_DONE", "session_id": 9001, "epoch": 1, "payload": b""})
    assert r.ok is True
    assert r.epoch == 1
    fp1 = r.key_fingerprint_hex

    # first rekey to epoch=2 should succeed
    r2 = c.accept_frame({"type": "REKEY", "session_id": 9001, "epoch": 2, "payload": b"r1"})
    assert r2.ok is True
    assert r2.epoch == 2
    fp2 = r2.key_fingerprint_hex
    assert fp2 != fp1  # key must evolve across epochs

    # duplicate rekey to SAME epoch=2 must fail
    with pytest.raises(ProtocolViolation) as e:
        c.accept_frame({"type": "REKEY", "session_id": 9001, "epoch": 2, "payload": b"r1-dup"})

    assert "bad rekey epoch" in str(e.value)


def test_rekey_jump_is_rejected():
    c = MiniCore()
    c.accept_frame({"type": "HANDSHAKE_DONE", "session_id": 9002, "epoch": 1, "payload": b""})

    with pytest.raises(ProtocolViolation) as e:
        c.accept_frame({"type": "REKEY", "session_id": 9002, "epoch": 3, "payload": b"jump"})

    assert "bad rekey epoch" in str(e.value)
