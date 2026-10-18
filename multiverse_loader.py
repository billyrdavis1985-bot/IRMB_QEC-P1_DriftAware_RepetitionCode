"""QEC-P1 4.3 multiverse -- data loader (final). Reuses qec.analyze.enc_pL."""
import json
try:
    from qec.analyze import enc_pL          # study's own decode (authoritative)
except Exception:
    enc_pL = None

def deploy_key(patch):
    return f"deploy|{tuple(patch)}|ENC_ACTIVE"

def patch_id(patch):
    return "-".join(map(str, patch))

def load_window(path, day, enc_pL_fn=None):
    fn = enc_pL_fn or enc_pL
    if fn is None:
        raise RuntimeError("qec.analyze.enc_pL not importable; run in-repo or pass enc_pL_fn.")
    with open(path, encoding="utf-8") as f:
        blob = json.load(f)
    stamp, counts = blob["stamp"], blob["counts"]
    state = int(stamp["state"])
    recs = []
    for patch in stamp["candidates"]:
        c = counts.get(deploy_key(patch))
        if not c:
            raise KeyError(f"missing/empty ENC_ACTIVE counts for {deploy_key(patch)}")
        k, n = fn(c, state, False)          # False == ENC_ACTIVE (final-data majority)
        recs.append(dict(patch_id=patch_id(patch), day=day, state=str(state),
                         err=int(k), n=int(n)))
    return recs
