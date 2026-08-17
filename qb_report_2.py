import json
from qec.analyze import bare_pL, enc_pL, wilson

out = json.load(open("runs/qb_supplement_2_result.json"))
counts = out["counts"]
print("=" * 70)
print("Q-B SUPPLEMENT - DURATION-MATCHED BARE (single window)")
print("=" * 70)
for m in out["stamp"]["meta"]:
    dur = m.get("match_duration_dt", m.get("enc_duration_dt"))
    us = m.get("match_duration_us", "")
    print("\n%s %s  matched delay = %s dt (%s us)" % (m["policy"], m["patch"], dur, us))
    for st in (0, 1):
        bares = []
        for k in range(3):
            c = counts.get("%s|BAREMATCH%d|%d" % (m["policy"], k, st))
            if c:
                kk, nn = bare_pL(c, st)
                bares.append(kk / nn)
        if not bares:
            continue
        mb = sum(bares) / len(bares)
        print("  |%d_L>  BARE(matched) each=%s mean=%.4f"
              % (st, [round(x, 4) for x in bares], mb))
        for klass, corr, note in (("ENC_PASSIVE", True, "exactly matched"),
                                  ("ENC_ACTIVE", False, "under-matched by branch time")):
            c = counts.get("%s|%s|%d" % (m["policy"], klass, st))
            if not c:
                continue
            kk, nn = enc_pL(c, st, corr)
            p = kk / nn
            lo, hi = wilson(kk, nn)
            print("         %-12s p_L=%.4f [%.4f, %.4f]  (%s)" % (klass, p, lo, hi, note))
            if p > 0:
                S = mb / p
                print("                      S = %.3f   %s"
                      % (S, "encoding HELPS" if S > 1 else "overhead dominates"))
print("\n" + "=" * 70)
print("LIMITATION: single window, no cross-session replication.")
print("The unmatched S values from sessions 11-14 are VOID.")
print("=" * 70)
m = out.get("metrics")
if m:
    print("metered:", m)

