# MIT License © 2025 Motohiro Suzuki
"""
attack_scenarios/attack_04_appdata_before_handshake/runner.py

Stage178-B Attack A-04: APP_DATA before handshake
"""

from qsp.minicore import MiniCore, ProtocolViolation


def main() -> int:
    c = MiniCore()
    try:
        c.accept_frame({"type": "APP_DATA", "session_id": 1, "epoch": 0, "payload": b"hello"})
    except ProtocolViolation as e:
        msg = str(e)
        if "before handshake" in msg:
            print("[OK] appdata-before-handshake rejected:", msg)
            return 0
        print("[FAIL] rejected, but unexpected reason:", msg)
        return 1

    print("[FAIL] APP_DATA accepted before handshake")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
