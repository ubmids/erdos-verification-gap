"""Tao's AI-contributions ledger: the final table, plus every outcome change over its git history."""
import json, re, subprocess
W, F = "wiki", "AI-contributions-to-Erdős-problems.md"
ROW = re.compile(r"^\|\s*\[\[(\d+)\]\][^|]*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|\s*(.*?)\s*\|?\s*$")

def parse(md):
    rows, sect = [], None
    for line in md.split("\n"):
        m = re.match(r"^###\s+(\d\([a-d]\))", line)
        if m:
            sect = m.group(1); continue
        m = ROW.match(line)
        if m and sect:
            n, ai, date, outcome = m.groups()
            colour = next((c for c in "🟢🟡🔴⚪" if c in outcome), "")
            rows.append({"section": sect, "problem": n, "ai": ai, "date": date,
                         "outcome": re.sub(r"[🟢🟡🔴⚪]", "", outcome).strip(), "colour": colour,
                         "lean": "(Lean)" in outcome})
    return rows

final = parse(open(f"{W}/{F}").read())
json.dump(final, open("paper/data/ledger_final.json", "w"), indent=0, ensure_ascii=False)
log = subprocess.run(["git", "-C", W, "log", "--reverse", "--format=%H %aI", "--", F],
                     capture_output=True, text=True).stdout.split("\n")
seen, events = {}, []
for line in filter(None, log):
    sha, when = line.split(" ", 1)
    md = subprocess.run(["git", "-C", W, "show", f"{sha}:{F}"], capture_output=True, text=True).stdout
    cur = {}
    for r in parse(md):
        cur[(r["section"], r["problem"])] = (r["colour"], r["outcome"], r["lean"])
    for k, v in cur.items():
        if k not in seen:
            events.append({"section": k[0], "problem": k[1], "when": when, "event": "added", "colour": v[0], "outcome": v[1], "lean": v[2]})
        elif seen[k] != v:
            events.append({"section": k[0], "problem": k[1], "when": when, "event": "changed",
                           "from": seen[k][0], "colour": v[0], "outcome": v[1], "lean": v[2]})
    for k in set(seen) - set(cur):
        events.append({"section": k[0], "problem": k[1], "when": when, "event": "removed", "from": seen[k][0]})
    seen = cur
json.dump(events, open("paper/data/ledger_events.json", "w"), indent=0, ensure_ascii=False)
import collections
print(len(final), "rows in final ledger;", collections.Counter(r["section"] for r in final))
print("colours:", collections.Counter(r["colour"] for r in final))
print(len(events), "events;", collections.Counter(e["event"] for e in events))
