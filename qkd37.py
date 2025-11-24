# qkd37_realistic.py
# E91 + CASCADEエラー訂正 + 有限サイズ補正
# 実用に近いパラメータでの教育用デモ

import numpy as np
import math
import secrets

# ====== 設定 ======
N_PAIRS = 200000        # ペア総数（試行回数） ← 大幅増
KEY_FRACTION = 0.75     # 鍵生成に使う割合
TEST_FRACTION = 0.10    # CHSHテストに使う割合
ERROR_RATE = 0.006      # 誤り率（QBER）0.6%程度
ALPHA = 1e-10           # 有限サイズ補正の信頼水準（厳しめ）
SAFETY_BITS = 40        # 安全マージン

# ====== エントロピー関数 ======
def h2(x):
    if x <= 0 or x >= 1:
        return 0.0
    return -x*math.log2(x) - (1-x)*math.log2(1-x)

# ====== シミュレーション ======
def run():
    # ペアを分配
    n_key = int(N_PAIRS * KEY_FRACTION)
    n_test = int(N_PAIRS * TEST_FRACTION)

    # QBER測定
    q_obs = ERROR_RATE

    # CHSH値の推定（理論値を3.2程度に設定、ノイズ加味）
    S_point = 2.8 + np.random.normal(0, 0.05)
    # 有限サイズ補正で下限を計算（近似）
    S_LB = S_point - 3.0/np.sqrt(max(1, n_test))

    # エラー訂正リーク（CASCADEを模擬）
    EC_leak = int(n_key * h2(q_obs) * 1.2)  # 1.2倍はCASCADEのオーバーヘッド

    # Devetak-Winter レート
    if S_LB > 2.0:
        r = 1 - h2(q_obs) - (EC_leak / n_key)
    else:
        r = 0.0

    # 有限サイズ補正
    A = int(5.0 * math.sqrt(n_key))  # 教育用に簡略化

    # 最終鍵長
    l_raw = int(n_key * max(0, 1 - h2(q_obs))) - EC_leak
    l_final = max(0, l_raw - A - SAFETY_BITS)

    return {
        "N": N_PAIRS,
        "n_key": n_key,
        "n_test": n_test,
        "QBER": q_obs,
        "S_point": S_point,
        "S_LB": S_LB,
        "EC_leak": EC_leak,
        "finite_A": A,
        "l_raw": l_raw,
        "l_final": l_final,
    }

# ====== 実行 ======
def main():
    res = run()

    print("=== 段階37: 実用寄りE91 + CASCADE + 有限サイズ補正 ===")
    print(f"総ペア数 N = {res['N']}")
    print(f"鍵用ビット = {res['n_key']} / テストビット = {res['n_test']}")
    print(f"QBER（誤り率） = {100*res['QBER']:.3f} %")
    print(f"CHSH推定値 S_point = {res['S_point']:.3f}, 下限 S_LB = {res['S_LB']:.3f}")
    print(f"エラー訂正リーク = {res['EC_leak']} ビット")
    print(f"有限サイズ補正 A = {res['finite_A']} ビット")
    print(f"生の鍵長 l_raw = {res['l_raw']} ビット")
    print(f"最終鍵長 l_final = {res['l_final']} ビット")

    if res['l_final'] > 0:
        print("\n✅ 最終鍵が生成されました！")
        # OTPデモ
        key_len = res['l_final'] // 8
        key = secrets.token_bytes(key_len)
        msg = "E91で暗号通信テスト"
        msg_bytes = msg.encode('utf-8')
        cipher = bytes([a ^ b for a, b in zip(msg_bytes, key[:len(msg_bytes)])])
        plain = bytes([a ^ b for a, b in zip(cipher, key[:len(msg_bytes)])])
        print(f"暗号文 (hex) = {cipher.hex()}")
        print(f"復号結果 = {plain.decode('utf-8')}")
    else:
        print("\n⚠️ 鍵が残りませんでした（統計不足かノイズ大）。")

if __name__ == "__main__":
    main()

