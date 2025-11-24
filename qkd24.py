# qkd24_throughput.py
# 段階24：E91 QKD のスループット最適化（bit/s）

import math
import numpy as np

try:
    from scipy.stats import beta as sp_beta
    HAVE_SCIPY=True
except:
    HAVE_SCIPY=False

def h2(x):
    if x<=0 or x>=1: return 0.0
    return -(x*math.log2(x)+(1-x)*math.log2(1-x))

def clopper_pearson_interval(k, n, alpha=1e-3):
    if n==0: return (0.0,1.0)
    if HAVE_SCIPY:
        lo = 0.0 if k==0 else float(sp_beta.ppf(alpha/2, k, n-k+1))
        hi = 1.0 if k==n else float(sp_beta.ppf(1-alpha/2, k+1, n-k))
        return (lo,hi)
    # fallback: Wilson近似
    p = k/n; z=3.29
    denom = 1+z*z/n
    center=(p+z*z/(2*n))/denom
    half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/denom
    return (max(0,center-half), min(1,center+half))

# ==== 物理モデル ====
def eta_fiber(L_km, alpha_db=0.2, eta_det=0.2):
    return eta_det * 10**(-alpha_db*L_km/10)

def eta_satellite(R_km, lambda_nm=850, extra_losses_db=12, eta_det=0.5):
    lambda_m=lambda_nm*1e-9
    R=R_km*1000
    Lfs=20*math.log10(4*math.pi*R/lambda_m)
    Ltot=Lfs+extra_losses_db
    return eta_det*10**(-Ltot/10)

# ==== 鍵率計算（有限サイズ近似） ====
def final_key_length(n_total, q_err, f_ec=1.16, eps_sec=1e-6, alpha=1e-3):
    # サンプルを test=20% にして QBER推定
    testN=int(0.2*n_total)
    keepN=n_total-testN
    # 観測エラー数（期待値で近似）
    k_err=int(q_err*testN)
    _,qU=clopper_pearson_interval(k_err,testN,alpha)
    e_u=qU
    leak_ec=int(math.ceil(f_ec*keepN*h2(q_err)))
    delta=int(math.ceil(2*math.log2(1/eps_sec)))
    m=max(0,int(math.floor(keepN*(1-h2(e_u))-leak_ec-delta)))
    return m

# ==== シミュレーション ====
def simulate_throughput(mode="fiber", L=100, R_pulse=1e7, T=1.0, p_noise=0.03):
    """
    mode: "fiber" (L=km) or "sat" (L=slant range km)
    R_pulse: pulse rate [Hz]
    T:収集時間[秒]
    """
    if mode=="fiber":
        etaA=eta_fiber(L); etaB=eta_fiber(L)
    else:
        etaA=eta_satellite(L); etaB=eta_satellite(L)
    eta_pair=etaA*etaB
    N=int(R_pulse*T*eta_pair)  # 両端に届くペア数
    m=final_key_length(N,p_noise)
    R_key=m/T
    return dict(N=N, m=m, R_key=R_key, eta_pair=eta_pair)

def main():
    R_pulse=1e7; T=1.0; p_noise=0.03
    for L in [50,100,150]:
        res=simulate_throughput("fiber",L,R_pulse,T,p_noise)
        print(f"Fiber {L}km: N={res['N']}, m={res['m']}, throughput={res['R_key']:.1f} bit/s")
    for R in [500,1000,1500]:
        res=simulate_throughput("sat",R,R_pulse,T,p_noise)
        print(f"Satellite {R}km: N={res['N']}, m={res['m']}, throughput={res['R_key']:.1f} bit/s")

if __name__=="__main__":
    main()

