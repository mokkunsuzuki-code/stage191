# MIT License © 2025 Motohiro Suzuki
from __future__ import annotations

import asyncio
import os

from protocol.config import ProtocolConfig
from crypto.algorithms import AlgorithmSuite
from transport.io_async import AsyncFrameIO, open_client

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
    """
    Stage176 Attack-04:
      If QSP_ATTACK04_WRONG_SESSION_ID=1, send ACK with a wrong session_id.
    """
    if os.getenv("QSP_ATTACK04_WRONG_SESSION_ID", "") == "1":
        # deterministic wrong id (simple +1)
        return int(base_session_id) + 1
    return int(base_session_id)


async def main() -> None:
    cfg = make_config()

    io = await open_client(HOST, PORT)
    try:
        r = await client_handshake(io, cfg)
        hr = r.value if hasattr(r, "ok") and r.ok else r

        session_id = int(hr.session_id)
        epoch = int(hr.epoch)

        # Wait REKEY_INIT
        f = await io.recv_rekey()
        msg = decode_rekey_plaintext(f.payload)
        if not isinstance(msg, RekeyInit):
            raise RuntimeError("expected RekeyInit")

        # Build ACK
        c = confirm_material(msg.material, bytes(msg.qkd_bytes))
        ack_pt = encode_rekey_ack(new_epoch=msg.new_epoch, confirm=c)

        # Attack-04: wrong session_id on ACK
        ack_session_id = _attack04_session_id(session_id)

        await io.send_rekey(
            session_id=ack_session_id,
            epoch=epoch,
            seq=1,
            payload=ack_pt,
            flags=0,
        )

        committed_epoch = int(msg.new_epoch)

        # Attack-02: replay ACK after commit (server should detect)
        if os.getenv("QSP_ATTACK02_REPLAY_ACK", "") == "1":
            await asyncio.sleep(0.10)
            await io.send_rekey(
                session_id=ack_session_id,
                epoch=committed_epoch,
                seq=99,
                payload=ack_pt,
                flags=0,
            )

        # Attack-03 is handled by a separate runner in this repo.
        return
    finally:
        await io.close()


if __name__ == "__main__":
    asyncio.run(main())
