# qkd45.py  — 段階45 安全実行テンプレ（ハングしない版）

from __future__ import annotations
import os, sys, time, math, random
import faulthandler
faulthandler.enable()
faulthandler.dump_traceback_later(30, repeat=True, file=sys.stderr)  # 30秒ごとに現在のスタックを自動表示

# ---- Matplotlib は非GUIバックエンドにしてブロック回避 ----
os.environ.setdefault("MPLBACKEND", "Agg")  # GUIが無い環境でもOK
import matplotlib
import matplotlib.pyplot as plt

# ---- Qiskit を使う場合に備えて“任意”で読み込む（無い環境でも動く）----
HAS_QISKIT = False
try:
    from qiskit import QuantumCircuit, transpile
    from qiskit_aer import AerSimulator
    HAS_QISKIT = True
except Exception:
    pass  # Qiskitが無ければスキップ。下の run_qiskit_demo() は呼ばれない想定


# ===================== ここに段階45の本処理を入れる =====================

def run_qiskit_demo(n_circs=50, shots=256, seed=45):
    """
    （任意）Qiskitの重さを抑えたサンプル。
    Qiskitが無ければ何もしない。
    """
    if not HAS_QISKIT:
        print("[Qiskit] 未導入のためスキップ", flush=True)
        return []

    rng = random.Random(seed)
    circs = []
    for _ in range(n_circs):
        qc = QuantumCircuit(1, 1)
        if rng.random() < 0.5:
            qc.x(0)
        qc.h(0)
        qc.measure(0, 0)
        circs.append(qc)

    sim = AerSimulator(method="stabilizer")  # 速いメソッド
    tc = transpile(circs, sim, optimization_level=1)  # transpileは1回だけ
    res = sim.run(tc, shots=shots).result()
    counts = [res.get_counts(i) for i in range(len(circs))]
    return counts


def run_stage45(N=200_000, progress_every=5_000):
    """
    段階45の重計算をここに入れる。
    今はダミーで“計算→配列に記録→グラフ化”を行う。
    """
    print(f"[RUN] stage45 start: N={N}", flush=True)
    rng = random.Random(2025)

    xs, ys = [], []
    SAFETY_MAX_STEPS = N + 10_000  # 無限ループ保険
    steps = 0

    s = 0.0
    for i in range(N):
        # --- ここにあなたの計算ロジックを入れる（ダミーはランダムウォーク）---
        s += rng.uniform(-1.0, 1.0)
        xs.append(i)
        ys.append(s)

        # 進捗ログ
        if (i + 1) % progress_every == 0:
            print(f"  progress: {i+1}/{N}", flush=True)

        # 安全ブレーク
        steps += 1
        if steps > SAFETY_MAX_STEPS:
            raise RuntimeError("safety break: loop too long")

    print("[RUN] stage45 main loop done.", flush=True)
    return xs, ys


def plot_and_finish(xs, ys, title="Stage45 Result", show=False, save_path="stage45_plot.png"):
    """ブロックしない描画。既定は保存のみ。"""
    plt.figure(figsize=(8, 4.5))
    plt.plot(xs, ys, lw=1)
    plt.xlabel("Step")
    plt.ylabel("Value")
    plt.title(title)
    plt.grid(True)
    plt.tight_layout()

    # まず保存（常に非ブロッキング）
    plt.savefig(save_path, dpi=150)
    print(f"[PLOT] saved: {save_path}", flush=True)

    # 画面表示が必要な場合でもブロックしない
    if show:
        try:
            plt.show(block=False)
            plt.pause(0.2)  # ほんの少し描画時間
        except Exception as e:
            print(f"[PLOT] show skipped ({e})", flush=True)
    plt.close()


# =============================== main ===============================

def main():
    print("[BOOT] stage45 starting...", flush=True)

    # 1) （任意）Qiskitデモを動かす場合は軽量設定で
    _ = run_qiskit_demo(n_circs=30, shots=128)  # 無ければ自動スキップ

    # 2) 本計算
    xs, ys = run_stage45(N=120_000, progress_every=4_000)

    # 3) 可視化（保存が既定。画面表示したいなら show=True）
    plot_and_finish(xs, ys, title="Stage45 Random Walk (demo)", show=False)

    print("[DONE] stage45 finished.", flush=True)
    # ハング監視停止
    faulthandler.cancel_dump_traceback_later()


# ---- macOS のフリーズ回避：必ずガードを付ける ----
if __name__ == "__main__":
    main()

