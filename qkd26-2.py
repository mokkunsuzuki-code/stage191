import matplotlib.pyplot as plt

def main():
    # 光ファイバーと衛星のパラメータ（教育用）
    fiber_rate = 5.28e11   # Fiber 50 km
    sat_rate_base = 2.1e6  # Satellite 1000 km (晴天率100%の場合)

    # 晴天率 80% に設定
    clear_prob = 0.8
    sat_rate = sat_rate_base * clear_prob

    # 合計（Fiber + Satellite）
    total = fiber_rate + sat_rate

    # グラフ描画（段階26と同じ3本の棒グラフ）
    labels = ["Fiber/day", "Satellite/day", "Total/day"]
    values = [fiber_rate, sat_rate, total]

    plt.figure(figsize=(6,5))
    plt.bar(labels, values, color=["blue","orange","green"])
    plt.yscale("log")  # 桁が大きいので対数スケール
    plt.ylabel("Secret key bits per day (log scale)")
    plt.title("Hybrid QKD Throughput (Fiber + Satellite, 晴天率=80%)")
    plt.tight_layout()
    plt.show()

    # 数値を出力
    print("=== Hybrid QKD throughput (晴天率80%) ===")
    print(f"Fiber/day = {fiber_rate:.2e} bits/day")
    print(f"Satellite/day (80%) = {sat_rate:.2e} bits/day")
    print(f"Total/day = {total:.2e} bits/day")

if __name__ == "__main__":
    main()

