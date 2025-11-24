from qiskit import QuantumCircuit, transpile
from qiskit_aer import AerSimulator

def measure(state, basis='Z'):
    qc = QuantumCircuit(1,1)
    if state == '1': qc.x(0)
    if state == '+': qc.h(0)
    if state == '-': qc.x(0); qc.h(0)
    if basis == 'X': qc.h(0)
    qc.measure(0,0)
    sim = AerSimulator()
    return sim.run(transpile(qc, sim), shots=1000).result().get_counts()

print("Z(|0>)=", measure('0','Z'))
print("Z(|1>)=", measure('1','Z'))
print("X(|+>)=", measure('+','X'))
print("X(|->)=", measure('-','X'))
print("Z(|+>)=", measure('+','Z'))
print("X(|0>)=", measure('0','X'))
