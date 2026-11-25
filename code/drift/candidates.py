"""Statement-drift study, step 2a: list candidate main theorems per claim.

For every retrieved claim, parse the claimant's own .lean files (vendored
Mathlib, Formal Conjectures copies and build directories are skipped), and
list each `theorem`/`lemma` with signals that it is the one presented as the
solution: the problem number or "erdos" in its name or file, being in the
linked file, and not being used by any other declaration in the project.
Writes work/candidates.json. Prints counts only.
"""
import csv, json, os, re
from pathlib import Path

WORK = Path(os.environ.get('DRIFT_WORK', '/tmp/drift'))
SKIP = {'.lake', '.git', 'Mathlib', 'mathlib', 'lake-packages', 'build', 'FormalConjectures', 'formal-conjectures', '.github'}
DECL = re.compile(r'^(?:@\[[^\]]*\]\s*)?(?:(?:private|protected|noncomputable|nonrec)\s+)*(theorem|lemma)\s+([^\s:({\[]+)', re.M)

def lean_files(row):
    out = []
    for p in row['path'].split(';'):
        base = WORK / p
        if base.is_file():
            out.append(base)
        elif base.is_dir():
            out += [f for f in base.rglob('*.lean') if not SKIP & set(f.relative_to(base).parts)]
    return out[:3000]

def strip_comments(t):
    t = re.sub(r'/-.*?-/', lambda m: '\n' * m.group(0).count('\n'), t, flags=re.S)
    return re.sub(r'--[^\n]*', '', t)

def main():
    rows = [r for r in csv.DictReader(open(WORK / 'fetch.csv')) if r['status'] == 'ok']
    out = {}
    for r in rows:
        prob = r['problem']
        files = lean_files(r)
        texts = {f: strip_comments(f.read_text(errors='replace')) for f in files}
        decls = []
        for f, t in texts.items():
            for m in DECL.finditer(t):
                decls.append((f, m.group(2), t.count('\n', 0, m.start()) + 1))
        # one pass over the project: how often each identifier's last part appears
        from collections import Counter
        tokens = Counter()
        for t in texts.values():
            for tok in re.findall(r"[\w'.]+", t):
                tokens[tok.split('.')[-1]] += 1
        # names the claimant points at in their own README / notes
        roots = {WORK / p for p in r['path'].split(';')}
        repo_root = next(iter(roots))
        while repo_root.parent != WORK / 'repos' and repo_root.parent != WORK / 'manual' and repo_root != WORK:
            repo_root = repo_root.parent
        pointed = set()
        for md in list(repo_root.glob('*.md')) + list(repo_root.glob('*/*.md'))[:40]:
            pointed |= set(re.findall(r'`([\w.\']+)`', md.read_text(errors='replace')))
        pointed = {x.split('.')[-1] for x in pointed}
        cands = []
        for f, name, line in decls:
            short = name.split('.')[-1]
            uses = tokens[short] - 1
            score = 0
            low = (name + ' ' + f.name).lower()
            if re.search(r'(?<!\d)' + prob + r'(?!\d)', name + f.name): score += 3
            if 'erdos' in low or 'erdős' in low: score += 2
            if re.search(r'main|solution|answer|final|resolve|theorem_?\d*$', low): score += 1
            if uses <= 0: score += 2
            if short in pointed: score += 4
            cands.append({'file': str(f.relative_to(WORK)), 'name': name, 'line': line,
                          'uses': uses, 'score': score})
        cands.sort(key=lambda c: -c['score'])
        out[r['claim_id']] = {'problem': prob, 'n_files': len(files), 'n_decls': len(decls), 'top': cands[:12]}
    json.dump(out, open(WORK / 'candidates.json', 'w'), indent=1)
    import statistics
    print('claims', len(out), '| decls median', statistics.median(v['n_decls'] for v in out.values()),
          '| no decls', sum(v['n_decls'] == 0 for v in out.values()),
          '| clear top (score gap>=2)', sum(len(v['top']) > 1 and v['top'][0]['score'] - v['top'][1]['score'] >= 2 or len(v['top']) == 1 for v in out.values()))

if __name__ == '__main__':
    main()
