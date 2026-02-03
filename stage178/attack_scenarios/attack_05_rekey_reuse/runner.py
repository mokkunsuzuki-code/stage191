# MIT License © 2025 Motohiro Suzuki
"""
attack_scenarios/attack_05_rekey_reuse/runner.py

Stage178-B Attack A-05: rekey reuse / replay
"""

from qsp.minicore import MiniCore, ProtocolViolation


def main() -> int:
    c = MiniCore()
    c.accept_frame({"type": "HANDSHAKE_DONE", "session_id": 5050, "epoch": 1, "payload": b""})

    c.accept_frame({"type": "REKEY", "session_id": 5050, "epoch": 2, "payload": b"rekey_payload"})

    try:
        c.accept_frame({"type": "REKEY", "session_id": 5050, "epoch": 2, "payload": b"rekey_payload"})
    except ProtocolViolation as e:
        msg = str(e)
        if "bad rekey epoch" in msg:
            print("[OK] rekey reuse rejected:", msg)
            return 0
        print("[FAIL] rejected, but unexpected reason:", msg)
        return 1

    print("[FAIL] rekey reuse accepted (should have been rejected)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
