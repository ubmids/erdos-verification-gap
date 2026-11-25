"""Statement-drift study, step 1: fetch every Lean project in the sample.

Reads data/claims.csv, keeps rows with a lean_url (the pre-registered sample,
122 claims), and for each one:
  - GitHub repo / tree / blob links: clones the repo (full history, blobs on
    demand) and checks out the last commit on the linked branch made before
    the claim was submitted, so what gets judged is what the claim pointed
    at, not later fixes. Records which .lean files fall under the linked
    path; a linked .md page is followed to the .lean files it links to;
  - gists: clones the gist;
  - anything else: marked `manual` for retrieval by hand.
It also counts `sorry`, `axiom` declarations and `native_decide` in those
files. It never prints a theorem statement, so the coder stays blind.

Output: work/fetch.csv (one row per claim). work/ is not committed.
"""
import csv, re, subprocess, sys, os, threading
from urllib.parse import unquote
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(os.environ.get('DRIFT_WORK', '/tmp/drift'))
REPOS = WORK / 'repos'
GH = re.compile(r'https://github\.com/([^/]+)/([^/#?]+)(?:/(?:tree|blob)/([^/#?]+)(?:/([^#?]*))?)?')
GIST = re.compile(r'https://gist\.github\.com/(?:[^/]+/)?([0-9a-f]+)')

def run(cmd, cwd=None):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=600)

_locks: dict = {}
_locks_guard = threading.Lock()

def lock_for(dest):
    with _locks_guard:
        return _locks.setdefault(str(dest), threading.Lock())

def clone(url, dest):
    """Blobless clone of the whole history, once per repo (threads share it)."""
    with lock_for(dest):
        if (dest / '.git').exists():
            return True, ''
        p = run(['git', 'clone', '--filter=blob:none', '--no-checkout', '--quiet', url, str(dest)])
        return p.returncode == 0, (p.stderr.strip().splitlines() or [''])[-1][:120]

def has_lean(dest, commit, sub):
    """Does `commit` have .lean files at the linked path (or the linked file)?"""
    names = run(['git', 'ls-tree', '-r', '--name-only', commit, '--', sub or '.'], cwd=dest).stdout.split()
    if sub.endswith('.md'):
        return bool(names)  # a linked page; its .lean links are followed later
    return any(n.endswith('.lean') for n in names)

def pick_commit(dest, ref, when, sub):
    """Which commit to judge, and how it was chosen.

    - A tag or a commit hash in the link pins the version: use it (`pinned`).
    - A branch: the last commit made before the claim was submitted
      (`before-claim`). If there is none with Lean files at the linked path
      (history rewritten after the claim, or files added later), the earliest
      later commit that has them (`post-claim`, reported separately).
    """
    rev = lambda r: run(['git', 'rev-parse', '--verify', '--quiet', r + '^{commit}'], cwd=dest).stdout.strip()
    if ref:
        for r in (f'refs/tags/{ref}', ref if re.fullmatch(r'[0-9a-f]{7,40}', ref) else ''):
            if r and (c := rev(r)):
                return c, 'pinned'
    branch = f'origin/{ref}' if ref else 'origin/HEAD'
    if not rev(branch):
        return None, 'ref-missing'
    before = run(['git', 'rev-list', f'--before={when} +0000', branch], cwd=dest).stdout.split()
    for c in before[:20]:
        if has_lean(dest, c, sub):
            return c, 'before-claim'
    after = run(['git', 'rev-list', '--reverse', f'--since={when} +0000', branch], cwd=dest).stdout.split()
    for c in after[:200]:
        if has_lean(dest, c, sub):
            return c, 'post-claim'
    return None, 'no-lean-in-history'

def checkout(dest, commit):
    with lock_for(dest):
        wt = dest.parent / f'{dest.name}@{commit[:10]}'
        if not wt.exists():
            q = run(['git', 'worktree', 'add', '--detach', '--quiet', str(wt), commit], cwd=dest)
            if q.returncode != 0:
                return None
        return wt

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
    out = {'claim_id': row['claim_id'], 'problem': row['problem'], 'host': '', 'status': '', 'commit': '', 'version': '',
           'note': '', 'lean_files': 0, 'sorry': '', 'axiom': '', 'native_decide': '', 'path': ''}
    m, g = GH.match(u), GIST.match(u)
    when = row['submitted_utc']
    if m:
        owner, repo, ref, sub = m.groups()
        repo = repo.removesuffix('.git')
        dest = REPOS / f'{owner}__{repo}'
        ok, note = clone(f'https://github.com/{owner}/{repo}', dest)
        out['host'] = 'github'
    elif g:
        dest, ref, sub = REPOS / f'gist__{g.group(1)}', None, None
        ok, note = clone(f'https://gist.github.com/{g.group(1)}.git', dest)
        out['host'] = 'gist'
    else:
        out.update(host=u.split('/')[2], status='manual')
        return out
    if not ok:
        out.update(status='unretrievable', note=note)
        return out
    sub = unquote(sub or '')
    commit, how = pick_commit(dest, ref, when, sub)
    wt = checkout(dest, commit) if commit else None
    if not wt:
        out.update(status='unretrievable', note=how)
        return out
    out.update(commit=commit[:10], version=how)
    base = wt / sub
    if base.is_file() and base.suffix == '.md':
        # a page describing the proof: follow its links to .lean files
        links = re.findall(r'\]\(([^)]+\.lean)\)', base.read_text(errors='replace'))
        targets = [(base.parent / l).resolve() for l in links if not l.startswith('http')]
        files = [t for t in targets if t.exists()]
        out['note'] = 'via .md page'
        s_, a_, n_ = scan(files)
        out.update(status='ok' if files else 'no-lean-files', lean_files=len(files),
                   sorry=s_, axiom=a_, native_decide=n_,
                   path=';'.join(str(f.relative_to(WORK)) for f in files))
        return out
    if base.is_file() and base.suffix != '.lean':
        out.update(status='not-lean', note=base.suffix, path=str(base.relative_to(WORK)))
        return out
    if not base.exists():
        out.update(status='path-missing', path=str(base.relative_to(WORK)))
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
