"""Every status change of every Erdős problem, from the community database's git history."""
import json, subprocess, yaml
try:
    Loader = yaml.CSafeLoader
except AttributeError:
    Loader = yaml.SafeLoader
DB = "db"
shas = subprocess.run(["git", "-C", DB, "log", "--reverse", "--format=%H %aI", "--", "data/problems.yaml"],
                      capture_output=True, text=True).stdout.split("\n")
prev, changes = {}, []
for line in filter(None, shas):
    sha, when = line.split(" ", 1)
    raw = subprocess.run(["git", "-C", DB, "show", f"{sha}:data/problems.yaml"], capture_output=True, text=True).stdout
    try:
        ps = yaml.load(raw, Loader=Loader) or []
    except Exception as e:
        print("skip", sha[:8], e); continue
    cur = {}
    for p in ps:
        st = p.get("status", {}).get("state") or p.get("informal_status", {}).get("state") or p.get("status")
        if isinstance(st, dict): st = st.get("state")
        cur[str(p.get("number"))] = st
    for n, st in cur.items():
        if n in prev and prev[n] != st:
            changes.append({"problem": n, "date": when, "from": prev[n], "to": st, "commit": sha[:10]})
    prev = cur
json.dump(changes, open("paper/data/status_changes.json", "w"), indent=0)
print(len(changes), "status changes;", len(prev), "problems at head")
