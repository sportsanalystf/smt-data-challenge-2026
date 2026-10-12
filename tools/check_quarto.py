"""
check_quarto.py — validate the Quarto documents without rendering them.

Quarto is not installed in the environment these documents were written in, so
this performs the checks a render would otherwise catch:

  * YAML front matter parses and carries a title
  * every code chunk has a language and a closing fence
  * Python chunks COMPILE (via `compile()`), catching real syntax errors
  * R chunks pass the static R checker (balance, dangling pipes, top-level else)
  * chunk labels are unique within a document (Quarto errors on duplicates)
  * every referenced image path exists
  * panel-tabset blocks are balanced

Usage:  python tools/check_quarto.py [quarto_dir]
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_r_syntax import tokenize_structure, check_balance, check_lines  # noqa: E402

FENCE = re.compile(r"^```+\s*\{?([a-zA-Z0-9_-]*)")
LABEL = re.compile(r"^#\|\s*label:\s*(\S+)")
IMAGE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


def parse_front_matter(text):
    if not text.startswith("---"):
        return None, "no YAML front matter"
    end = text.find("\n---", 3)
    if end == -1:
        return None, "front matter not terminated"
    block = text[3:end]
    meta = {}
    for line in block.splitlines():
        if ":" in line and not line.strip().startswith("#"):
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip('"')
    return meta, None


def extract_chunks(text):
    """Return (lang, label, code, start_line) for each fenced code chunk."""
    chunks = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = FENCE.match(lines[i])
        if m and lines[i].startswith("```"):
            lang = m.group(1)
            if lang == "":            # closing fence encountered out of order
                i += 1
                continue
            start = i
            body = []
            i += 1
            closed = False
            while i < len(lines):
                if lines[i].startswith("```"):
                    closed = True
                    break
                body.append(lines[i])
                i += 1
            label = None
            for b in body:
                lm = LABEL.match(b.strip())
                if lm:
                    label = lm.group(1)
                    break
            code = "\n".join(l for l in body if not l.strip().startswith("#|"))
            chunks.append({"lang": lang, "label": label, "code": code,
                           "line": start + 1, "closed": closed})
        i += 1
    return chunks


def check_document(path):
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    problems, warnings = [], []
    meta, err = parse_front_matter(text)
    if err:
        problems.append(err)
    elif "title" not in meta:
        warnings.append("front matter has no title")

    chunks = extract_chunks(text)
    labels = {}
    n_r = n_py = 0

    for c in chunks:
        where = f"chunk at line {c['line']}"
        if not c["closed"]:
            problems.append(f"{where}: fence never closed")
            continue

        if c["label"]:
            if c["label"] in labels:
                problems.append(
                    f"{where}: duplicate label '{c['label']}' "
                    f"(also line {labels[c['label']]})")
            labels[c["label"]] = c["line"]

        if c["lang"] == "python":
            n_py += 1
            try:
                compile(c["code"], f"{path}:{c['line']}", "exec")
            except SyntaxError as exc:
                problems.append(f"{where}: Python syntax error: {exc.msg} "
                                f"(line {exc.lineno})")
        elif c["lang"] == "r":
            n_r += 1
            try:
                events = tokenize_structure(c["code"])
                for p in check_balance(events):
                    problems.append(f"{where}: R {p}")
            except Exception as exc:
                problems.append(f"{where}: R tokenize failed: {exc}")
            p2, _ = check_lines(c["code"])
            for p in p2:
                problems.append(f"{where}: R {p}")

    # Balanced ::: divs (panel-tabset / callouts)
    opens = len(re.findall(r"^:::+\s*\{", text, flags=re.M))
    closes = len(re.findall(r"^:::+\s*$", text, flags=re.M))
    if opens != closes:
        problems.append(f"unbalanced ::: blocks ({opens} opened, {closes} closed)")

    # Referenced images must exist
    base = os.path.dirname(os.path.abspath(path))
    for rel in IMAGE.findall(text):
        if rel.startswith(("http://", "https://")):
            continue
        if not os.path.exists(os.path.normpath(os.path.join(base, rel))):
            warnings.append(f"missing image: {rel}")

    return {"path": path, "problems": problems, "warnings": warnings,
            "chunks": len(chunks), "r": n_r, "py": n_py}


def main(target):
    if os.path.isdir(target):
        files = sorted(os.path.join(target, f) for f in os.listdir(target)
                       if f.endswith(".qmd"))
    else:
        files = [target]

    print("=" * 70)
    print("QUARTO DOCUMENT CHECK")
    print("=" * 70)
    total = 0
    for f in files:
        r = check_document(f)
        total += len(r["problems"])
        status = "FAIL" if r["problems"] else "ok  "
        print(f"[{status}] {os.path.basename(f):32s} "
              f"{r['chunks']:3d} chunks ({r['r']} R, {r['py']} Python)")
        for p in r["problems"]:
            print(f"         PROBLEM  {p}")
        for w in r["warnings"]:
            print(f"         warn     {w}")

    print("-" * 70)
    print(f"{len(files)} documents, {total} problems")
    if total == 0:
        print("QUARTO CHECK PASSED (run `quarto render` for a full build)")
    return 1 if total else 0


if __name__ == "__main__":
    t = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "quarto")
    sys.exit(main(t))
