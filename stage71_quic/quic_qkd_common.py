# -*- coding: utf-8 -*-
# quic_qkd_common.py
import json
from typing import Tuple

from crypto_primitives import hkdf_extract, hkdf_expand
from qkd_buffer import QKDKeyBuffer

# Exporter のラベル（任意のアプリ識別子でOK）
EXPORTER_LABEL = b"EXPORTER-QUIC-KEY-v1"


def derive_epoch_keys(quic_connection, qkd_buf: QKDKeyBuffer, epoch: int) -> Tuple[bytes, bytes]:
    """
    ステップ2: TLS Exporter で素材を取得（32B）
    ステップ3: QKD(32B) を salt に HKDF-Extract -> Expand で app鍵へ
    """
    # --- Exporter（TLS 1.3, aioquicの内部TLS） ---
    # 注意: _quic.tls.export_keying_material はaioquicで一般的に使われるAPI
    exporter_secret = quic_connection._quic.tls.export_keying_material(  # type: ignore[attr-defined]
        label=EXPORTER_LABEL,
        length=32,
    )

    # --- QKDスライスを取得（欠品ならゼロ塩でフォールバック） ---
    qkd_slice = qkd_buf.get_slice(epoch)
    if qkd_slice is None:
        qkd_slice = b"\x00" * 32

    # --- HKDFで混合（情報理論的エントロピーを加える） ---
    prk = hkdf_extract(salt=qkd_slice, ikm=exporter_secret)
    client_write = hkdf_expand(prk, b"client_write_key", 32)
    server_write = hkdf_expand(prk, b"server_write_key", 32)
    return client_write, server_write


# 1行JSONの軽量制御（Key Phase通知）
def make_phase_notice(epoch: int) -> bytes:
    return json.dumps({"type": "phase_notice", "epoch": int(epoch)}, separators=(",", ":")).encode() + b"\n"


def parse_if_phase_notice(line: bytes):
    try:
        obj = json.loads(line.decode())
        if obj.get("type") == "phase_notice":
            return int(obj["epoch"])
    except Exception:
        pass
    return None

