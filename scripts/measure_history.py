#!/usr/bin/env python3
"""How much of its own past does a published PDF actually keep?

Four questions, asked of every PDF in a directory, each sharper than the last.
The point of the script is that the answers are two orders of magnitude apart,
and only the last one means what a reader assumes the first one means.

    python3 measure_history.py <directory of PDFs>

Q1  does the file chain to an earlier cross-reference section at all
Q2  does before-you-send call that a HIGH finding
Q3  does any object actually exist in two versions inside the file
Q4  does any PAGE point at a different content stream than it used to

Q1, Q3 and Q4 are answered here by walking the bytes. Nothing in this file
imports before_you_send, on purpose: Q2 is answered by running the tool as a
subprocess, so the two implementations of the same byte walk are independent
and can be compared against each other.

It prints structure. It never prints anything recovered from a document.
"""
import sys, os, re, zlib, glob, json, subprocess, collections
import concurrent.futures as cf

BYS = os.environ.get("BYS", "before-you-send")


# ------------------------------------------------------------------ byte walk
def xref_offsets(raw):
    """Offsets of every cross-reference section, newest first, following /Prev."""
    try:
        off = int(raw.rsplit(b"startxref", 1)[1].split()[0])
    except Exception:
        return []
    offs, seen = [], set()
    while 0 < off < len(raw) and off not in seen and len(offs) < 64:
        seen.add(off)
        offs.append(off)
        w = raw[off:off + 4096]
        e = w.find(b"%%EOF")
        if e != -1:
            w = w[:e]
        m = re.search(rb"/Prev\s+(\d+)", w)
        if not m:
            break
        try:
            off = int(m.group(1))
        except Exception:
            break
    return offs


def _classic(raw, off):
    m = re.compile(rb"\s*xref\s*").match(raw, off)
    if not m:
        return None
    out, pos = {}, m.end()
    while True:
        h = re.compile(rb"(\d+)\s+(\d+)\s*").match(raw, pos)
        if not h:
            break
        start, count = int(h.group(1)), int(h.group(2))
        pos = h.end()
        for i in range(count):
            em = re.match(rb"(\d{10})\s(\d{5})\s([nf])", raw[pos:pos + 20])
            if not em:
                return out
            if em.group(3) == b"n":
                out[start + i] = ("n", int(em.group(1)))
            pos += 20
            while pos < len(raw) and raw[pos:pos + 1] in (b"\r", b"\n", b" "):
                pos += 1
        if raw[pos:pos + 7].startswith(b"trailer"):
            break
    return out


def _unpredict(data, W, d):
    pm = re.search(rb"/Predictor\s+(\d+)", d)
    if not (pm and int(pm.group(1)) >= 10):
        return data
    cm = re.search(rb"/Columns\s+(\d+)", d)
    cols = int(cm.group(1)) if cm else sum(W)
    rowlen, bpp = cols + 1, sum(W)
    prev, out = bytearray(cols), bytearray()
    for r in range(0, len(data) - rowlen + 1, rowlen):
        ft = data[r]
        row = bytearray(data[r + 1:r + 1 + cols])
        for i in range(cols):
            a = row[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            if ft == 1:
                row[i] = (row[i] + a) & 0xFF
            elif ft == 2:
                row[i] = (row[i] + b) & 0xFF
            elif ft == 3:
                row[i] = (row[i] + ((a + b) >> 1)) & 0xFF
            elif ft == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                row[i] = (row[i] + pr) & 0xFF
        out += row
        prev = row
    return bytes(out)


def _xrefstream(raw, off):
    m = re.compile(rb"\s*(\d+)\s+(\d+)\s+obj").match(raw, off)
    if not m:
        return None
    sm = raw.find(b"stream", m.end())
    if sm == -1:
        return None
    d = raw[m.end():sm]
    if b"/XRef" not in d:
        return None
    wm = re.search(rb"/W\s*\[\s*(\d+)\s+(\d+)\s+(\d+)\s*\]", d)
    if not wm:
        return None
    W = [int(wm.group(i)) for i in (1, 2, 3)]
    szm = re.search(rb"/Size\s+(\d+)", d)
    idxm = re.search(rb"/Index\s*\[([\d\s]+)\]", d)
    index = ([int(x) for x in idxm.group(1).split()] if idxm
             else [0, int(szm.group(1)) if szm else 0])
    body = raw[sm + 6:].lstrip(b"\r\n")
    em = body.find(b"endstream")
    data = body[:em] if em != -1 else body
    if b"/FlateDecode" in d:
        try:
            data = zlib.decompress(data)
        except Exception:
            try:
                data = zlib.decompressobj().decompress(data)
            except Exception:
                return None
    data = _unpredict(data, W, d)
    ent = sum(W)
    if not ent:
        return None
    res, pos = {}, 0
    for k in range(0, len(index) - 1, 2):
        for i in range(index[k + 1]):
            if pos + ent > len(data):
                break
            f = []
            for w in W:
                f.append(int.from_bytes(data[pos:pos + w], "big") if w else None)
                pos += w
            t = f[0] if W[0] else 1
            if t == 1:
                res[index[k] + i] = ("n", f[1])
            elif t == 2:
                res[index[k] + i] = ("c", f[1])
    return res


def section(raw, off):
    return _classic(raw, off) or _xrefstream(raw, off) or {}


def obj_dict(raw, off, n=4000):
    """The dictionary text of the object defined at off, and nothing after it.

    The window must be closed at `endobj` as well as at `stream`. A fixed length
    window runs off the end of a short object into whatever is stored next, and a
    neighbouring page dictionary then answers a question asked about this object.
    That defect made a catalogue and two fonts count as replaced pages before it
    was caught.
    """
    m = re.compile(rb"\s*(\d+)\s+(\d+)\s+obj").match(raw, off)
    if not m:
        return None
    tail = raw[m.end():m.end() + n]
    for marker in (b"endobj", b"stream"):
        c = tail.find(marker)
        if c != -1:
            tail = tail[:c]
    return tail


def contents_of(d):
    if d is None:
        return None
    m = re.search(rb"/Contents\s*(\[[^\]]*\]|\d+\s+\d+\s+R)", d)
    if not m:
        return None
    return tuple(int(x) for x in re.findall(rb"(\d+)\s+\d+\s+R", m.group(1)))


def walk(path):
    raw = open(path, "rb").read()
    offs = xref_offsets(raw)
    r = {"file": os.path.basename(path), "revisions": max(len(offs), 1),
         "linearized": b"/Linearized" in raw[:2048], "superseded": 0,
         "page_objs": 0, "page_rows_changed": 0, "pages_changed": 0,
         "changed_pages": set(), "kinds": collections.Counter()}
    if len(offs) < 2:
        return r
    secs = [section(raw, o) for o in offs]
    newest = secs[0]
    for older in secs[1:]:
        for num, loc in older.items():
            new = newest.get(num)
            if new is None or new == loc:
                continue
            r["superseded"] += 1
            if loc[0] != "n" or new[0] != "n":
                r["kinds"]["in an object stream"] += 1
                continue
            od, nd = obj_dict(raw, loc[1]), obj_dict(raw, new[1])
            t = re.search(rb"/Type\s*/(\w+)", od) if od else None
            r["kinds"][t.group(1).decode() if t else "no /Type"] += 1
            if od and nd and re.search(rb"/Type\s*/Page\b", od) \
                    and re.search(rb"/Type\s*/Page\b", nd):
                r["page_objs"] += 1
                oc, nc = contents_of(od), contents_of(nd)
                if oc and nc and oc != nc:
                    # One page can be superseded from several earlier sections,
                    # so the comparison rows over-count pages. Keep both: the
                    # row count for the examination, the set for the answer.
                    r["page_rows_changed"] += 1
                    r["changed_pages"].add(num)
    r["pages_changed"] = len(r["changed_pages"])
    return r


# ------------------------------------------------------------------- the tool
def tool(path):
    try:
        p = subprocess.run([BYS, path, "--format", "json"],
                           capture_output=True, timeout=300)
        if not p.stdout.strip():
            return {"file": os.path.basename(path), "ok": False,
                    "why": p.stderr.decode()[:120].replace("\n", " ")}
        d = json.loads(p.stdout)
        lvl = "none"
        for f in d.get("findings", []):
            if f["check"] == "earlier_versions_retained":
                lvl = f["level"]
        return {"file": os.path.basename(path), "ok": True, "ev_level": lvl,
                "findings": len(d.get("findings", [])), "counts": d.get("counts", {})}
    except Exception as e:
        return {"file": os.path.basename(path), "ok": False, "why": type(e).__name__}


def main():
    files = sorted(glob.glob(os.path.join(sys.argv[1], "*.pdf")))
    if not files:
        raise SystemExit("no PDFs in " + sys.argv[1])
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        tools = list(ex.map(tool, files))
    walks = {w["file"]: w for w in (walk(f) for f in files)}
    src = lambda n: n.split("_")[0]
    ok = [t for t in tools if t["ok"]]

    print("PDFs in the directory                            :", len(files))
    print("read by before-you-send                          :", len(ok))
    for t in tools:
        if not t["ok"]:
            print("   could not read:", t["file"], "|", t.get("why"))
    print("by source:", dict(collections.Counter(src(t["file"]) for t in ok)))
    print()
    m = [t for t in ok if walks[t["file"]]["revisions"] >= 2]
    print("Q1 chaining to an earlier xref section           :", len(m),
          dict(collections.Counter(src(t["file"]) for t in m)))
    hi = [t for t in ok if t["ev_level"] == "high"]
    print("Q2 flagged HIGH by earlier_versions_retained     :", len(hi),
          dict(collections.Counter(src(t["file"]) for t in hi)))
    sup = [t for t in ok if walks[t["file"]]["superseded"] > 0]
    print("Q3 any object present in two versions            :", len(sup),
          dict(collections.Counter(src(t["file"]) for t in sup)))
    print("   of the HIGH files, how many are in Q3         :",
          sum(1 for t in hi if walks[t["file"]]["superseded"] > 0))
    ch = [t for t in ok if walks[t["file"]]["pages_changed"] > 0]
    print("Q4 a page points at different content            :", len(ch),
          dict(collections.Counter(src(t["file"]) for t in ch)))
    print("   page comparisons examined (old vs new)        :",
          sum(walks[t["file"]]["page_objs"] for t in ok))
    print("   comparisons where content differs             :",
          sum(walks[t["file"]]["page_rows_changed"] for t in ok))
    print("   DISTINCT pages whose content was replaced     :",
          sum(walks[t["file"]]["pages_changed"] for t in ok))
    for t in ch:
        print("      ", t["file"], walks[t["file"]]["pages_changed"], "page(s)",
              "obj", sorted(walks[t["file"]]["changed_pages"]))
    print()
    ag = sum(1 for t in ok
             if (walks[t["file"]]["revisions"] >= 2) == (t["ev_level"] != "none"))
    print("tool and byte walk agree that history exists     :", ag, "of", len(ok))
    k = collections.Counter()
    for t in ok:
        k.update(walks[t["file"]]["kinds"])
    print("superseded objects by kind:", dict(k.most_common(10)))


if __name__ == "__main__":
    main()
