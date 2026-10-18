SYNDROME_TABLE = {(0,0):None,(1,0):0,(1,1):1,(0,1):2}
def decode_history(history):
    net=[0,0,0]
    for s in history:
        idx=SYNDROME_TABLE[tuple(s)]
        if idx is not None: net[idx]^=1
    return net
def logical_value(data_bits):
    return 1 if sum(data_bits)>=2 else 0
def decode_shot(data_bits,history,apply_corrections):
    bits=list(data_bits)
    if apply_corrections:
        for i,c in enumerate(decode_history(history)):
            bits[i]^=c
    return logical_value(bits)
def enc_pL(counts, state, apply_corrections):
    total=fails=0
    for bitstr,cnt in counts.items():
        f=bitstr.split()
        data_bits=[int(b) for b in f[0][::-1]]
        hist=[(int(x[::-1][0]),int(x[::-1][1])) for x in f[1:][::-1]]
        if decode_shot(data_bits,hist,apply_corrections)!=state: fails+=cnt
        total+=cnt
    return fails,total
