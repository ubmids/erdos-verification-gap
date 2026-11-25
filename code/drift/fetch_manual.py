"""Statement-drift study, step 1b: the claims whose Lean is not in a git repo.

- live.lean-lang.org links carry the file itself, lz-string compressed in the
  URL (#codez=...) or as a pointer to a raw file (#url=...): decode or fetch.
- Everything else (zip downloads, registries, Drive, Zenodo, dead gists and
  repos) cannot be reached from the sandbox and is listed for retrieval by
  hand into work/manual/<claim_id>/.
Never prints file contents.
"""
import csv, os, re, subprocess
from pathlib import Path
from urllib.parse import unquote
from lzstring import LZString

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(os.environ.get('DRIFT_WORK', '/tmp/drift'))

def decode_codez(z):
    """The editor packs the file with lz-string; try both of its alphabets."""
    for fn in (LZString().decompressFromBase64, LZString().decompressFromEncodedURIComponent):
        try:
            out = fn(z)
            if out:
                return out
        except Exception:
            pass
    return None

def main():
    claims = {r['claim_id']: r for r in csv.DictReader(open(ROOT / 'data/claims.csv'))}
    rows = list(csv.DictReader(open(WORK / 'fetch.csv')))
    for r in rows:
        if r['status'] not in ('manual', 'unretrievable'):
            continue
        u = claims[r['claim_id']]['lean_url'].strip()
        d = WORK / 'manual' / r['claim_id']
        got = sorted(d.glob('**/*.lean')) if d.exists() else []
        if 'live.lean-lang.org' in u and not got:
            d.mkdir(parents=True, exist_ok=True)
            if m := re.search(r'#codez=([^&]+)', u):
                code = decode_codez(unquote(m.group(1)))
                if code:
                    (d / 'Main.lean').write_text(code)
            elif m := re.search(r'#url=([^&]+)', u):
                subprocess.run(['curl', '-sf', '-o', str(d / 'Main.lean'), unquote(m.group(1))])
            got = sorted(d.glob('*.lean'))
            r['version'] = 'pinned'  # the code is in the link itself / a commit URL
        if not got and not u.endswith('.lean') and re.search(r'\.(py|md|pdf|tex)$', u):
            r.update(status='not-lean', note=u.rsplit('.', 1)[-1])
            continue
        if got:
            r.update(status='ok', note='manual', lean_files=len(got),
                     path=';'.join(str(f.relative_to(WORK)) for f in got))
        else:
            r.update(status='manual', note=u[:80])
    with open(WORK / 'fetch.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    from collections import Counter
    print(Counter(r['status'] for r in rows))
    print('still to fetch by hand:', [r['claim_id'] for r in rows if r['status'] == 'manual'])

if __name__ == '__main__':
    main()
