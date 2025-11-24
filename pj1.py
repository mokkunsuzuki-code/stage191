# pj1_e91_qkd.py
"""
PJ1: E91-based educational QKD pipeline (EPR, CHSH+Clopper-Pearson, simple EC, Toeplitz PA, OTP demo)
- Author: ChatGPT (education / prototype)
- Note: This is NOT a formal security proof. For production, use formal finite-size security analysis.
"""

import math
import numpy as np
from qiskit import QuantumCircuit, transpile
from qiskit_aer import AerSimulator
from scipy.stats import beta
import hashlib
import secrets

# ------------------------------
# Utility: Clopper-Pearson interval for binomial proportion
# returns (lower, upper) for confidence level 1-alpha
def clopper_pearson(k, n, alpha=0.05):
    """
    k: successes, n: trials
    returns (lower, upper) for (1-alpha) confidence
    """
    if n == 0:
        return 0.0, 1.0
    lower = 0.0 if k == 0 else beta.ppf(alpha/2, k, n-k+1)
    upper = 1.0 if k == n else beta.ppf(1-alpha/2, k+1, n-k)
    return lower, upper

# ------------------------------
# Qiskit-based EPR measurement (single-shot)
sim = AerSimulator()

def measure_epr_once(theta_a: float, theta_b: float, p_flip=0.0):
    """
    Generate |Phi+> and measure Alice at theta_a, Bob at theta_b.
    Simple classical bit-flip noise p_flip applied independently to each measured bit.
    Returns (a_bit, b_bit).
    """
    qc = QuantumCircuit(2, 2)
    # create |Phi+> = (|00> + |11>)/sqrt(2)
    qc.h(0)
    qc.cx(0, 1)
    # rotate measurement basis: apply RY(-2*theta) then measure Z
    if theta_a != 0.0:
        qc.ry(-2*theta_a, 0)
    if theta_b != 0.0:
        qc.ry(-2*theta_b, 1)
    qc.measure(0, 0)
    qc.measure(1, 1)
    tqc = transpile(qc, sim, optimization_level=0)
    result = sim.run(tqc, shots=1, memory=True).result()
    mem = result.get_memory()[0]  # string like 'ab'
    a = int(mem[0])
    b = int(mem[1])
    # classical bit-flip noise
    if p_flip > 0.0:
        if np.random.random() < p_flip:
            a ^= 1
        if np.random.random() < p_flip:
            b ^= 1
    return a, b

# ------------------------------
# CHSH bookkeeping helpers
def make_bucket():
    return {"n00":0, "n01":0, "n10":0, "n11":0, "N":0}

def E_from_bucket(b):
    if b["N"] == 0:
        return 0.0
    return (b["n00"] + b["n11"] - b["n01"] - b["n10"]) / b["N"]

# ------------------------------
# Toeplitz privacy amplification (bit arrays)
def toeplitz_hash(bit_array, out_len, seed_bytes=None):
    """
    bit_array: numpy array of 0/1 bits (length L)
    out_len: desired output bits
    seed_bytes: optional bytes for deterministic Toeplitz generator (if None, uses secrets.token_bytes)
    Implementation: build Toeplitz matrix via first column and first row technique.
    Complexity O(L * out_len) naive; ok for moderate sizes.
    """
    L = len(bit_array)
    if seed_bytes is None:
        seed_bytes = secrets.token_bytes((L + out_len + 7)//8)
    # generate first column (length L) and first row (length out_len) but first element duplicated
    rng = np.frombuffer(hashlib.sha256(seed_bytes + b'0').digest(), dtype=np.uint8)
    # use a deterministic RNG expanded via SHA256 chaining to produce bits:
    needed = L + out_len - 1
    buf = bytearray()
    i = 0
    while len(buf) * 8 < needed:
        h = hashlib.sha256(seed_bytes + i.to_bytes(4, 'big')).digest()
        buf.extend(h)
        i += 1
    bits = np.unpackbits(np.frombuffer(bytes(buf), dtype=np.uint8))
    first_col = bits[:L]
    first_row = bits[L-1:L-1+out_len]
    # Toeplitz multiplication mod 2
    out = np.zeros(out_len, dtype=np.uint8)
    # naive convolution-like computation
    for j in range(out_len):
        total = 0
        for i_bit in range(L):
            # Toeplitz element T[j,i] = first_col[i] if j==0? index transform:
            # T[j,i] corresponds to first_col[i - j] if (i - j) >=0 else first_row[j - i]
            idx = i_bit - j
            if idx >= 0:
                t = first_col[idx]
            else:
                t = first_row[-idx - 1]
            total ^= (bit_array[i_bit] & t)
        out[j] = total
    return out, seed_bytes

# ------------------------------
# Simple parity-based error correction (interactive simulation)
def simple_parity_ec(alice_bits, bob_bits, block_size=32):
    """
    A very simplified interactive error-correction:
    - Partition bits into blocks of block_size
    - For each block, reveal parity (cost = 1 bit) and if parity differs, binary-search to find one differing bit (cost ~ log2(block_size))
    - Returns corrected bob_bits, and leaked_bits count
    This is not CASCADE but gives an estimate of leak_EC (in bits).
    """
    n = len(alice_bits)
    alice = alice_bits.copy()
    bob = bob_bits.copy()
    leaked = 0
    if n == 0:
        return bob, leaked
    nb = math.ceil(n / block_size)
    for bi in range(nb):
        start = bi * block_size
        end = min(n, start + block_size)
        a_block = alice[start:end]
        b_block = bob[start:end]
        parity_a = int(np.sum(a_block) % 2)
        parity_b = int(np.sum(b_block) % 2)
        leaked += 1  # parity revelation (1 bit)
        if parity_a != parity_b:
            # binary search to locate a differing index
            lo = start
            hi = end
            # We'll reveal parities of halves iteratively - each reveal costs 1 bit
            while hi - lo > 1:
                mid = (lo + hi) // 2
                p_a = int(np.sum(alice[lo:mid]) % 2)
                p_b = int(np.sum(bob[lo:mid]) % 2)
                leaked += 1
                if p_a != p_b:
                    # difference in left half
                    hi = mid
                else:
                    lo = mid
            # flip bob bit at position lo to correct
            bob[lo] ^= 1
    return bob, leaked

# ------------------------------
# Core experiment run: single set of parameters
def run_e91_protocol(N_pairs=2000, key_fraction=0.3, p_flip=0.0, alpha=0.05, block_size_ec=32):
    """
    Runs E91 educational experiment with given params:
    - Splits attempts into key vs test according to key_fraction
    Returns dict with S, S_LB, qber, key_bits (alice,bob), leak_EC, final_key (after PA)
    """
    # angles for CHSH (standard)
    a0 = 0.0
    a1 = math.pi / 4
    b0 = math.pi / 8
    b1 = -math.pi / 8
    bucket_map = {
        0: (a0, b0),
        1: (a0, b1),
        2: (a1, b0),
        3: (a1, b1)
    }
    b_a0b0 = make_bucket()
    b_a0b1 = make_bucket()
    b_a1b0 = make_bucket()
    b_a1b1 = make_bucket()
    buckets = [b_a0b0, b_a0b1, b_a1b0, b_a1b1]
    key_alice = []
    key_bob = []
    # Run pair generation and measurements
    for _ in range(N_pairs):
        if np.random.random() < key_fraction:
            # key measurement (same basis)
            a, b = measure_epr_once(0.0, 0.0, p_flip=p_flip)
            key_alice.append(a)
            key_bob.append(b)
        else:
            idx = np.random.randint(0, 4)
            th_a, th_b = bucket_map[idx]
            a, b = measure_epr_once(th_a, th_b, p_flip=p_flip)
            ba = buckets[idx]
            if a == 0 and b == 0:
                ba["n00"] += 1
            elif a == 0 and b == 1:
                ba["n01"] += 1
            elif a == 1 and b == 0:
                ba["n10"] += 1
            else:
                ba["n11"] += 1
            ba["N"] += 1
    # compute S
    E00 = E_from_bucket(b_a0b0)
    E01 = E_from_bucket(b_a0b1)
    E10 = E_from_bucket(b_a1b0)
    E11 = E_from_bucket(b_a1b1)
    S = E00 + E01 + E10 - E11
    # For each bucket compute the lower/upper for each joint-prob component
    # We'll estimate S_LB using worst-case within Clopper-Pearson intervals:
    # Convert each E to a function of counts: E = (n00 + n11 - n01 - n10)/N
    # For conservative LB of E, use lower bound for (n00+n11) and upper bound for (n01+n10)
    def E_lower_from_bucket(b, alpha_local=alpha):
        N = b["N"]
        if N == 0:
            return 0.0
        # successes for "same" = n00 + n11
        same = b["n00"] + b["n11"]
        diff = b["n01"] + b["n10"]
        same_L, _ = clopper_pearson(same, N, alpha_local)
        _, diff_U = clopper_pearson(diff, N, alpha_local)
        return (same_L - diff_U) / N
    E00_L = E_lower_from_bucket(b_a0b0)
    E01_L = E_lower_from_bucket(b_a0b1)
    E10_L = E_lower_from_bucket(b_a1b0)
    E11_U = None
    # For the last term E11 appears with minus sign in S = E00+E01+E10-E11
    # Conservative LB for S is E00_L + E01_L + E10_L - E11_U (where E11_U is upper bound for E11)
    def E_upper_from_bucket(b, alpha_local=alpha):
        N = b["N"]
        if N == 0:
            return 0.0
        same = b["n00"] + b["n11"]
        diff = b["n01"] + b["n10"]
        _, same_U = clopper_pearson(same, N, alpha_local)
        diff_L, _ = clopper_pearson(diff, N, alpha_local)
        return (same_U - diff_L) / N
    E11_U = E_upper_from_bucket(b_a1b1)
    S_LB = E00_L + E01_L + E10_L - E11_U

    # Key stats: QBER
    key_alice = np.array(key_alice, dtype=np.uint8)
    key_bob = np.array(key_bob, dtype=np.uint8)
    n_key = len(key_alice)
    if n_key == 0:
        qber = 0.5
    else:
        qber = 1.0 - np.mean(key_alice == key_bob)

    # Error correction (simple parity EC): simulate and compute leak_EC
    corrected_bob, leak_ec = simple_parity_ec(key_alice.copy(), key_bob.copy(), block_size=block_size_ec)
    # Recompute QBER after correction
    if n_key > 0:
        qber_after = 1.0 - np.mean(key_alice == corrected_bob)
    else:
        qber_after = qber

    # Privacy amplification: conservative final key length estimate (education model)
    # We compute a conservative multiplier from S_LB mapping to "confidence" in entanglement:
    # map S_LB in [2, 2*sqrt(2)] to factor in [0,1]
    S_clamped = max(2.0, min(S_LB, 2.0*math.sqrt(2)))
    conf = (S_clamped - 2.0) / (2.0*math.sqrt(2) - 2.0)
    # estimate of information per bit leaked to Eve approximated by binary entropy of qber_after
    info_leak_per_bit = h2 = lambda p: 0.0 if p <= 0 or p >= 1 else -p*math.log2(p) - (1-p)*math.log2(1-p)
    # estimated secure fraction
    secure_fraction = max(0.0, conf * max(0.0, 1.0 - info_leak_per_bit(qber_after)))
    # final key length (bits) after PA (conservative) subtracting leak_ec
    final_key_bits = max(0, int(math.floor(n_key * secure_fraction) - leak_ec))
    # perform Toeplitz PA if final_key_bits>0
    final_key = np.array([], dtype=np.uint8)
    toeplitz_seed = None
    if final_key_bits > 0:
        # derive PA input as the corrected bob (or alice) bits
        pa_input = key_alice  # both should match after EC
        final_key, toeplitz_seed = toeplitz_hash(pa_input, final_key_bits)
    # return results and metadata
    return {
        "N_pairs": N_pairs,
        "key_fraction": key_fraction,
        "n_key": n_key,
        "qber_before": qber,
        "qber_after": qber_after,
        "S": S,
        "S_LB": S_LB,
        "leak_EC": leak_ec,
        "secure_fraction": secure_fraction,
        "final_key_bits": final_key_bits,
        "final_key": final_key,
        "toeplitz_seed": toeplitz_seed
    }

# ------------------------------
# Demo runner and OTP test
def demo_run_and_otp():
    # Parameters (you can tune these)
    N_pairs = 4000
    key_fraction = 0.30
    p_flip = 0.001   # small simulated noise
    alpha = 0.01     # 99% confidence for Clopper-Pearson
    block_size_ec = 32

    print("PJ1 Demo: running E91 educational experiment")
    res = run_e91_protocol(N_pairs=N_pairs, key_fraction=key_fraction, p_flip=p_flip, alpha=alpha, block_size_ec=block_size_ec)

    print(f"N_pairs={res['N_pairs']}, key_fraction={res['key_fraction']:.3f}, n_key={res['n_key']}")
    print(f"S (point est) = {res['S']:.4f}, S_LB (alpha={alpha}) = {res['S_LB']:.4f}")
    print(f"QBER before EC = {res['qber_before']:.4f}, after EC = {res['qber_after']:.4f}")
    print(f"leak_EC (bits) = {res['leak_EC']}")
    print(f"secure_fraction (conservative est) = {res['secure_fraction']:.4f}")
    print(f"final_key_bits = {res['final_key_bits']}")

    if res['final_key_bits'] > 0:
        # OTP demo: encrypt a short message using final_key (as bytes)
        # Convert bit-array to bytes
        bits = res['final_key']
        # pack bits to bytes
        bytelist = []
        for i in range(0, len(bits), 8):
            b = 0
            for j in range(8):
                if i+j < len(bits):
                    b = (b << 1) | int(bits[i+j])
                else:
                    b = (b << 1)
            bytelist.append(b)
        key_bytes = bytes(bytelist)
        msg = b"HELLO-QKD-PJ1"
        # one-time pad: XOR msg with key stream (repeated if key shorter)
        stream = (key_bytes * ((len(msg) // len(key_bytes)) + 1))[:len(msg)]
        cipher = bytes([m ^ s for m, s in zip(msg, stream)])
        recovered = bytes([c ^ s for c, s in zip(cipher, stream)])
        print("OTP demo:")
        print("plaintext:", msg)
        print("cipher(hex):", cipher.hex())
        print("recovered:", recovered)
    else:
        print("No final key generated; OTP demo skipped.")

if __name__ == "__main__":
    demo_run_and_otp()

