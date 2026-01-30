# MIT License © 2025 Motohiro Suzuki
from __future__ import annotations

import asyncio
import os

from protocol.config import ProtocolConfig
from crypto.algorithms import AlgorithmSuite
from transport.io_async import open_client

from protocol.handshake import client_handshake
from protocol.rekey import (
    decode_rekey_plaintext,
    encode_rekey_ack,
    RekeyInit,
    confirm_material,
)

HOST = "127.0.0.1"
PORT = 9000


def make_config() -> ProtocolConfig:
    suite = AlgorithmSuite(
        supported_sigs=["ed25519"],
        supported_kems=["toy_kem"],
        supported_aeads=["aes-gcm"],
    )
    return ProtocolConfig(
        suite=suite,
        sig_alg="ed25519",
        kem_alg="toy_kem",
        key_len=32,
        enable_qkd=True,
        qkd_seed=1234,
    )


def _attack04_session_id(base_session_id: int) -> int:
    if os.getenv("QSP_ATTACK04_WRONG_SESSION_ID", "") == "1":
        return int(base_session_id) + 1
    return int(base_session_id)


def _attack01_maybe_tamper_confirm(confirm: bytes) -> bytes:
    """
    Attack-01:
      If QSP_STAGE167A_FAIL=1, tamper ACK confirm so server rejects (fail-closed).
    """
    if os.getenv("QSP_STAGE167A_FAIL", "") == "1":
        b = bytearray(confirm)
        if len(b) > 0:
            b[0] ^= 0x01
        else:
            b.extend(b"\x01")
        return bytes(b)
    return confirm


async def main() -> None:
    cfg = make_config()

    io = await open_client(HOST, PORT)
    try:
        r = await client_handshake(io, cfg)
        hr = r.value if hasattr(r, "ok") and r.ok else r

        session_id = int(hr.session_id)
        epoch = int(hr.epoch)

        f = await io.recv_rekey()
        msg = decode_rekey_plaintext(f.payload)
        if not isinstance(msg, RekeyInit):
            raise RuntimeError("expected RekeyInit")

        c = confirm_material(msg.material, bytes(msg.qkd_bytes))
        c = _attack01_maybe_tamper_confirm(c)
        ack_pt = encode_rekey_ack(new_epoch=msg.new_epoch, confirm=c)

        ack_session_id = _attack04_session_id(session_id)

        await io.send_rekey(
            session_id=ack_session_id,
            epoch=epoch,
            seq=1,
            payload=ack_pt,
            flags=0,
        )

        committed_epoch = int(msg.new_epoch)

        if os.getenv("QSP_ATTACK02_REPLAY_ACK", "") == "1":
            await asyncio.sleep(0.10)
            await io.send_rekey(
                session_id=ack_session_id,
                epoch=committed_epoch,
                seq=99,
                payload=ack_pt,
                flags=0,
            )
        return
    finally:
        await io.close()


if __name__ == "__main__":
    asyncio.run(main())
