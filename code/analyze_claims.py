"""Per-claim table: problem status when the claim was made, what happened after, and the site's verdict."""
import json, re, subprocess, yaml, csv
from datetime import datetime, timezone
C = json.load(open("data/claims.json")); P = json.load(open("data/problems_pages.json"))
S = sorted(json.load(open("data/status_changes.json")), key=lambda s: s["date"])
SOLVED = ("proved", "disproved", "solved")
def solved(st): return bool(st) and st.split(" ")[0] in SOLVED

# status of every problem at the first commit, then replay changes
first = subprocess.run(["git","-C","../db","log","--reverse","--format=%H","--","data/problems.yaml"],capture_output=True,text=True).stdout.split()[0]
init = {str(p["number"]): (p.get("status",{}) or {}).get("state") if isinstance(p.get("status"),dict) else p.get("status")
        for p in yaml.safe_load(subprocess.run(["git","-C","../db","show",f"{first}:data/problems.yaml"],capture_output=True,text=True).stdout)}
def status_at(n, when):
    st = init.get(n)
    for s in S:
        if s["problem"] != n: continue
        if datetime.fromisoformat(s["date"]) > when: break
        st = s["to"]
    return st
def first_solved_after(n, when):
    for s in S:
        if s["problem"] == n and datetime.fromisoformat(s["date"]) > when and solved(s["to"]) and not solved(s["from"]):
            return datetime.fromisoformat(s["date"])
    return None

REFUTE = re.compile(r"\b(incorrect|wrong|error|flaw(?:ed)?|fails?|false|invalid|gap|counterexample|not (?:a )?(?:valid|correct|proof))\b", re.I)
KNOWN = re.compile(r"\b(already (?:known|solved|proved)|in the literature|previously (?:known|proved|solved)|was (?:proved|solved) (?:by|in))\b", re.I)
rows = []
for c in C:
    n = c["problem"]
    t = datetime.strptime(c["submitted"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    st0 = status_at(n, t)
    fs = first_solved_after(n, t)
    rows.append({
        "claim_id": c["claim_id"], "problem": n, "submitted": c["submitted"], "kind": c["kind"],
        "ai": bool(c["tools"]), "tools": c["tools"],
        "lean": any(l["kind"] == "formalisation" for l in c["links"]),
        "accepted": "8FBC8F" in c["style"], "n_comments": c["n_comments"],
        "status_at_claim": st0, "was_open": not solved(st0),
        "solved_after": fs.isoformat() if fs else "", "days_to_solved": round((fs - t).total_seconds()/86400, 1) if fs else "",
        "status_now": P[n]["db_status"], "tags": ";".join(P[n]["tags"]),
        "comment_refutes": bool(REFUTE.search(c["comments_text"])), "comment_known": bool(KNOWN.search(c["comments_text"])),
    })
with open("data/claims_table.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

import collections
op = [r for r in rows if r["was_open"]]
print(f"claims {len(rows)}: on OPEN problems {len(op)}, on already-solved {len(rows)-len(op)}")
for kind in ("full", "partial"):
    k = [r for r in op if r["kind"] == kind]
    print(f"\n{kind} claims on open problems: {len(k)}")
    print("  accepted (green):", sum(r["accepted"] for r in k))
    print("  problem solved after claim:", sum(bool(r["solved_after"]) for r in k))
    print("  no comments at all:", sum(r["n_comments"] == 0 for r in k))
    print("  comments mention error/gap:", sum(r["comment_refutes"] for r in k), "| mention already known:", sum(r["comment_known"] for r in k))
    print("  with Lean:", sum(r["lean"] for r in k), "| of which accepted:", sum(r["lean"] and r["accepted"] for r in k))
    ds = sorted(r["days_to_solved"] for r in k if r["days_to_solved"] != "")
    if ds: print("  days claim->status change: median", ds[len(ds)//2], "range", ds[0], "-", ds[-1])
