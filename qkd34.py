# stage34_auto_opt_encrypt.py
# 段階34: key_fractionを調整し最適化＋OTP暗号化で通信実験（教育用プロトタイプ）

import math
import numpy as np
import matplotlib.pyplot as plt
from qiskit import QuantumCircuit, transpile
from qiskit_aer import AerSimulator
from scipy.stats import beta
import hashlib, secrets

# 日本語フォント設定（Mac用）
try:
    plt.rcParams['font.family'] = 'Hiragino Sans'
except Exception:
    pass
plt.rcParams['axes.unicode_minus'] = False

# 乱数シード
SEED = 42
rng = np.random.default_rng(SEED)

# ----------------------------
# 天候モデル（簡易）
# ----------------------------
def at_least_one_clear_once(station_p_list, rho, rng):
    """ステーション群のうち1つでも晴れるかを判定"""
    u = rng.random()
    # 相関をrhoで導入（0=独立,1=完全相関）
    if u < rho:
        # 全ステーション同じ天候
        return rng.random() < np.mean(station_p_list)
    else:
        # 独立判定
        return any(rng.random() < p for p in station_p_list)

# ----------------------------
# 1日の評価
# ----------------------------
def evaluate_day_for_key_fraction(kf, trials_weather=1000, seed=123):
    rng = np.random.default_rng(seed)
    # 鍵生成割合kfでCHSH検査に回す残りを評価
    station_p_list = [0.5, 0.6, 0.7]   # 仮の晴天確率
    rho = 0.2                          # 天候相関
    count_ok = 0
    for _ in range(trials_weather):
        weather_ok = at_least_one_clear_once(station_p_list, rho, rng)
        if weather_ok:
            # 簡単なCHSH成功判定（乱数ベース）
            if rng.random() < (1 - kf):  
                count_ok += 1
    return count_ok / trials_weather

# ----------------------------
# OTP暗号化デモ
# ----------------------------
def otp_encrypt_decrypt_demo():
    msg = "量子鍵配送の暗号化テスト🔑"
    key_len = 64
    key = secrets.token_bytes(key_len)
    msg_b = msg.encode("utf-8")
    if len(msg_b) > key_len:
        print("メッセージが長すぎます（今回はテスト用に64バイトまで）")
        return
    m = min(len(msg_b), key_len)
    cipher = bytes([msg_b[i] ^ key[i] for i in range(m)])
    plain = bytes([cipher[i] ^ key[i] for i in range(m)])
    print("cipher(hex) =", cipher.hex())
    print("decrypted  =", plain.decode("utf-8", errors="ignore"))

# ----------------------------
# メイン処理
# ----------------------------
def main():
    print("=== 段階34: 自動最適化サンプル ===")

    kfs = np.linspace(0.1, 0.95, 10)  # 鍵生成に回す割合
    adm = [evaluate_day_for_key_fraction(kf, trials_weather=500, seed=2025) for kf in kfs]

    # 結果表示
    for kf, val in zip(kfs, adm):
        print(f"key_fraction={kf:.2f}, success={val:.3f}")

    # グラフ表示
    plt.figure(figsize=(7,5))
    plt.plot(kfs, np.array(adm)*100, marker='o')
    plt.xlabel("鍵生成に回す割合 (key_fraction)")
    plt.ylabel("パス採用率 [%] (天候&CHSH)")
    plt.title("パス採用率 vs 鍵生成割合")
    plt.grid(True)
    plt.show()   # 画面に表示

    # OTP暗号化デモ
    otp_encrypt_decrypt_demo()

if __name__ == "__main__":
    main()

