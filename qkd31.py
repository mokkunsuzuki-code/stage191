# qkd31_chsh_pass_rate.py
# 段階31：CHSH 不合格率の統計シミュレーション
# - 衛星ごとのパスを多数サンプルして、S_LB > 2 となる割合を調べる
# - N_sat や N_chsh による依存性をグラフ化

import math
import numpy as np
import matplotlib.pyplot as plt

try:
    from scipy.stats import beta as sp_beta
    HAVE_SCIPY = True
except Exception:
    HAVE_SCIPY = False

# ===== Utility =====
def clopper_pearson_interval(k, n, alpha=1e-3):
    if n == 0: return (0.0, 1.0)
    if HAVE_SCIPY:
        lo = 0.0 if k == 0 else float(sp_beta.ppf(alpha/2, k, n-k+1))
        hi = 1.0 if k == n else float(sp_beta.ppf(1-alpha/2, k+1, n-k))
        return (lo, hi)
    # Wilson近似
    p = k/n; z=3.29
    denom = 1+z*z/n
    center=(p+z*z/(2*n))/denom
    half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/denom
    return (max(0, center-half), min(1, center+half))

def h2(x):
    if x<=0 or x>=1: return 0.0
    return -(x*math.log2(x)+(1-x)*math.log2(1-x))

# ===== CHSH finite-size LB =====
def chsh_mismatch_prob(base_match, p_noise):
    return (1.0-base_match)+p_noise*(2*base_match-1.0)

def chsh_lower_bound_for_pass(N_chsh, p_noise=0.03, alpha=1e-3, rng=None):
    if N_chsh<=0: return -1e9
    if rng is None: rng=np.random.default_rng()
    n00=n01=n10=n11=N_chsh//4
    for _ in range(N_chsh-4*(N_chsh//4)):
        n00+=1
    q_pos=chsh_mismatch_prob(0.85,p_noise)
    q_neg=chsh_mismatch_prob(0.15,p_noise)
    k00=rng.binomial(n00,q_pos)
    k01=rng.binomial(n01,q_pos)
    k10=rng.binomial(n10,q_pos)
    k11=rng.binomial(n11,q_neg)
    _,qU00=clopper_pearson_interval(k00,n00,alpha)
    _,qU01=clopper_pearson_interval(k01,n01,alpha)
    _,qU10=clopper_pearson_interval(k10,n10,alpha)
    qL11,_=clopper_pearson_interval(k11,n11,alpha)
    E00_LB=1-2*qU00
    E01_LB=1-2*qU01
    E10_LB=1-2*qU10
    E11_UB=1-2*qL11
    return E00_LB+E01_LB+E10_LB-E11_UB

# ===== Experiment =====
def estimate_pass_rate(N_chsh, n_trials=5000, p_noise=0.03, alpha=1e-3, seed=1234):
    rng=np.random.default_rng(seed)
    count=0
    for _ in range(n_trials):
        S_LB=chsh_lower_bound_for_pass(N_chsh,p_noise,alpha,rng)
        if S_LB>2.0:
            count+=1
    return count/n_trials

def main():
    # サンプル数ごとの合格率
    N_chsh_values=[100,300,1000,3000,10000]
    rates=[]
    for N in N_chsh_values:
        r=estimate_pass_rate(N,n_trials=5000)
        rates.append(r)
        print(f"N_chsh={N}: pass rate={r*100:.1f}%")

    plt.figure(figsize=(7,5))
    plt.plot(N_chsh_values,rates,marker='o')
    plt.xscale("log")
    plt.xlabel("CHSH samples per pass (log scale)")
    plt.ylabel("Pass rate (S_LB>2)")
    plt.title("CHSH pass probability vs sample size")
    plt.grid(True)
    plt.show()

if __name__=="__main__":
    main()
