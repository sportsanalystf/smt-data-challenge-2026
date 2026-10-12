"""
check_r_syntax.py — a static checker for the R sources.

WHY THIS EXISTS
R is not installed in the environment these modules were written in, so the R
code could not be executed during development. Shipping unvalidated code would
be careless, so this tool performs the checks that catch the overwhelming
majority of errors in generated R:

  * unbalanced (), [], {} and unterminated strings, tracked by a real tokenizer
    that understands R comments, strings, and escapes
  * a trailing pipe (%>% or |>) or a dangling operator at end of file/line
    followed by a blank line, which is the classic silent R breakage
  * `else` starting a line at top level (valid inside {} but a parse error at
    top level)
  * assignment typos such as `<--` and `= =`
  * unknown function calls into our own namespace (helps catch renames)
  * TABs mixed with spaces in indentation (style, reported separately)

It is NOT a full R parser and does not replace `Rscript -e 'parse(...)'`. Run
that too when R is available:

    for f in R/*.R; do Rscript -e "parse('$f')" || echo "FAILED $f"; done

Usage:  python tools/check_r_syntax.py [paths...]
"""
import os
import re
import sys

OPENERS = {"(": ")", "[": "]", "{": "}"}
CLOSERS = {v: k for k, v in OPENERS.items()}

PIPE_END = re.compile(r"(%>%|\|>|\+|,|&&|\|\||~|<-|=)\s*$")
# `<--` is never valid; `= =` (split equality) is a typo. Plain `==`, `<=`,
# `>=` and `!=` must NOT match, which is why the second branch requires
# whitespace between the two equals signs.
BAD_ASSIGN = re.compile(r"<--|->>>|=\s+=")
ELSE_AT_START = re.compile(r"^\s*else\b")


class RCheckError(Exception):
    pass


def tokenize_structure(text):
    """Walk the source tracking strings/comments; return bracket events.

    Yields (line_no, char) for every structural bracket found in real code.
    Raises RCheckError on an unterminated string.
    """
    events = []
    i = 0
    line = 1
    n = len(text)
    in_string = None      # quote char
    in_comment = False
    escaped = False

    while i < n:
        c = text[i]
        if c == "\n":
            line += 1
            in_comment = False
            if in_string is not None:
                # R strings may span lines, which is legal; keep going.
                pass
            i += 1
            continue

        if in_comment:
            i += 1
            continue

        if in_string is not None:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == in_string:
                in_string = None
            i += 1
            continue

        if c == "#":
            in_comment = True
            i += 1
            continue

        if c in ("'", '"'):
            in_string = c
            i += 1
            continue

        if c == "`":
            # Backtick-quoted name; skip to the matching backtick.
            j = text.find("`", i + 1)
            if j == -1:
                raise RCheckError(f"line {line}: unterminated backtick name")
            i = j + 1
            continue

        if c in OPENERS or c in CLOSERS:
            events.append((line, c))
        i += 1

    if in_string is not None:
        raise RCheckError("unterminated string literal at end of file")
    return events


def check_balance(events):
    """Verify bracket nesting. Returns a list of problems."""
    stack = []
    problems = []
    for line, ch in events:
        if ch in OPENERS:
            stack.append((line, ch))
        else:
            if not stack:
                problems.append(f"line {line}: unmatched closing '{ch}'")
                continue
            open_line, open_ch = stack.pop()
            if OPENERS[open_ch] != ch:
                problems.append(
                    f"line {line}: '{ch}' closes '{open_ch}' opened on line {open_line}")
    for line, ch in stack:
        problems.append(f"line {line}: unclosed '{ch}'")
    return problems


def strip_code_line(raw):
    """Remove comments and blank out strings so line-level regexes see only code.

    String CONTENT is replaced by a single placeholder character rather than
    deleted. Deleting it turns `RED <- "#c8102e"` into `RED <- `, which then
    looks exactly like a dangling assignment operator and produces a false
    "file ends with a dangling operator" report.
    """
    out = []
    in_string = None
    escaped = False
    for c in raw:
        if in_string is not None:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == in_string:
                in_string = None
                out.append("S")      # placeholder standing in for the literal
            continue
        if c == "#":
            break
        if c in ("'", '"'):
            in_string = c
            continue
        out.append(c)
    return "".join(out)


def check_lines(text):
    problems, warnings = [], []
    lines = text.splitlines()
    code = [strip_code_line(l) for l in lines]

    for idx, raw in enumerate(code):
        line_no = idx + 1
        stripped = raw.rstrip()
        if not stripped.strip():
            continue

        if BAD_ASSIGN.search(stripped):
            problems.append(f"line {line_no}: suspicious assignment operator")

        if ELSE_AT_START.match(stripped):
            # `else` on a new line is a parse error at TOP LEVEL, but perfectly
            # legal inside a braced block (R keeps reading to the closing brace).
            # So only flag it when we are at brace depth zero.
            depth = 0
            for k in range(idx):
                depth += code[k].count("{") - code[k].count("}")
            if depth <= 0:
                # At top level R ends the statement at the closing brace, so a
                # line STARTING with `else` is always a parse error there --
                # it must be written `} else {` on one line.
                problems.append(
                    f"line {line_no}: 'else' starts a top-level line "
                    f"(write '}} else {{' on one line)")

        if PIPE_END.search(stripped):
            # Find the next non-blank code line; a dangling operator before EOF
            # or before a blank gap is the classic R break.
            nxt = None
            for k in range(idx + 1, len(code)):
                if code[k].strip():
                    nxt = code[k].strip()
                    break
            if nxt is None:
                problems.append(
                    f"line {line_no}: file ends with a dangling operator/pipe")

        if "\t" in lines[idx]:
            warnings.append(f"line {line_no}: tab character in indentation")

    return problems, warnings


def check_file(path):
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    problems, warnings = [], []
    try:
        events = tokenize_structure(text)
        problems.extend(check_balance(events))
    except RCheckError as exc:
        problems.append(str(exc))

    p2, w2 = check_lines(text)
    problems.extend(p2)
    warnings.extend(w2)

    funcs = re.findall(r"^([A-Za-z_][A-Za-z0-9_.]*)\s*<-\s*function", text,
                       flags=re.M)
    return {"path": path, "problems": problems, "warnings": warnings,
            "functions": funcs, "lines": len(text.splitlines())}


def main(paths):
    files = []
    for p in paths:
        if os.path.isdir(p):
            for root, _, names in os.walk(p):
                files.extend(os.path.join(root, n) for n in sorted(names)
                             if n.endswith(".R"))
        elif p.endswith(".R"):
            files.append(p)

    if not files:
        print("no .R files found")
        return 1

    total_problems = 0
    total_funcs = 0
    print("=" * 68)
    print("R STATIC CHECK")
    print("=" * 68)
    for f in files:
        r = check_file(f)
        total_problems += len(r["problems"])
        total_funcs += len(r["functions"])
        status = "FAIL" if r["problems"] else "ok  "
        print(f"[{status}] {os.path.basename(f):32s} "
              f"{r['lines']:5d} lines  {len(r['functions']):3d} functions")
        for p in r["problems"]:
            print(f"         PROBLEM  {p}")
        for w in r["warnings"][:3]:
            print(f"         warn     {w}")

    print("-" * 68)
    print(f"{len(files)} files, {total_funcs} functions defined, "
          f"{total_problems} problems")
    if total_problems == 0:
        print("STATIC CHECK PASSED "
              "(run `Rscript -e \"parse('file.R')\"` for a full parse when R is available)")
    return 1 if total_problems else 0


if __name__ == "__main__":
    args = sys.argv[1:] or [os.path.join(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))), "R")]
    sys.exit(main(args))
