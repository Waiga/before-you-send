#!/usr/bin/env python3
"""Download every collected URL. Filename is sha1(url)[:12], as the prior corpus did."""
import sys, os, hashlib, urllib.request, concurrent.futures as cf, glob

UA = {"User-Agent": "before-you-send-corpus/1.0 (public-document measurement)"}
OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)

rows = []
for f in sorted(glob.glob(os.path.join(os.path.dirname(OUT), "urls_*.tsv"))):
    for line in open(f):
        line = line.rstrip("\n")
        if not line.strip():
            continue
        src, url = line.split("\t", 1)
        rows.append((src, url))

def fetch(row):
    src, url = row
    name = "%s_%s.pdf" % (src, hashlib.sha1(url.encode()).hexdigest()[:12])
    path = os.path.join(OUT, name)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        b = open(path, "rb").read()
        return (src, name, len(b), hashlib.sha256(b).hexdigest(), url, "cached")
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=120) as r:
            b = r.read()
    except Exception as e:
        return (src, name, 0, "", url, "ERROR %s" % type(e).__name__)
    if not b.startswith(b"%PDF"):
        return (src, name, len(b), "", url, "NOTPDF")
    with open(path, "wb") as fh:
        fh.write(b)
    return (src, name, len(b), hashlib.sha256(b).hexdigest(), url, "ok")

results = []
with cf.ThreadPoolExecutor(max_workers=8) as ex:
    for i, r in enumerate(ex.map(fetch, rows), 1):
        results.append(r)
        if i % 100 == 0:
            print("  ...%d/%d" % (i, len(rows)), file=sys.stderr)

man = os.path.join(os.path.dirname(OUT), "documents.tsv")
with open(man, "w") as fh:
    fh.write("source\tlocal_name\tbytes\tsha256\tsource_url\tstatus\n")
    for r in results:
        fh.write("\t".join(str(x) for x in r) + "\n")

ok = [r for r in results if r[5] in ("ok", "cached")]
print("attempted %d, downloaded %d" % (len(results), len(ok)))
from collections import Counter
print(Counter(r[0] for r in ok))
print(Counter(r[5] for r in results))
