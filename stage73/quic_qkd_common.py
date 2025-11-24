# quic_qkd_common.py
import json
from typing import Tuple

from crypto_primitives import hkdf_extract, hkdf_expand
from qkd_buffer import QKDKeyBuffer
from metrics import inc_qkd_missing  # ← これが見つからないエラーを修正

def derive_epoch_keys(
    quic_connection,  # 実運用では tls exporter を使う想定（ここでは未使用ダミー）
    qkd_buf: QKDKeyBuffer,
    epoch: int,
    exporter_secret: bytes | None = None,
    role: str = "client",
) -> Tuple[bytes, bytes]:
    """
    指定エポックのQKDスライス(32B)と exporter_secret を混ぜて
    client_write / server_write の 32バイト鍵を導出するデモ関数
    """
    qkd_slice = qkd_buf.get_slice(epoch)
    if qkd_slice is None:
        # QKDがまだ届いていなければゼロ塩＋メトリクス加算
        inc_qkd_missing(role)
        qkd_slice = b"\x00" * 32

    if exporter_secret is None:
        exporter_secret = b"\x00" * 32  # デモ用フォールバック

    prk = hkdf_extract(salt=qkd_slice, ikm=exporter_secret)
    client_write = hkdf_expand(prk, b"client_write_key", 32)
    server_write = hkdf_expand(prk, b"server_write_key", 32)
    return client_write, server_write

def make_phase_notice(epoch: int) -> bytes:
    """フェーズ変更通知をJSONで送る（デモ用）"""
    return json.dumps({"type": "phase_notice", "epoch": int(epoch)}).encode()

def parse_if_phase_notice(line: bytes) -> int | None:
    """受け取った1行がフェーズ通知なら epoch を返す"""
    try:
        obj = json.loads(line.decode())
        if obj.get("type") == "phase_notice":
            return int(obj["epoch"])
    except Exception:
        pass
    return None

# 簡単セルフテスト
if __name__ == "__main__":
    buf = QKDKeyBuffer()
    epoch = 100
    # QKDスライスを入れない→inc_qkd_missing が 1 カウントされる
    cw, sw = derive_epoch_keys(None, buf, epoch, exporter_secret=b"\x11"*32, role="server")
    print("[SelfTest] cw[:8]=", cw[:8].hex(), "sw[:8]=", sw[:8].hex())
    # スライスを供給→通常導出
    buf.feed(epoch, b"\x22"*32)
    cw, sw = derive_epoch_keys(None, buf, epoch, exporter_secret=b"\x11"*32, role="server")
    print("[SelfTest] (with QKD) cw[:8]=", cw[:8].hex(), "sw[:8]=", sw[:8].hex())
