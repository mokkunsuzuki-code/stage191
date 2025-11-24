# quic_qkd_common.py
import json
from crypto_primitives import hkdf_extract, hkdf_expand
from qkd_buffer import QKDKeyBuffer
from metrics import inc_qkd_missing

def derive_epoch_keys(quic_connection, qkd_buf: QKDKeyBuffer, epoch: int, role: str, exporter_secret: bytes):
    """エポックごとにQKDビットを混ぜて鍵を導出"""
    qkd_slice = qkd_buf.get_slice(epoch)
    if qkd_slice is None:
        inc_qkd_missing(role)
        qkd_slice = b"\x00" * 32

    prk = hkdf_extract(salt=qkd_slice, ikm=exporter_secret)
    client_write = hkdf_expand(prk, b"client_write_key", 32)
    server_write = hkdf_expand(prk, b"server_write_key", 32)
    return client_write, server_write


def make_phase_notice(epoch: int) -> bytes:
    """フェーズ変更通知をJSON化して送信"""
    return json.dumps({"type": "phase_notice", "epoch": int(epoch)}).encode()


def parse_if_phase_notice(line: bytes):
    """受信したデータがフェーズ通知ならepochを返す"""
    try:
        obj = json.loads(line.decode())
        if obj.get("type") == "phase_notice":
            return int(obj["epoch"])
    except Exception:
        pass
    return None
