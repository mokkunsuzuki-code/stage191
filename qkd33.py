# qkd32_jp.py  — 段階32：パス採用率 vs 鍵生成割合（日本語表示）
# 依存: numpy, matplotlib
# 実行: python qkd32_jp.py

import math
import numpy as np

# ====== 日本語フォント設定（環境にあるものを順に試す）======
import matplotlib
import matplotlib.pyplot as plt

def set_japanese_font():
    candidates = [
        "Hiragino Sans",        # macOS
        "Hiragino Kaku Gothic ProN",
        "Yu Gothic",            # Windows
        "Meiryo",
        "Noto Sans CJK JP",     # Linux / Google fonts
        "Noto Sans JP",
        "TakaoGothic"
    ]
    for name in candidates:
        try:
            matplotlib.rcParams["font.family"] = name
            # テスト描画でエラーが出なければ採用
            fig = plt.figure()
            plt.title("日本語フォントテスト")
            plt.close(fig)
            return name
        except Exception:
            continue
    return matplotlib.rcParams.get("font.family", ["sans-serif"])[0]

FONT_USED = set_japanese_font()

# ====== 教育用簡略モデル ======
# 1日に得られるEPRペア総数（教育用の固定値）
PAIRS_PER_DAY = 20000

# 天候の平均成功確率（例：地上局の平均クリア率）
# 値を変えると全体のレベルが上下します（0.0〜1.0）
P_CLEAR_AVG = 0.75  # 75% くらいに設定（段階32のグラフの雰囲気に近づけるため）

def chsh_pass_prob(n_samples: int) -> float:
    """
    CHSHの検定に使えるサンプル数 n_samples に応じた合格確率（教育用モデル）
    ・サンプルが少ないと通りにくい
    ・増えるほど通りやすくなる（S字）
    """
    if n_samples <= 0:
        return 0.0
    # ロジスティック曲線で 3000 サンプル付近からグッと上がる感じ
    x0 = 3000.0   # 立ち上がり中心
    k  = 1/800.0  # 立ち上がりの急さ
    p  = 1.0 / (1.0 + math.exp(-(n_samples - x0) * k))
    # 上限は 99% 程度に制限（理想でも完全ではない前提）
    return min(0.99, max(0.0, p))

def pass_rate_for_key_fraction(key_fraction: float) -> float:
    """
    鍵に回す割合 key_fraction（0〜1）から、その日のパス採用率（0〜1）を返す。
    ・テスト割合 test_frac = 1 - key_fraction
    ・CHSHは test に回したサンプル数が多いほど通りやすい
    ・天候は平均値 P_CLEAR_AVG を掛け合わせる（独立仮定）
    """
    key_fraction = max(0.0, min(1.0, key_fraction))
    test_frac = 1.0 - key_fraction
    n_chsh = int(PAIRS_PER_DAY * test_frac)
    p_chsh = chsh_pass_prob(n_chsh)
    p_pass = P_CLEAR_AVG * p_chsh
    return p_pass

def expected_final_key_bits_per_day(key_fraction: float) -> int:
    """
    期待できる最終鍵ビット数（雑に：パス採用率 × 鍵に回したビット数）
    ※段階32は“採用率”が主題なので、参考出力として用意
    """
    test_frac = 1.0 - key_fraction
    n_keep = int(PAIRS_PER_DAY * key_fraction)
    return int(n_keep * pass_rate_for_key_fraction(key_fraction))

# ====== 掃引してプロット ======
def main():
    # 掃引用の鍵割合（0.30〜0.80）
    xs = np.round(np.linspace(0.30, 0.80, 21), 3)
    ys = []
    keys = []

    for kf in xs:
        p = pass_rate_for_key_fraction(kf)
        ys.append(100.0 * p)  # %
        keys.append(expected_final_key_bits_per_day(kf))

    ys = np.array(ys)
    keys = np.array(keys)

    # 最良点（採用率最大→同率なら最終鍵ビットが最大）
    best_idx = int(np.argmax(np.stack([ys, keys], axis=1)[:,0]))
    best_kf  = xs[best_idx]
    best_pass = ys[best_idx]
    best_key  = keys[best_idx]

    # ---- グラフ（日本語）----
    plt.figure(figsize=(7,5))
    plt.plot(xs, ys, marker="o")
    plt.xlabel("鍵生成に回す割合（key_fraction）")
    plt.ylabel("パス採用率（%）\n（天候 × CHSH）")
    plt.title("パス採用率 vs 鍵生成割合（教育用モデル）")
    plt.grid(True, alpha=0.3)

    # 最良点に★と注釈
    plt.plot([best_kf], [best_pass], marker="*", markersize=14)
    plt.annotate(
        f"最良: key_fraction={best_kf:.2f}\n"
        f"採用率={best_pass:.1f}% / 期待鍵={best_key:,} bit/日",
        xy=(best_kf, best_pass), xytext=(best_kf+0.015, best_pass+1.5),
        arrowprops=dict(arrowstyle="->", lw=1.2),
        fontsize=10
    )

    # フォント名を図中に小さく表示（確認用）
    plt.text(0.305, min(ys)+0.3, f"使用フォント: {FONT_USED}", fontsize=8, alpha=0.5)

    plt.tight_layout()
    plt.show()

    # ---- 表形式の概要出力 ----
    print("\n=== 掃引結果（抜粋）===")
    print(" key_fraction | pass_rate(%) | expected_key(bit/day)")
    for i in range(0, len(xs), 2):
        print(f"   {xs[i]:.2f}      |   {ys[i]:6.2f}    |   {keys[i]:>8,d}")

    print("\n[推奨（教育用）]")
    print(f"  ・key_fraction = {best_kf:.2f}")
    print(f"  ・採用率 ≈ {best_pass:.1f}%")
    print(f"  ・期待最終鍵 ≈ {best_key:,} bit/日")
    print("\n※実験パラメータを変えるには、コード冒頭の PAIRS_PER_DAY と P_CLEAR_AVG を変更してください。")
    print("  （より厳密には、CHSHの通過確率モデル chsh_pass_prob() を実験系に合わせて調整します）")

if __name__ == "__main__":
    main()

