# qkd59.py  (Shamir Secret Sharing: init/combine/status/clean)
from __future__ import annotations
from pathlib import Path
import json, secrets, sys

# ====== 保存場所（ここがポイント！）======
BASE_DIR  = Path(__file__).parent        # スクリプトと同じ場所
SHARES_DIR = BASE_DIR / "shares"         # ここに必ず保存
MANIFEST  = SHARES_DIR / "team_manifest.json"

# ====== Shamir over large prime field ======
# 2^256 より大きい素数（Mersenne primeを使う）
P = (1 << 521) - 1  # 2^521 - 1（素数）。Python の int なら高速に動きます。

def bytes_to_int(b: bytes) -> int:
    return int.from_bytes(b, "big")

def int_to_bytes(x: int, length: int) -> bytes:
    return x.to_bytes(length, "big")

def poly_eval(coeffs: list[int], x: int, p: int = P) -> int:
    """ coeffs[0] + coeffs[1]*x + ...  (mod p) """
    y = 0
    for c in reversed(coeffs):
        y = (y * x + c) % p
    return y

def lagrange_interpolate(xy: list[tuple[int,int]], p: int = P) -> int:
    """ x=0 における多項式値（= 秘密）をラグランジュ補間で復元 """
    x_s = [x for x,_ in xy]
    y_s = [y for _,y in xy]
    k = len(xy)
    total = 0
    for i in range(k):
        xi, yi = x_s[i], y_s[i]
        num, den = 1, 1
        for j in range(k):
            if i == j: continue
            xj = x_s[j]
            num = (num * (-xj)) % p
            den = (den * (xi - xj)) % p
        # 逆元
        inv_den = pow(den, -1, p)
        li = (num * inv_den) % p
        total = (total + yi * li) % p
    return total

# ====== I/O ======
def save_json(path: Path, obj: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2))
    tmp.replace(path)

def load_json(path: Path) -> dict:
    return json.loads(path.read_text())

# ====== コマンド ======
def cmd_init():
    print("== 段階59: 初期化（シェアの作成） ==")
    try:
        n = int(input("配布人数 n を入力（例 5）: ").strip())
        k = int(input("復元に必要な人数 k を入力（例 3）: ").strip())
    except Exception:
        print("数字を入力してください"); return
    if not (1 <= k <= n):
        print("条件: 1 <= k <= n"); return

    ids_line = input("メンバーIDを入力（カンマ区切り 例: Alice,Bob,Carol ）: ").strip()
    ids = [s.strip() for s in ids_line.split(",") if s.strip()]
    if len(ids) != n:
        print(f"エラー: 入力ID数 {len(ids)} が n={n} と一致しません"); return

    # 32バイトのMKを作成（例: QKD最終鍵とみなす）
    MK = secrets.token_bytes(32)
    MK_int = bytes_to_int(MK)
    if MK_int >= P:
        # ほぼ起きないが念のため
        print("内部エラー: MK が P 以上でした。再実行してください。"); return

    # ランダム係数（秘匿）を用いた次数 k-1 の多項式
    coeffs = [MK_int] + [secrets.randbelow(P) for _ in range(k-1)]
    shares = []
    for idx, mid in enumerate(ids, start=1):
        x = idx
        y = poly_eval(coeffs, x, P)
        shares.append({"id": mid, "x": x, "y": str(y)})

    manifest = {
        "n": n, "k": k,
        "members": ids,
        "share_files": [f"share_{mid}.json" for mid in ids],
        "mk_len": len(MK),    # 復元時のバイト長
        "note": "Shamir secret sharing over prime field"
    }
    save_json(MANIFEST, manifest)
    for s in shares:
        save_json(SHARES_DIR / f"share_{s['id']}.json", s)

    print("\n✅ 作成完了。以下に保存しました：")
    print(f"  マニフェスト: {MANIFEST}")
    for mid in ids:
        print(f"  シェア:       {SHARES_DIR / ('share_'+mid+'.json')}")
    print("\n次は `python qkd59.py combine` で復元を試してください。")

def cmd_status():
    if not MANIFEST.exists():
        print("team_manifest.json がありません。まず `python qkd59.py init` を実行してください。")
        return
    mf = load_json(MANIFEST)
    print("== 状態 ==")
    print(json.dumps(mf, ensure_ascii=False, indent=2))
    # 既存シェア確認
    print("\n-- 既存シェア --")
    for f in mf["share_files"]:
        path = SHARES_DIR / f
        print("  ", ("OK " if path.exists() else "NG "), path)

def cmd_combine():
    if not MANIFEST.exists():
        print("team_manifest.json が見つかりません。`python qkd59.py init` を先に実行してください。")
        return
    mf = load_json(MANIFEST)
    n, k, ids = mf["n"], mf["k"], mf["members"]
    print(f"== 復元（k/n = {k}/{n}）==")
    use_line = input(f"復元に使うメンバーIDをカンマ区切りで {k} 個以上入力（例: {','.join(ids[:k])}）: ").strip()
    use_ids = [s.strip() for s in use_line.split(",") if s.strip()]
    if len(use_ids) < k:
        print(f"エラー: 少なくとも {k} ユーザーが必要です"); return

    xy = []
    for mid in use_ids:
        path = SHARES_DIR / f"share_{mid}.json"
        if not path.exists():
            print(f"シェアが見つかりません: {path}"); return
        s = load_json(path)
        xy.append((int(s["x"]), int(s["y"])))

    secret_int = lagrange_interpolate(xy[:k], P)
    MK_len = int(mf.get("mk_len", 32))
    MK = int_to_bytes(secret_int, MK_len)

    print("\n✅ 復元成功。MK（hex）:")
    print(MK.hex())
    # 必要ならファイルに吐き出す
    out = SHARES_DIR / "recovered_mk.bin"
    out.write_bytes(MK)
    print(f"→ 保存: {out}")

def cmd_clean():
    if SHARES_DIR.exists():
        for p in SHARES_DIR.glob("*"):
            p.unlink()
        SHARES_DIR.rmdir()
        print("shares/ を削除しました。")
    else:
        print("shares/ は存在しません。")

def main():
    if len(sys.argv) < 2:
        print("使い方: python qkd59.py [init|combine|status|clean]")
        return
    cmd = sys.argv[1]
    if cmd == "init":
        cmd_init()
    elif cmd == "combine":
        cmd_combine()
    elif cmd == "status":
        cmd_status()
    elif cmd == "clean":
        cmd_clean()
    else:
        print("未知のコマンドです: ", cmd)
        print("使い方: python qkd59.py [init|combine|status|clean]")

if __name__ == "__main__":
    main()

