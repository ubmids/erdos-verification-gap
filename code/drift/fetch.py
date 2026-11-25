"""Statement-drift study, step 1: fetch every Lean project in the sample.

Reads data/claims.csv, keeps rows with a lean_url (the pre-registered sample,
122 claims), and for each one:
  - GitHub repo / tree / blob links: shallow-clones the repo (at the linked
    ref when the link names one) into work/repos/ and records which .lean
    files fall under the linked path;
  - gists: clones the gist;
  - anything else: marked `manual` for retrieval by hand.
It also counts `sorry`, `axiom` declarations and `native_decide` in those
files. It never prints a theorem statement, so the coder stays blind.

Output: work/fetch.csv (one row per claim). work/ is not committed.
"""
import csv, re, subprocess, sys, os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(os.environ.get('DRIFT_WORK', '/tmp/drift'))
REPOS = WORK / 'repos'
GH = re.compile(r'https://github\.com/([^/]+)/([^/#?]+)(?:/(?:tree|blob)/([^/#?]+)(?:/([^#?]*))?)?')
GIST = re.compile(r'https://gist\.github\.com/(?:[^/]+/)?([0-9a-f]+)')

def run(cmd, cwd=None):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=600)

def clone(url, dest, ref=None):
    if (dest / '.git').exists():
        return True, 'cached'
    args = ['git', 'clone', '--depth', '1', '--quiet']
    if ref:
        args += ['--branch', ref]
    p = run(args + [url, str(dest)])
    if p.returncode != 0 and ref:  # ref may be a commit, not a branch
        p = run(['git', 'clone', '--depth', '50', '--quiet', url, str(dest)])
        if p.returncode == 0:
            q = run(['git', 'checkout', '--quiet', ref], cwd=dest)
            if q.returncode != 0:
                return True, 'ref-missing'
    return p.returncode == 0, (p.stderr.strip().splitlines() or [''])[-1][:120]

def scan(files):
    s = a = n = 0
    for f in files:
        t = f.read_text(errors='replace')
        t = re.sub(r'/-.*?-/', '', t, flags=re.S)
        t = re.sub(r'--[^\n]*', '', t)
        s += len(re.findall(r'\bsorry\b', t))
        a += len(re.findall(r'^\s*axiom\s', t, flags=re.M))
        n += len(re.findall(r'\bnative_decide\b', t))
    return s, a, n

def fetch(row):
    u = row['lean_url'].strip()
    out = {'claim_id': row['claim_id'], 'problem': row['problem'], 'host': '', 'status': '',
           'note': '', 'lean_files': 0, 'sorry': '', 'axiom': '', 'native_decide': '', 'path': ''}
    m, g = GH.match(u), GIST.match(u)
    if m:
        owner, repo, ref, sub = m.groups()
        repo = repo.removesuffix('.git')
        dest = REPOS / f'{owner}__{repo}__{ref or "HEAD"}'
        ok, note = clone(f'https://github.com/{owner}/{repo}', dest, ref)
        out.update(host='github', note=note)
        base = dest / (sub or '')
    elif g:
        dest = REPOS / f'gist__{g.group(1)}'
        ok, note = clone(f'https://gist.github.com/{g.group(1)}.git', dest)
        out.update(host='gist', note=note)
        base = dest
    else:
        out.update(host=u.split('/')[2], status='manual')
        return out
    if not ok:
        out['status'] = 'unretrievable'
        return out
    files = [base] if base.is_file() else [f for f in base.rglob('*.lean') if '.lake' not in f.parts]
    files = [f for f in files if f.suffix == '.lean']
    s, a, n = scan(files)
    out.update(status='ok' if files else 'no-lean-files', lean_files=len(files),
               sorry=s, axiom=a, native_decide=n, path=str(base.relative_to(WORK)))
    return out

def main():
    rows = [r for r in csv.DictReader(open(ROOT / 'data/claims.csv')) if r['lean_url'].strip()]
    assert len(rows) == 122, len(rows)
    REPOS.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(4) as ex:
        res = list(ex.map(fetch, rows))
    with open(WORK / 'fetch.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(res[0]))
        w.writeheader(); w.writerows(res)
    from collections import Counter
    print(Counter(r['status'] for r in res))

if __name__ == '__main__':
    main()
