import io
p = "PAPER.md"
s = io.open(p, encoding="utf-8").read()

a = """spends five physical qubits, twenty-eight two-qubit gates and nine
mid-circuit measurements to protect one logical bit."""
b = """spends five physical qubits, twenty-eight two-qubit gates, six
mid-circuit measurements and six ancilla resets to protect one logical bit."""
assert a in s, "anchor 1 not found"
s = s.replace(a, b, 1)

c = """only a delay and a terminal measurement; encoded circuits add 28
two-qubit gates, 9 mid-circuit measurements and 6 resets."""
d = """only a delay and a terminal measurement; encoded circuits add 28
two-qubit gates, 6 mid-circuit measurements and 6 resets."""
assert c in s, "anchor 2 not found"
s = s.replace(c, d, 1)

io.open(p, "w", encoding="utf-8").write(s)
print("patched")
