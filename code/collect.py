"""Collect every Erdős problem page, every proof claim, and every claim's comment thread.
Polite: one request per 1.2 s, with everything cached on disk so a rerun only fetches what is missing."""
import html, json, os, re, time, urllib.request, yaml

ROOT = os.path.expanduser("~/Desktop/erdos")
BASE = "https://www.erdosproblems.com"
UA = {"User-Agent": "Mozilla/5.0 (research; contact subomi)"}

def get(url, path, xhr=False):
    if os.path.exists(path) and os.path.getsize(path) > 200:
        return open(path, encoding="utf-8", errors="replace").read()
    h = dict(UA)
    if xhr:
        h["X-Requested-With"] = "XMLHttpRequest"
    for attempt in range(3):
        try:
            data = urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=30).read()
            open(path, "wb").write(data)
            time.sleep(1.2)
            return data.decode("utf-8", "replace")
        except Exception as e:
            print("retry", url, e, flush=True); time.sleep(5 * (attempt + 1))
    return ""

def text(s):
    s = re.sub(r"<script.*?</script>|<style.*?</style>", "", s, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()

ps = yaml.safe_load(open(f"{ROOT}/db/data/problems.yaml"))
problems, claims = {}, []
for i, p in enumerate(ps):
    n = p["number"]
    s = get(f"{BASE}/{n}", f"{ROOT}/pages/{n}.html")
    t = text(s)
    g = lambda pat: int(m.group(1)) if (m := re.search(pat, t)) else 0
    label = (m.group(1) if (m := re.search(r"Random Open\s+([A-Z][A-Z ()-]+?)\s+(?:Resolved|Let|Is|Are|Does|Do|Can|What|Show|Prove|Find|For|If|Suppose|There|How|Must|A |An |The |Let's)", t)) else "")
    problems[n] = {"db_status": p["status"]["state"], "tags": p.get("tags", []), "prize": p.get("prize"),
                   "page_label": label.strip(), "comments": g(r"Comments \((\d+)\)"),
                   "proof_claims": g(r"Proof claims \((\d+)\)"),
                   "edited": (m.group(1) if (m := re.search(r"last edited (\d{1,2} \w+ \d{4})", t)) else "")}
    if problems[n]["proof_claims"]:
        cs = get(f"{BASE}/forum/thread/{n}/proof-claims", f"{ROOT}/claims/{n}.html")
        for art in re.findall(r'<article\s+class="proof-claim"\s+id="proof-claim-(\d+)"\s*>(.*?)</article>', cs, flags=re.S):
            cid, body = art
            head = text(re.search(r"<p>\s*A\s+<b>.*?</p>", body, flags=re.S).group(0)) if re.search(r"<p>\s*A\s+<b>", body) else ""
            style = (m.group(1) if (m := re.search(r'<li class="post[^"]*"\s+style="([^"]*)"', body)) else "")
            links = re.findall(r'href="([^"]+)"[^>]*>\s*External link to (proof|formalisation)', body)
            sub = re.search(r"Submitted\s+(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+by\s*<a href=\"/forum/user/([^\"]+)\"", body)
            summ = re.search(r"<strong>Summary:</strong>(.*?)</p>", body, flags=re.S)
            notes = re.search(r"<strong>Notes:</strong>(.*?)</p>", body, flags=re.S)
            ncom = (int(m.group(1)) if (m := re.search(r"Comments \((\d+)\)", body)) else 0)
            com_html = get(f"{BASE}/forum/proof-claims/{cid}/comments", f"{ROOT}/comments/{cid}.html", xhr=True) if ncom else ""
            claims.append({
                "claim_id": int(cid), "problem": n, "header": head, "style": style,
                "kind": (m.group(1) if (m := re.search(r"A\s+(\w+)\s+proof", head)) else ""),
                "tools": (m.group(1) if (m := re.search(r"\(using (.*?)\)\.?$", head)) else ""),
                "submitted": sub.group(1) if sub else "", "user": sub.group(2) if sub else "",
                "summary": text(summ.group(1)) if summ else "", "notes": text(notes.group(1)) if notes else "",
                "links": [{"kind": k, "url": u} for u, k in links], "n_comments": ncom,
                "comments_text": text(com_html)[:20000] if com_html else "",
            })
    if (i + 1) % 50 == 0:
        print(i + 1, "problems,", len(claims), "claims", flush=True)
        json.dump(problems, open(f"{ROOT}/paper/data/problems_pages.json", "w"))
        json.dump(claims, open(f"{ROOT}/paper/data/claims.json", "w"))
json.dump(problems, open(f"{ROOT}/paper/data/problems_pages.json", "w"))
json.dump(claims, open(f"{ROOT}/paper/data/claims.json", "w"))
print("finished", len(problems), "problems,", len(claims), "claims", flush=True)
