#!/usr/bin/env python3
"""
G3 Research EA - MQL5 static pre-compile check.

This is NOT a compiler. MetaEditor (Windows/MQL5) is the only authority for
"compile: PASS". This script performs the structural checks that can be made
without it, so that an obvious defect is caught before the MetaEditor run:

  1. balanced braces / parentheses / brackets (string and comment aware)
  2. every #include target resolves
  3. include guards are present and balanced
  4. #ifdef / #ifndef / #endif nesting is balanced
  5. every G3* symbol that is called is defined somewhere in /src
  6. forbidden-construct scan (Master Specification v0.4 section 2 bans)
  7. shift-0 (forming bar) price reads must carry an explicit
     "G3-CHECK: shift0-safe" justification comment

Exit code 0 = all checks pass.
"""
import os
import re
import sys

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")
SRC = os.path.normpath(SRC)

FORBIDDEN = [
    (r"\bholdout\b", "Final Holdout must not be referenced (section 24)"),
    (r"\bmartingale\b", "martingale is forbidden (section 2)"),
    (r"\bnanpin\b", "averaging down is forbidden (section 2)"),
    (r"ACCOUNT_MARGIN_MODE_RETAIL_NETTING", "netting support is forbidden (section 2)"),
    (r"\bWebRequest\b", "external realtime AI/service calls are forbidden (section 2)"),
    (r"\bOptimization\b", "no optimiser helper is allowed (section 17)"),
]

PRICE_COPY = re.compile(r"\bCopy(Close|Open|High|Low|Buffer|Rates|TickVolume)\s*\(")


def strip_code(text):
    """Remove comments and string literals, keep structure characters."""
    out = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == '/' and i + 1 < n and text[i + 1] == '/':
            while i < n and text[i] != '\n':
                i += 1
        elif c == '/' and i + 1 < n and text[i + 1] == '*':
            i += 2
            while i + 1 < n and not (text[i] == '*' and text[i + 1] == '/'):
                i += 1
            i += 2
        elif c == '"':
            i += 1
            while i < n and text[i] != '"':
                i += 2 if text[i] == '\\' else 1
            i += 1
        elif c == "'":
            i += 1
            while i < n and text[i] != "'":
                i += 2 if text[i] == '\\' else 1
            i += 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


def check_balance(path, code, errors):
    pairs = {'}': '{', ')': '(', ']': '['}
    stack = []
    line = 1
    for ch in code:
        if ch == '\n':
            line += 1
        elif ch in "{([":
            stack.append((ch, line))
        elif ch in ")}]":
            if not stack or stack[-1][0] != pairs[ch]:
                errors.append(f"{path}:{line}: unbalanced '{ch}'")
                return
            stack.pop()
    for ch, ln in stack:
        errors.append(f"{path}:{ln}: unclosed '{ch}'")


def check_preprocessor(path, text, errors):
    depth = 0
    for i, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if re.match(r"#\s*(ifndef|ifdef|if)\b", s):
            depth += 1
        elif re.match(r"#\s*endif\b", s):
            depth -= 1
            if depth < 0:
                errors.append(f"{path}:{i}: #endif without matching #if")
                return
    if depth != 0:
        errors.append(f"{path}: {depth} unterminated #if/#ifndef block(s)")


def check_includes(path, text, errors):
    for i, line in enumerate(text.splitlines(), 1):
        m = re.match(r'\s*#include\s+"([^"]+)"', line)
        if m:
            target = os.path.join(os.path.dirname(path), m.group(1))
            if not os.path.exists(target):
                errors.append(f"{path}:{i}: include not found: {m.group(1)}")


def check_forbidden(path, text, errors):
    lowered = text.lower()
    for pattern, why in FORBIDDEN:
        for m in re.finditer(pattern, lowered, re.IGNORECASE):
            line = lowered.count("\n", 0, m.start()) + 1
            ctx = text.splitlines()[line - 1].strip()
            # a prohibition that is only *mentioned* in a comment is fine
            if ctx.startswith("//") or ctx.startswith("*") or ctx.startswith("/*"):
                continue
            errors.append(f"{path}:{line}: forbidden construct ({why}): {ctx}")


def check_shift_zero(path, text, errors):
    lines = text.splitlines()
    for i, line in enumerate(lines, 1):
        if not PRICE_COPY.search(line):
            continue
        args = line.split("(", 1)[1] if "(" in line else ""
        parts = [p.strip() for p in args.split(",")]
        # start position is argument 3 for CopyX(symbol, tf, start, ...)
        # and argument 3 for CopyBuffer(handle, buffer, start, ...)
        if len(parts) >= 3 and parts[2] == "0":
            context = "\n".join(lines[max(0, i - 8):i])
            if "G3-CHECK: shift0-safe" not in context:
                errors.append(
                    f"{path}:{i}: forming-bar (shift 0) read without a "
                    f"'G3-CHECK: shift0-safe' justification: {line.strip()}")


def collect_symbols(files):
    defined, called = {}, {}
    define_re = re.compile(
        r"^\s*(?:[A-Za-z_][A-Za-z0-9_]*\s+)+(G3[A-Za-z0-9_]*)\s*\(", re.M)
    macro_re = re.compile(r"^\s*#define\s+(G3[A-Za-z0-9_]*)", re.M)
    call_re = re.compile(r"\b(G3[A-Za-z0-9_]*)\s*\(")
    for path, code in files.items():
        for m in define_re.finditer(code):
            defined.setdefault(m.group(1), path)
        for m in macro_re.finditer(code):
            defined.setdefault(m.group(1), path)
        for m in call_re.finditer(code):
            called.setdefault(m.group(1), (path, code.count("\n", 0, m.start()) + 1))
    return defined, called


def main():
    errors = []
    files = {}
    names = sorted(os.listdir(SRC))
    for name in names:
        if not (name.endswith(".mqh") or name.endswith(".mq5")):
            continue
        path = os.path.join(SRC, name)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        code = strip_code(text)
        files[path] = code
        check_balance(path, code, errors)
        check_preprocessor(path, text, errors)
        check_includes(path, text, errors)
        check_forbidden(path, text, errors)
        check_shift_zero(path, text, errors)
        if name.endswith(".mqh"):
            guards = re.findall(r"#ifndef\s+(G3_[A-Z0-9_]+_MQH)", text)
            if not guards:
                errors.append(f"{path}: missing include guard")

    defined, called = collect_symbols(files)
    for sym, (path, line) in sorted(called.items()):
        if sym not in defined:
            errors.append(f"{path}:{line}: call to undefined symbol {sym}")

    print(f"files checked : {len(files)}")
    print(f"G3 symbols    : {len(defined)} defined, {len(called)} referenced")
    if errors:
        print(f"\nISSUES: {len(errors)}")
        for e in errors:
            print("  " + e)
        return 1
    print("\nstatic check: OK (0 issues)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
