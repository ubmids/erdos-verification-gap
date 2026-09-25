"""All numbers and figures for "Faster Than They Can Be Checked". Reads data/, writes results.json and figures/."""
import collections, csv, glob, json, re
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

D = Path(__file__).parent / "data"
FIG = Path(__file__).parent / "figures"; FIG.mkdir(exist_ok=True)
CUTOFF = datetime(2026, 9, 25, tzinfo=timezone.utc)   # data collection date
LEDGER_FREEZE = datetime(2026, 6, 30, tzinfo=timezone.utc)

SURFACE, INK, INK2, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#8a8984", "#e6e5e0"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
plt.rcParams.update({"figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
                     "font.size": 9, "axes.edgecolor": MUTED, "axes.labelcolor": INK2, "xtick.color": INK2,
                     "ytick.color": INK2, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
                     "axes.spines.top": False, "axes.spines.right": False, "legend.frameon": False,
                     "lines.linewidth": 2})

def utc(s, fmt):
    return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)

claims = {c["claim_id"]: c for c in json.load(open(D / "claims.json"))}
table = {int(r["claim_id"]): r for r in csv.DictReader(open(D / "claims_table.csv"))}
coded = {int(r["claim_id"]): r for r in csv.DictReader(open(D / "claims_coded.csv"))}

VERDICT = {"verified_correct", "verified_partial", "already_known", "refuted",
           "misstated_or_technicality", "superseded", "dismissed_in_error"}
rows = []
for cid, c in claims.items():
    t, k = table[cid], coded[cid]
    sub = utc(c["submitted"], "%Y-%m-%d %H:%M:%S")
    vd = utc(k["verdict_date"], "%Y-%m-%d %H:%M") if k["verdict_date"] else None
    tools = c["tools"].lower()
    family = ("GPT-6 Astra" if "astra" in tools or "gpt-6" in tools or "gpt 6" in tools else
              "GPT-5.6" if "5.6" in tools else
              "GPT (other)" if "gpt" in tools or "chatgpt" in tools or "codex" in tools or "openai" in tools else
              "Claude / Fable" if "claude" in tools or "fable" in tools or "opus" in tools else
              "Gemini" if "gemini" in tools else ("none" if not tools else "other"))
    rows.append({"id": cid, "problem": c["problem"], "kind": c["kind"], "submitted": sub, "verdict": k["verdict"],
                 "has_verdict": k["verdict"] in VERDICT, "verdict_date": vd, "accepted": t["accepted"] == "True",
                 "lean": t["lean"] == "True", "was_open": t["was_open"] == "True", "family": family,
                 "tags": t["tags"].split(";") if t["tags"] else [], "n_comments": int(c["n_comments"])})

R = {}
def pct(a, b): return round(100 * a / b, 1) if b else None

# ── 1. funnel ───────────────────────────────────────────────────────────────
op = [r for r in rows if r["was_open"]]
R["n_claims"] = len(rows); R["n_on_open"] = len(op)
R["ai_share_pct"] = pct(sum(bool(claims[r["id"]]["tools"]) for r in rows), len(rows))
R["lean_share_pct"] = pct(sum(r["lean"] for r in rows), len(rows))
R["funnel_open"] = {
    "claims": len(op),
    "any_comment": sum(r["n_comments"] > 0 for r in op),
    "any_verdict": sum(r["has_verdict"] for r in op),
    "verified": sum(r["verdict"] in ("verified_correct", "verified_partial") for r in op),
    "accepted_by_moderators": sum(r["accepted"] for r in op),
}
R["verdict_counts_all"] = dict(collections.Counter(r["verdict"] for r in rows))
R["verdict_by_kind_open"] = {k: dict(collections.Counter(r["verdict"] for r in op if r["kind"] == k))
                             for k in ("full", "partial")}

# ── 2. time to verdict (Kaplan–Meier, censored at the cutoff) ───────────────
def km(sample):
    ev = sorted(((r["verdict_date"] - r["submitted"]).total_seconds() / 86400 if r["has_verdict"] and r["verdict_date"]
                 else (CUTOFF - r["submitted"]).total_seconds() / 86400,
                 bool(r["has_verdict"] and r["verdict_date"])) for r in sample)
    s, n, out = 1.0, len(ev), [(0.0, 1.0)]
    for d, e in ev:
        if e:
            s *= (n - 1) / n
            out.append((d, s))
        n -= 1
    # extend the last step to the longest follow-up, so the plateau is drawn in full
    out.append((max(d for d, _ in ev), out[-1][1]))
    return out, ev
curve, ev = km(op)
R["km_prob_no_verdict_at"] = {f"{d}d": round(next((s for t_, s in reversed(curve) if t_ <= d), 1.0), 3)
                              for d in (7, 30, 60)}
lat = sorted(d for d, e in ev if e)
R["days_to_verdict_among_verdicts"] = {"n": len(lat), "median": round(lat[len(lat) // 2], 1) if lat else None,
                                       "p75": round(lat[3 * len(lat) // 4], 1) if lat else None}
R["open_claims_waiting_at_cutoff"] = sum(1 for d, e in ev if not e)
R["verdicts_without_date"] = sum(1 for r in op if r["has_verdict"] and not r["verdict_date"])
R["median_wait_of_waiting_days"] = round(sorted(d for d, e in ev if not e)[len([1 for d, e in ev if not e]) // 2], 1)

# ── 3. correlates ───────────────────────────────────────────────────────────
def rate(group):
    return {"n": len(group), "verdict_pct": pct(sum(r["has_verdict"] for r in group), len(group)),
            "verified_pct": pct(sum(r["verdict"] in ("verified_correct", "verified_partial") for r in group), len(group)),
            "no_comment_pct": pct(sum(r["n_comments"] == 0 for r in group), len(group))}
R["by_lean"] = {"with_lean": rate([r for r in op if r["lean"]]), "without_lean": rate([r for r in op if not r["lean"]])}
R["by_kind"] = {k: rate([r for r in op if r["kind"] == k]) for k in ("full", "partial")}
R["by_family"] = {f: rate([r for r in op if r["family"] == f]) for f in sorted({r["family"] for r in op})}
top_tags = [t for t, _ in collections.Counter(t for r in op for t in r["tags"]).most_common(6)]
R["by_tag"] = {t: rate([r for r in op if t in r["tags"]]) for t in top_tags}

# ── 4. ledger (tracked by problem across restructures) ─────────────────────
events = json.load(open(D / "ledger_events.json"))
state = {}
for e in sorted(events, key=lambda e: e["when"]):
    if e["event"] in ("added", "changed") and e.get("colour"):
        p = e["problem"]; t = datetime.fromisoformat(e["when"])
        st = state.setdefault(p, {"first": t, "first_colour": e["colour"], "resolved": None})
        if st["first_colour"] == "⚪" and e["colour"] in "🟢🟡🔴" and st["resolved"] is None:
            st["resolved"] = (t, e["colour"])
white = {p: s for p, s in state.items() if s["first_colour"] == "⚪"}
R["ledger"] = {"problems_with_coloured_entries": len(state), "entered_unverified": len(white),
               "resolved_before_freeze": sum(1 for s in white.values() if s["resolved"]),
               "resolved_colours": dict(collections.Counter(s["resolved"][1] for s in white.values() if s["resolved"])),
               "final_colours_primary": dict(collections.Counter(r["colour"] or "none" for r in
                                             json.load(open(D / "ledger_final.json")) if r["section"].startswith("1")))}

# ── 5. LLM Hunter review funnel ─────────────────────────────────────────────
H = "data/llm-hunter"
attempts = glob.glob(str(D / "llm-hunter/attacks/erdos/*/*.tex"))
reviews = [json.load(open(f)) for f in glob.glob(str(D / "llm-hunter/reviews/erdos/*.json"))]
norm = lambda l: "technicality" if "technicality" in (l or "").lower() else (l or "").lower()
R["llm_hunter"] = {"attempts": len(attempts), "models": len({Path(a).parent.name for a in attempts}),
                   "reviews": len(reviews), "review_labels": dict(collections.Counter(norm(x.get("label")) for x in reviews))}

# ── 6. baseline: problems moving from open to solved, per month ────────────
sc = json.load(open(D / "status_changes.json"))
solvedw = lambda s: bool(s) and s.split(" ")[0] in ("proved", "disproved", "solved")
per_month = collections.Counter(s["date"][:7] for s in sc if solvedw(s["to"]) and not solvedw(s["from"]))
R["open_to_solved_per_month"] = dict(sorted(per_month.items()))
R["claims_per_month"] = dict(sorted(collections.Counter(r["submitted"].strftime("%Y-%m") for r in rows).items()))

json.dump(R, open(Path(__file__).parent / "results.json", "w"), indent=1, default=str)

# ── figures ─────────────────────────────────────────────────────────────────
# F1 verification debt: cumulative claims on open problems vs cumulative verdicts
days = sorted({r["submitted"].date() for r in op} | {r["verdict_date"].date() for r in op if r["has_verdict"] and r["verdict_date"]})
cum_c = [sum(r["submitted"].date() <= d for r in op) for d in days]
cum_v = [sum(bool(r["has_verdict"] and r["verdict_date"] and r["verdict_date"].date() <= d) for r in op) for d in days]
fig, ax = plt.subplots(figsize=(5.4, 3.3))
ax.plot(days, cum_c, color=BLUE, label="proof claims on open problems")
ax.plot(days, cum_v, color=ORANGE, label="claims that reached a dated verdict")
ax.fill_between(days, cum_v, cum_c, color=BLUE, alpha=0.08, lw=0)
ax.text(days[-1], (cum_c[-1] + cum_v[-1]) / 2, f"  {cum_c[-1] - cum_v[-1]}\n  waiting", color=INK2, fontsize=8, va="center")
ax.set_ylabel("cumulative count"); ax.legend(loc="upper left", fontsize=8)
ax.set_title("Verification debt on erdosproblems.com, Jul–Sep 2026", fontsize=9, color=INK, loc="left")
fig.autofmt_xdate(); fig.tight_layout(); [fig.savefig(FIG / f"fig1_debt.{e}", dpi=300) for e in ("png", "pdf")]; plt.close(fig)

# F2 Kaplan–Meier: probability a claim still has no verdict
fig, ax = plt.subplots(figsize=(5.4, 3.3))
xs, ys = zip(*curve); ax.step(xs, ys, where="post", color=BLUE)
ax.set_ylim(0, 1.02); ax.set_xlabel("days since the claim was posted"); ax.set_ylabel("share of claims with no verdict yet")
ax.set_title("Most claims never get a verdict (Kaplan–Meier, censored at 25 Sep 2026)", fontsize=9, color=INK, loc="left")
fig.tight_layout(); [fig.savefig(FIG / f"fig2_survival.{e}", dpi=300) for e in ("png", "pdf")]; plt.close(fig)

# F3 funnel
f = R["funnel_open"]; labels = ["proof claims\n(open problems)", "got any\ncomment", "reached any\nverdict", "verified\n(any reviewer)", "accepted by\nmoderators"]
vals = [f["claims"], f["any_comment"], f["any_verdict"], f["verified"], f["accepted_by_moderators"]]
fig, ax = plt.subplots(figsize=(5.4, 3.0))
bars = ax.barh(range(len(vals))[::-1], vals, color=BLUE, height=0.6)
for b, v in zip(bars, vals):
    ax.text(v + 2, b.get_y() + b.get_height() / 2, f"{v}  ({pct(v, vals[0])}%)", va="center", color=INK, fontsize=8)
ax.set_yticks(range(len(vals))[::-1], labels); ax.grid(axis="y", visible=False); ax.set_xlim(0, vals[0] * 1.25)
ax.set_title("From claim to verdict", fontsize=9, color=INK, loc="left")
fig.tight_layout(); [fig.savefig(FIG / f"fig3_funnel.{e}", dpi=300) for e in ("png", "pdf")]; plt.close(fig)

print(json.dumps(R, indent=1, default=str))
