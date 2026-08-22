import io
p = "PAPER.md"
s = io.open(p, encoding="utf-8").read()
entry = """- **A circuit description was wrong in two places.** The encoded
  circuit was described as carrying nine mid-circuit measurements. It
  carries six — three rounds of two ancilla measurements each — plus three
  terminal measurements of the data qubits. Nine is the total measurement
  count, not the mid-circuit count. Corrected in v1.2. No result depended
  on the figure.
"""
assert entry not in s
s = s.rstrip() + "\n" + entry
io.open(p, "w", encoding="utf-8").write(s)
print("entry added; section 9 now has", s.split("## 9. Errors")[1].count("\n- **"), "entries")
