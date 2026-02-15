# MIT License © 2025 Motohiro Suzuki
"""
attack_scenarios/attack_02_rekey_race/runner.py

Stage178-B Attack A-02: rekey race (double rekey)

Exit code:
- 0 if second REKEY is rejected (safe)
- 1 if accepted or wrong rejection reason
"""

from qsp.minicore import MiniCore, ProtocolViolation


def main() -> int:
    c = MiniCore()
    c.accept_frame({"type": "HANDSHAKE_DONE", "session_id": 9001, "epoch": 1, "payload": b""})

    # first rekey OK
    c.accept_frame({"type": "REKEY", "session_id": 9001, "epoch": 2, "payload": b"r1"})

    try:
        # duplicate rekey to same epoch must fail
        c.accept_frame({"type": "REKEY", "session_id": 9001, "epoch": 2, "payload": b"r1-dup"})
    except ProtocolViolation as e:
        msg = str(e)
        if "bad rekey epoch" in msg:
            print("[OK] rekey race rejected:", msg)
            return 0
        print("[FAIL] rejected, but unexpected reason:", msg)
        return 1

    print("[FAIL] second rekey accepted (race not protected)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
