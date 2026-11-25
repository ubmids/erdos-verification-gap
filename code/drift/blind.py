"""Statement-drift study, step 3: build the blinded statement files.

For every claim with a chosen main theorem (work/mainthm/part_*.jsonl), write
one markdown file under work/blind/<code>.md holding only:
  1. the Erdős problem number and its text as erdosproblems.com stated it
     (work/problems/<n>.txt; a visible placeholder until fetched),
  2. the reference statement(s) from Formal Conjectures at the pinned commit,
     with docstrings and proofs removed (they can carry the answer or the
     problem's status),
  3. the claimant's main theorem, its statement only, plus the project's own
     definitions it mentions (two levels deep).
Claimant, AI tool, repository, thread, verdict and dates are left out.
Files get random codes and are shuffled; work/blind_key.csv maps code ->
claim and must not be shown to a coder.
"""
import csv, json, os, random, re
from pathlib import Path

WORK = Path(os.environ.get('DRIFT_WORK', '/tmp/drift'))
FC = Path(os.environ.get('FC_DIR', '/tmp/fc/FormalConjectures/ErdosProblems'))
SKIP = {'.lake', '.git', 'Mathlib', 'mathlib', 'lake-packages', 'build', 'FormalConjectures', 'formal-conjectures'}
SEED = 20261125  # fixed so the shuffle can be reproduced


def strip_comments(t):
    t = re.sub(r'/-.*?-/', '', t, flags=re.S)
    return re.sub(r'--[^\n]*', '', t)


def statement_of(text, start_line):
    """From a declaration's first line to its top-level `:=` (or `where`/`|`)."""
    lines = text.split('\n')[start_line - 1:]
    chunk = '\n'.join(lines[:400])
    depth = 0
    i = 0
    while i < len(chunk):
        c = chunk[i]
        if c in '([{⟨':
            depth += 1
        elif c in ')]}⟩':
            depth -= 1
        elif depth == 0 and chunk.startswith(':=', i):
            return chunk[:i].rstrip()
        elif depth == 0 and re.match(r'\n\s*\|', chunk[i:i + 40]):
            return chunk[:i].rstrip()
        i += 1
    return chunk[:2000].rstrip()


DEF = re.compile(r'^(?:@\[[^\]]*\]\s*)?(?:(?:private|protected|noncomputable)\s+)*'
                 r'(def|abbrev|structure|inductive|class|instance)\s+([^\s:({\[]+)', re.M)


def project_defs(files):
    defs = {}
    for f in files:
        t = strip_comments(f.read_text(errors='replace'))
        for m in DEF.finditer(t):
            name = m.group(2)
            body = t[m.start():]
            nxt = re.search(r'\n(?=(?:@\[|theorem |lemma |def |abbrev |structure |inductive |class |instance |namespace |end |section |open |variable ))', body[1:])
            body = body[:nxt.start() + 1 if nxt else 3000]
            defs.setdefault(name.split('.')[-1], body.strip()[:3000])
    return defs


def needed_defs(stmt, defs, depth=2):
    out, frontier = {}, stmt
    for _ in range(depth):
        found = {}
        for tok in set(re.findall(r"[\w'.]+", frontier)):
            short = tok.split('.')[-1]
            if len(short) > 2 and short in defs and short not in out:
                found[short] = defs[short]
        if not found:
            break
        out.update(found)
        frontier = '\n'.join(found.values())
    return out


def fc_reference(problem):
    f = FC / f'{problem}.lean'
    if not f.exists():
        return None
    t = strip_comments(f.read_text(errors='replace'))
    t = re.sub(r'@\[category[^\]]*\]\s*', '', t)
    t = re.sub(r':=\s*by\s*\n?\s*sorry', ':= sorry', t)
    t = re.sub(r'^(module|public import .*|import .*|@\[expose\] public section|open .*)\n', '', t, flags=re.M)
    return re.sub(r'\n{3,}', '\n\n', t).strip()


def project_files(path_field):
    out = []
    for p in path_field.split(';'):
        base = WORK / p
        root = base if base.is_dir() else base.parent
        while root.parent not in (WORK / 'repos', WORK / 'manual', WORK):
            root = root.parent
        out += [f for f in root.rglob('*.lean') if not SKIP & set(f.relative_to(root).parts)]
    return out[:3000]


def main():
    fetch = {r['claim_id']: r for r in csv.DictReader(open(WORK / 'fetch.csv'))}
    picks = {}
    for f in sorted((WORK / 'mainthm').glob('part_*.jsonl')):
        for line in open(f):
            if line.strip():
                p = json.loads(line)
                picks[str(p['claim_id'])] = p
    ids = sorted(picks, key=int)
    rng = random.Random(SEED)
    codes = rng.sample(range(100, 1000), len(ids))
    order = ids[:]
    rng.shuffle(order)
    out = WORK / 'blind'
    out.mkdir(exist_ok=True)
    key = []
    for code, cid in zip(codes, order):
        pick, row = picks[cid], fetch[cid]
        if not pick.get('line'):
            # nothing to judge: no declaration at the version the claim linked to
            key.append({'code': code, 'claim_id': cid, 'version': row['version'], 'note': 'no declaration'})
            continue
        src = (WORK / pick['file']).read_text(errors='replace')
        stmt = statement_of(src, int(pick['line']))
        defs = needed_defs(stmt, project_defs(project_files(row['path'])))
        prob = row['problem']
        ptxt = WORK / 'problems' / f'{prob}.txt'
        problem_text = ptxt.read_text().strip() if ptxt.exists() else '[problem text to be fetched from erdosproblems.com as of the claim date]'
        ref = fc_reference(prob)
        md = [f'# Item {code}', '', f'## Erdős problem {prob}', '', problem_text, '',
              '## Reference statement (Formal Conjectures, commit 9097e2f)', '',
              f'```lean\n{ref}\n```' if ref else '_No reference statement for this problem._', '',
              "## Claimant's main theorem", '', f'```lean\n{stmt}\n```', '']
        if defs:
            md += ["## Claimant's definitions used above", '', '```lean\n' + '\n\n'.join(defs.values()) + '\n```', '']
        (out / f'{code}.md').write_text('\n'.join(md))
        key.append({'code': code, 'claim_id': cid, 'version': row['version'], 'note': ''})
    with open(WORK / 'blind_key.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['code', 'claim_id', 'version', 'note'])
        w.writeheader(); w.writerows(sorted(key, key=lambda k: k['code']))
    print('blinded files:', len(key))


if __name__ == '__main__':
    main()
