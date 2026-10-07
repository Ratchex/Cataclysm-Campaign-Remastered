"""Syntax-check generated Lua with luaparser (Lua 5 grammar). Our generated code avoids Lua-4/5 differences, so a
clean parse here means HWRM's Lua 4 should load it too. Also reports names called but not defined in the file
(so the runtime can be checked to provide them).

Usage: luacheck.py <file.lua> [runtime.lua ...]
"""
import re
import sys

from luaparser import ast


def main():
    path, runtimes = sys.argv[1], sys.argv[2:]
    src = open(path, encoding="latin-1").read()
    try:
        ast.parse(src)
    except Exception as e:  # noqa: BLE001 - report any parser failure with its position
        print(f"SYNTAX ERROR in {path}: {e}")
        sys.exit(1)
    defined = set(re.findall(r"^function (\w+)\(", src, re.M))
    for r in runtimes:
        defined |= set(re.findall(r"^\s*function (\w+)\(", open(r, encoding="latin-1").read(), re.M))
        defined |= set(re.findall(r"^(\w+)\s*=", open(r, encoding="latin-1").read(), re.M))
    code = re.sub(r"--\[\[.*?\]\]|--[^\n]*", "", src, flags=re.S)
    called = set(re.findall(r"\b([A-Za-z_]\w*)\(", code)) - {"function", "if", "while", "not", "and", "or", "return"}
    missing = sorted(n for n in called if n not in defined and not n.startswith(("KASRule_",)))
    print(f"{path}: syntax OK; {len(defined)} functions defined, {len(missing)} called but not defined")
    if missing:
        print("  " + ", ".join(missing))


if __name__ == "__main__":
    main()
