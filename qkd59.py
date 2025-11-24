# stage59_threshold_team_share.py
# 段階59：チーム共有（しきい値秘密分散 Shamir）＋ 各シェアをAES-GCM(パスワード)で保護
# 復元時は OSの金庫（mac: Keychain / Windows: DPAPI / Linux: 環境変数に出力）へ登録
# 依存: cryptography

import os, sys, json, base64, secrets, getpass, subprocess, hashlib
from typing import List, Tuple

from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

SERVICE_NAME = "QKD-Stage56"
ACCOUNT_NAME = os.environ.get("USER") or os.environ.get("USERNAME") or "user"
MANIFEST     = "team_manifest.json"     # n, k, 素数p など
EXPORT_DIR   = "shares"                 # シェアを保存するフォルダ
MK_BYTES     = 32                       # MK（32バイト）
# Shamir 用の大きな素数（2^521 - 1 より少し小さい安全マージンもOKだが、ここでは確実な大素数を固定）
# 参考用に十分大きな素数を用意（> 2^256）。以下は 2^521-1 ではなく、521ビット長の安全な素数の一例。
P = int(
    "686479766013060971498190079908139321726943530014330540939446345918"
    "554318339765605212255964066145455497729631139148085803712198799971"
    "6643812574028291115057151"
)  # これは secp521r1 の素数 p と同じ値

# ========== 基本ユーティリティ ==========
def b64e(b: bytes) -> str: return base64.b64encode(b).decode()
def b64d(s: str) -> bytes: return base64.b64decode(s.encode())

def scrypt_key(password: str, salt: bytes, length=32) -> bytes:
    kdf = Scrypt(salt=salt, length=length, n=2**14, r=8, p=1)
    return kdf.derive(password.encode())

def aesgcm_encrypt(key: bytes, plaintext: bytes, aad: bytes=b"") -> Tuple[bytes, bytes]:
    aes = AESGCM(key)
    nonce = os.urandom(12)
    ct = aes.encrypt(nonce, plaintext, aad)
    return nonce, ct

def aesgcm_decrypt(key: bytes, nonce: bytes, ct: bytes, aad: bytes=b"") -> bytes:
    aes = AESGCM(key)
    return aes.decrypt(nonce, ct, aad)

# ========== Shamir（大素数体上） ==========
# 秘密 s を次数(k-1) の多項式 f(x) の定数項にする。x=1..n の点を配る。
def _eval_poly(coeffs: List[int], x: int, p: int) -> int:
    # Horner法
    y = 0
    for c in reversed(coeffs):
        y = (y * x + c) % p
    return y

def shamir_split(secret_bytes: bytes, n: int, k: int, p: int=P) -> List[Tuple[int,int]]:
    if not (2 <= k <= n <= 255):
        raise ValueError("2 <= k <= n <= 255 で指定してください")
    s = int.from_bytes(secret_bytes, "big")
    if s >= p:
        raise ValueError("秘密が素数p以上です。pを大きくするか、秘密を短くしてください。")
    # ランダム係数（定数項=秘密）
    coeffs = [s] + [secrets.randbelow(p) for _ in range(k-1)]
    shares = []
    for x in range(1, n+1):
        y = _eval_poly(coeffs, x, p)
        shares.append((x, y))
    return shares

def _lagrange_basis(x_values: List[int], i: int, p: int) -> int:
    xi = x_values[i]
    num, den = 1, 1
    for j, xj in enumerate(x_values):
        if j == i: continue
        num = (num * (-xj)) % p
        den = (den * (xi - xj)) % p
    # 逆元
    inv_den = pow(den, p-2, p)
    return (num * inv_den) % p

def shamir_combine(shares: List[Tuple[int,int]], p: int=P) -> bytes:
    # x座標はユニーク
    x_vals = [x for x,_ in shares]
    y_vals = [y for _,y in shares]
    s = 0
    for i in range(len(shares)):
        li = _lagrange_basis(x_vals, i, p)
        s = (s + y_vals[i] * li) % p
    # s が秘密
    # 長さは MK_BYTES に合わせて32バイト化（上位ゼロ詰め）
    return int(s).to_bytes(MK_BYTES, "big")

# ========== OS金庫への登録 ==========
def set_macos_mk(mk: bytes):
    subprocess.check_call([
        "security","add-generic-password",
        "-a", ACCOUNT_NAME, "-s", SERVICE_NAME,
        "-w", b64e(mk), "-U"
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def set_windows_mk(mk: bytes):
    # DPAPI でユーザー領域に保存（stage56と同等）
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
    if not crypt32.CryptProtectData(ctypes.byref(in_blob), None, None, None, None, CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out_blob)):
        raise RuntimeError("DPAPI 保存に失敗")
    enc = _blob_to_bytes(out_blob)
    with open(blob_path, "wb") as f: f.write(enc)

def install_mk_to_os_keystore(mk: bytes):
    if sys.platform == "darwin":
        set_macos_mk(mk)
        print("✅ macOS Keychain に登録しました。")
    elif os.name == "nt":
        set_windows_mk(mk)
        print("✅ Windows DPAPI に登録しました。")
    else:
        # Linux等：安全のため環境変数値を表示（Secret Serviceは要ユーザの環境次第）
        print("🔎 Linux/その他: 以下を環境変数に設定してください（シェル例）")
        print(f'export QKD_STAGE56_MK_B64="{b64e(mk)}"')

# ========== シェアの保存形式（各メンバー1ファイル） ==========
# JSON構造: {
#   "member_id": "Alice",
#   "x": int,
#   "p": str(b10),   # 復元用に素数も同梱
#   "salt": b64,     # scrypt 用
#   "nonce": b64,    # AESGCM
#   "ct": b64        # AESGCM( y_bytes )
# }
def save_share(member_id: str, share: Tuple[int,int], password: str, out_dir=EXPORT_DIR):
    os.makedirs(out_dir, exist_ok=True)
    x, y = share
    y_bytes = int(y).to_bytes((P.bit_length()+7)//8, "big")  # pビット長に合わせた長さ
    salt = os.urandom(16)
    key = scrypt_key(password, salt)
    nonce, ct = aesgcm_encrypt(key, y_bytes, aad=b"stage59-share")
    obj = {
        "member_id": member_id,
        "x": x,
        "p": str(P),
        "salt": b64e(salt),
        "nonce": b64e(nonce),
        "ct": b64e(ct),
    }
    path = os.path.join(out_dir, f"{member_id}.qshare.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    print(f"🗂  {path} を作成しました。")

def load_share(path: str, password: str) -> Tuple[int,int]:
    obj = json.load(open(path, "r", encoding="utf-8"))
    x = int(obj["x"])
    salt = b64d(obj["salt"]); nonce = b64d(obj["nonce"]); ct = b64d(obj["ct"])
    key = scrypt_key(password, salt)
    y_bytes = aesgcm_decrypt(key, nonce, ct, aad=b"stage59-share")
    y = int.from_bytes(y_bytes, "big")
    return x, y

# ========== コマンド ==========
def cmd_init():
    print("=== 段階59: 初期化（シェアの作成）===")
    try:
        n = int(input("配布人数 n を入力 (例 5): ").strip())
        k = int(input("復元に必要な人数 k を入力 (例 3): ").strip())
    except Exception:
        print("数値で入力してください。"); return
    if not (2 <= k <= n <= 255):
        print("2 <= k <= n <= 255 を満たしてください。"); return

    # メンバーIDを入力（カンマ区切り）
    members = input("メンバーID一覧（カンマ区切り, 例: Alice,Bob,Carol,Dan,Eve）: ").strip()
    member_ids = [m.strip() for m in members.split(",") if m.strip()]
    if len(member_ids) != n:
        print(f"n={n} 人分のIDを入力してください。"); return

    # チームのマスター鍵 MK を生成
    mk = os.urandom(MK_BYTES)
    # Shamir で n,k に分割
    shares = shamir_split(mk, n, k, P)

    # マニフェスト保存
    manifest = {"n": n, "k": k, "p": str(P), "members": member_ids}
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"📄 マニフェスト {MANIFEST} を作成しました。")

    # 各メンバー分のパスワードを聞き、シェアを暗号化保存
    print("\n各メンバーのシェアにパスワードを設定します（受取人だけが知る合言葉）")
    for mid, share in zip(member_ids, shares):
        pw = getpass.getpass(f"  {mid} のパスワード: ")
        save_share(mid, share, pw, EXPORT_DIR)

    print("\n✅ 配布準備が完了しました。")
    print(f"- 配布フォルダ: {EXPORT_DIR}/（各 {member_ids[i]}.qshare.json）")
    print(f"- 復元には k={k} 人分の .qshare.json と各パスワードが必要です。")

def cmd_combine():
    print("=== 段階59: 復元（k人分のシェアからMKを再生）===")
    if not os.path.exists(MANIFEST):
        print(f"{MANIFEST} が見つかりません。init を先に実行してください。"); return
    manifest = json.load(open(MANIFEST, "r", encoding="utf-8"))
    n, k = int(manifest["n"]), int(manifest["k"])
    print(f"必要人数 k = {k} / 総メンバー n = {n}")

    # k個のファイルパスを入力させる
    print("復元に使う k 個の .qshare.json のパスを、改行で入力してください。")
    print("（入力を終えるには空行）")
    paths = []
    while True:
        pth = input("> ").strip()
        if not pth:
            break
        if not os.path.exists(pth):
            print("  ファイルが見つかりません。もう一度。"); continue
        paths.append(pth)
        if len(paths) == k: break
    if len(paths) < k:
        print(f"k={k} 個必要です。"); return

    # 各シェアのパスワードを聞いて復号
    shares = []
    for pth in paths:
        mid = os.path.splitext(os.path.basename(pth))[0].replace(".qshare","").replace(".json","")
        pw = getpass.getpass(f"  {mid} のパスワード: ")
        try:
            x, y = load_share(pth, pw)
            shares.append((x, y))
        except Exception:
            print("  復号に失敗：パスワードが違うかファイル破損です。"); return

    # 復元
    mk = shamir_combine(shares, P)
    print("🔓 マスター鍵（MK）を復元しました。OSの金庫へ登録します。")
    install_mk_to_os_keystore(mk)
    print("✅ 復元完了。以降は段階56〜の仕組みで DEK ラップ・永続化を安全に使えます。")

# ========== エントリ ==========
def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("init","combine"):
        print("使い方: python stage59_threshold_team_share.py [init|combine]")
        return
    if sys.argv[1] == "init":
        cmd_init()
    elif sys.argv[1] == "combine":
        cmd_combine()

if __name__ == "__main__":
    main()

