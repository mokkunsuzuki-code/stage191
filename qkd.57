# stage57_export_import.py
# 段階57：多端末移行（MKの安全なエクスポート/インポート）
# 依存: cryptography

import os, sys, base64, getpass, json, shutil, subprocess, ctypes, hashlib
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

EXPORT_FILE = "exported_mk.bin"
SERVICE_NAME = "QKD-Stage56"
ACCOUNT_NAME = os.environ.get("USER") or os.environ.get("USERNAME") or "user"

# ====== scrypt で強力な鍵を作る ======
def derive_key(password: str, salt: bytes) -> bytes:
    kdf = Scrypt(salt=salt, length=32, n=2**14, r=8, p=1)
    return kdf.derive(password.encode())

# ====== macOS Keychain から MK を取り出す ======
def get_macos_mk() -> bytes:
    out = subprocess.check_output(
        ["security","find-generic-password","-w","-a",ACCOUNT_NAME,"-s",SERVICE_NAME],
        stderr=subprocess.DEVNULL
    )
    return base64.b64decode(out.strip())

# ====== macOS Keychain に MK を登録する ======
def set_macos_mk(mk: bytes):
    subprocess.check_call(
        ["security","add-generic-password","-a",ACCOUNT_NAME,"-s",SERVICE_NAME,"-w",base64.b64encode(mk).decode(),"-U"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

# ====== Windows DPAPI 保存 ======
def set_windows_mk(mk: bytes):
    import ctypes, ctypes.wintypes
    blob_path = os.path.join(os.path.expanduser("~"), ".qkd_stage56_mk.dpapi")
    CRYPTPROTECT_UI_FORBIDDEN = 0x1
    crypt32 = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    class DATA_BLOB(ctypes.Structure):
        _fields_ = [('cbData', ctypes.wintypes.DWORD),
                    ('pbData', ctypes.POINTER(ctypes.c_ubyte))]
    def _bytes_to_blob(b: bytes) -> DATA_BLOB:
        buf = (ctypes.c_ubyte * len(b))(*b)
        return DATA_BLOB(len(b), buf)
    def _blob_to_bytes(blob: DATA_BLOB) -> bytes:
        size = int(blob.cbData)
        ptr = ctypes.cast(blob.pbData, ctypes.POINTER(ctypes.c_char))
        data = ctypes.string_at(ptr, size)
        kernel32.LocalFree(blob.pbData)
        return data
    in_blob = _bytes_to_blob(mk)
    out_blob = DATA_BLOB()
    crypt32.CryptProtectData(ctypes.byref(in_blob), None, None, None, None, CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out_blob))
    enc = _blob_to_bytes(out_blob)
    with open(blob_path,"wb") as f: f.write(enc)

# ====== 実行部分 ======
def export_mk():
    print("🔐 MKエクスポート（安全に持ち出し）")
    pw = getpass.getpass("合言葉を入力してください: ")
    salt = os.urandom(16)
    key = derive_key(pw, salt)
    mk = get_macos_mk() if sys.platform=="darwin" else os.urandom(32)
    aes = AESGCM(key)
    nonce = os.urandom(12)
    ct = aes.encrypt(nonce, mk, b"exportMK")
    with open(EXPORT_FILE,"wb") as f:
        f.write(salt+nonce+ct)
    print(f"✅ {EXPORT_FILE} に保存しました（パスワードで暗号化済み）")

def import_mk():
    print("📦 MKインポート（別端末で復元）")
    pw = getpass.getpass("合言葉を入力してください: ")
    blob = open(EXPORT_FILE,"rb").read()
    salt,nonce,ct = blob[:16], blob[16:28], blob[28:]
    key = derive_key(pw, salt)
    aes = AESGCM(key)
    mk = aes.decrypt(nonce, ct, b"exportMK")
    print("🔓 鍵を復号しました。OS金庫に登録します...")
    if sys.platform == "darwin":
        set_macos_mk(mk)
    elif os.name == "nt":
        set_windows_mk(mk)
    else:
        print("Linux環境では、環境変数 QKD_STAGE56_MK_B64 に設定してください:")
        print(base64.b64encode(mk).decode())
    print("✅ 鍵のインポートが完了しました！")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("使い方: python stage57_export_import.py [export|import]")
        sys.exit(1)
    if sys.argv[1] == "export":
        export_mk()
    elif sys.argv[1] == "import":
        import_mk()
