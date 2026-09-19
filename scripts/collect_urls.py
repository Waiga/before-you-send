#!/usr/bin/env python3
"""Collect PDF URLs from four public sources. Records every URL it chooses."""
import json, sys, urllib.request, urllib.parse, time, re, hashlib

UA = {"User-Agent": "before-you-send-corpus/1.0 (public-document measurement)"}

def get(url, timeout=60):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()

def j(url, timeout=60):
    return json.loads(get(url, timeout))

out = []

# ---- Federal Register: newest notices, GPO / Acrobat Distiller pipeline ----
def fedreg(n_pages=3, per=100):
    got = []
    url = ("https://www.federalregister.gov/api/v1/documents.json?per_page=%d"
           "&order=newest&fields[]=document_number&fields[]=pdf_url"
           "&fields[]=publication_date" % per)
    for page in range(n_pages):
        d = j(url)
        for r in d.get("results", []):
            if r.get("pdf_url"):
                got.append(("fedreg", r["pdf_url"]))
        nxt = d.get("next_page_url")
        if not nxt:
            break
        url = nxt + "&format=json"
        time.sleep(0.4)
    return got

# ---- gov.uk: recent guidance and regulation, Word pipeline ----
def govuk(target=250):
    got, seen = [], set()
    links = []
    for doctype in ("guidance", "regulation", "correspondence", "policy_paper"):
        for start in (0, 100, 200):
            u = ("https://www.gov.uk/api/search.json?"
                 "filter_content_store_document_type=%s&count=100&start=%d"
                 "&order=-public_timestamp&fields=link" % (doctype, start))
            try:
                d = j(u)
            except Exception:
                continue
            links += [r["link"] for r in d.get("results", []) if r.get("link")]
            time.sleep(0.3)
    for link in links:
        if len(got) >= target:
            break
        try:
            c = j("https://www.gov.uk/api/content" + link, timeout=45)
        except Exception:
            continue
        atts = (c.get("details") or {}).get("attachments") or []
        for a in atts:
            u = a.get("url") or ""
            if u.lower().endswith(".pdf") and u not in seen:
                seen.add(u)
                got.append(("govuk", u))
                break          # at most one PDF per publication, for producer spread
        time.sleep(0.15)
    return got

# ---- WHO IRIS: InDesign pipeline ----
def who(target=150):
    got = []
    for page in range(6):
        if len(got) >= target:
            break
        u = ("https://iris.who.int/server/api/discover/search/objects?"
             "size=50&page=%d&sort=dc.date.accessioned,DESC" % page)
        try:
            d = j(u, timeout=60)
        except Exception:
            break
        objs = (d.get("_embedded") or {}).get("searchResult", {}).get("_embedded", {}).get("objects", [])
        if not objs:
            break
        for o in objs:
            if len(got) >= target:
                break
            ind = (o.get("_embedded") or {}).get("indexableObject") or {}
            uuid = ind.get("uuid")
            if not uuid or ind.get("type") != "item":
                continue
            try:
                b = j("https://iris.who.int/server/api/core/items/%s/bundles" % uuid, timeout=45)
            except Exception:
                continue
            bundles = (b.get("_embedded") or {}).get("bundles", [])
            for bundle in bundles:
                if bundle.get("name") != "ORIGINAL":
                    continue
                href = ((bundle.get("_links") or {}).get("bitstreams") or {}).get("href")
                if not href:
                    continue
                try:
                    bs = j(href, timeout=45)
                except Exception:
                    continue
                for item in (bs.get("_embedded") or {}).get("bitstreams", []):
                    name = (item.get("name") or "").lower()
                    if name.endswith(".pdf"):
                        content = ((item.get("_links") or {}).get("content") or {}).get("href")
                        if content:
                            got.append(("who", content))
                        break
                break
            time.sleep(0.1)
        time.sleep(0.3)
    return got

# ---- arXiv: LaTeX / pdfTeX pipeline ----
def arxiv(cats=("cs.CR","econ.GN","stat.AP","physics.med-ph","math.PR","q-bio.QM"), per=25):
    got = []
    for c in cats:
        u = ("https://export.arxiv.org/api/query?search_query=cat:%s"
             "&sortBy=submittedDate&sortOrder=descending&max_results=%d" % (c, per))
        try:
            x = get(u, timeout=60).decode("utf-8", "replace")
        except Exception:
            continue
        for m in re.finditer(r'<id>http://arxiv\.org/abs/([^<]+)</id>', x):
            got.append(("arxiv", "https://arxiv.org/pdf/%s" % m.group(1)))
        time.sleep(3.2)   # arXiv asks for 3 seconds between calls
    return got

if __name__ == "__main__":
    which = sys.argv[1]
    fn = {"fedreg": fedreg, "govuk": govuk, "who": who, "arxiv": arxiv}[which]
    rows = fn()
    with open(sys.argv[2], "w") as fh:
        for src, u in rows:
            fh.write("%s\t%s\n" % (src, u))
    print(which, "collected", len(rows), "urls")
