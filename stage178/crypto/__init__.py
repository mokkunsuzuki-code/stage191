# MIT License © 2025 Motohiro Suzuki
"""
crypto/ (Stage178 package marker)

qsp.handshake / qsp.rekey_engine が `import crypto` を期待しているため、
crypto を “確実に import できる” パッケージとして固定する。

中身は Stage178 の crypto/ 配下の実装が使われる。
"""
