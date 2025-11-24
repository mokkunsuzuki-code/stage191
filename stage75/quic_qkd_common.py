# -*- coding: utf-8 -*-
# quic_qkd_common.py
from typing import Tuple
from crypto_primitives import hkdf_extract, hkdf_expand
from qkd_buffer import QKDKeyBuffer

EXPORTER_LABEL = b"EXPORTER-QUIC-KEY-v1"

def derive_epoch_keys(quic_connection, qkd_buf: QKDKeyBuffer, epoch: int) -> Tuple[bytes, bytes, bytes, bytes]:
    exporter_secret = quic_connection._quic.tls.export_keying_material(  # type: ignore[attr-defined]
        label=EXPORTER_LABEL,
        length=32,
    )
    qkd_slice = qkd_buf.get_slice(epoch)
    if qkd_slice is None:
        qkd_slice = b"\x00" * 32

    prk = hkdf_extract(salt=qkd_slice, ikm=exporter_secret)
    client_write = hkdf_expand(prk, b"client_write_key_v2", 32)
    server_write = hkdf_expand(prk, b"server_write_key_v2", 32)
    client_nonce_base = hkdf_expand(prk, b"client_nonce_base_v2", 12)
    server_nonce_base = hkdf_expand(prk, b"server_nonce_base_v2", 12)
    return client_write, server_write, client_nonce_base, server_nonce_base

