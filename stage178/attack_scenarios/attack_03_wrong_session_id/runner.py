# MIT License © 2025 Motohiro Suzuki
"""
attack_scenarios/attack_03_wrong_session_id/runner.py

Stage178-B Attack A-03: wrong session_id injection

Demonstration:
- handshake with session_id=1234
- attacker sends APP_DATA with session_id=9999
Expected: fail-closed (ProtocolViolation("session mismatch"))

Exit code:
- 0 if rejected correctly
- 1 otherwise
"""

from qsp.minicore import MiniCore, ProtocolViolation


def main() -> int:
    c = MiniCore()
    c.accept_frame({"type": "HANDSHAKE_DONE", "session_id": 1234, "epoch": 1, "payload": b""})

    try:
        c.accept_frame({"type": "APP_DATA", "session_id": 9999, "epoch": 1, "payload": b"hi"})
    except ProtocolViolation as e:
        msg = str(e)
        if "session mismatch" in msg:
            print("[OK] wrong session rejected:", msg)
            return 0
        print("[FAIL] rejected, but unexpected reason:", msg)
        return 1

    print("[FAIL] wrong session accepted (should have been rejected)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
