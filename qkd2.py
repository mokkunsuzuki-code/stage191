import numpy as np
from qiskit import QuantumCircuit, transpile
from qiskit_aer import AerSimulator

N = 128
rng = np.random.default_rng(0)
alice_bits  = rng.integers(0,2,size=N,dtype=np.uint8)
alice_basis = rng.integers(0,2,size=N,dtype=np.uint8)
bob_basis   = rng.integers(0,2,size=N,dtype=np.uint8)

circs = []
for b, ba, bb in zip(alice_bits, alice_basis, bob_basis):
    qc = QuantumCircuit(1,1)
    if b==1: qc.x(0)
    if ba==1:  qc.h(0)
    if bb==1: qc.h(0)
    qc.measure(0,0)
    circs.append(qc)

sim = AerSimulator()
res = sim.run(transpile(circs, sim), shots=1).result()
bob_bits = np.array([ (1 if res.get_counts(i).get('1',0) else 0) for i in range(N) ], dtype=np.uint8)

match = (alice_basis==bob_basis)
same  = np.mean(alice_bits[match] == bob_bits[match]) if match.any() else 0.0
diff  = np.mean(alice_bits[~match]== bob_bits[~match]) if (~match).any() else 0.0
print(f"同基底一致率={same:.2%}, 異基底一致率={diff:.2%}")
