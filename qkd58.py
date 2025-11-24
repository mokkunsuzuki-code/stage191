# stage58_secure_cloud_sync.py
# 段階58：クラウド暗号同期（Encrypt before Cloud）
# 依存: cryptography

import os, sys, base64, json, getpass, subprocess
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

SERVICE_NAME = "QKD-Stage56"
ACCOUNT_NAME = os.environ.get("USER") or os.environ.get("USERNAME") or "user"

# ===== scryptで強力な鍵を作る =====
def derive_key(password: str, salt: bytes) -> bytes:
    kdf = Scrypt(salt=salt, length=32, n=2**14, r=8, p=1)
    return kdf.derive(password.encode())

# ===== macOSのKeychainからMK取得 =====
def get_macos_mk() -> bytes:
    out = subprocess.check_output(
        ["security","find-generic-password","-w","-a",ACCOUNT_NAME,"-s",SERVICE_NAME],
        stderr=subprocess.DEVNULL
    )
    return base64.b64decode(out.strip())

# ===== 暗号化 =====
def encrypt_file(input_path: str, output_path: str, key: bytes):
    with open(input_path,"rb") as f: data = f.read()
    nonce = os.urandom(12)
    aes = AESGCM(key)
    ct = aes.encrypt(nonce, data, b"cloud-sync")
    blob = {"nonce": base64.b64encode(nonce).decode(), "ct": base64.b64encode(ct).decode()}
    with open(output_path,"w",encoding="utf-8") as f: json.dump(blob, f)
    print(f"✅ {input_path} を暗号化 → {output_path} に保存しました。")

# ===== 復号 =====
def decrypt_file(input_path: str, output_path: str, key: bytes):
    blob = json.load(open(input_path,"r",encoding="utf-8"))
    nonce = base64.b64decode(blob["nonce"])
    ct = base64.b64decode(blob["ct"])
    aes = AESGCM(key)
    data = aes.decrypt(nonce, ct, b"cloud-sync")
    with open(output_path,"wb") as f: f.write(data)
    print(f"✅ {input_path} を復号 → {output_path} に復元しました。")

# ===== メイン処理 =====
def main():
    if len(sys.argv)<2 or sys.argv[1] not in ["encrypt","decrypt"]:
        print("使い方: python stage58_secure_cloud_sync.py [encrypt|decrypt]")
        sys.exit(1)

    # 鍵を取得（macOS Keychain優先、無ければパスワード）
    try:
        mk = get_macos_mk()
    except Exception:
        pw = getpass.getpass("🔑 パスワードを入力してください: ")
        salt = b"cloud-sync-salt"
        mk = derive_key(pw, salt)

    if sys.argv[1] == "encrypt":
        input_file = input("暗号化したいファイルを入力してください: ").strip()
        if not os.path.exists(input_file):
            print("ファイルが見つかりません。"); return
        encrypt_file(input_file, input_file + ".qsync", mk)

    elif sys.argv[1] == "decrypt":
        input_file = input("復号したいファイルを入力してください: ").strip()
        if not os.path.exists(input_file):
            print("ファイルが見つかりません。"); return
        output_name = input_file.replace(".qsync","")
        decrypt_file(input_file, output_name, mk)

if __name__ == "__main__":
    main()

