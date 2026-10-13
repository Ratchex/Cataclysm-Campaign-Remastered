"""Translate Ghidra's decompiled Cataclysm mission code (kas2c output compiled by MSVC) into HWRM Lua 4.

Input:  Cataclysm-decomp/out/missions/<Mission>.c (from DecompileMissions.java after ApplyKasSignatures.java)
Output: <out>.lua - one Lua function per C function, wired like Gearbox's HW1 port (KASRule_Add/KASRule_AddFSM).

Design
- Every KAS API call is emitted by address, `K_<addr>(...)  -- <name>`, and implemented in the runtime
  (data/scripts/scar/cataclysmkas.lua). Names are only comments, so a wrong name can't change behaviour.
- KAS.c helpers become name strings: team / ships / volume / path lookups -> the label string the level uses
  (hashes are matched against the mission's own MissionMan labels with kasLabelHash).
- kasJump / kasFSMCreate become KASRule_Add / KASRule_AddFSM + the Init function, as in Gearbox's port.
- The current team (DAT_00a43ee8) is the TeamName parameter; its ship list (+0x1c) is the TeamName SobGroup.
- Lua 4 has no goto, no booleans (comparisons give 1/nil, 0 is TRUE), no bit operators and no %.
  Structured functions are emitted as structured Lua; functions with goto/switch/continue are lowered to basic
  blocks driven by a `_pc` dispatcher loop. Every C truth test becomes an explicit `~= 0` test.
Unknown constructs are emitted as runtime calls (KAS_Unsupported/KAS_Native) and counted in the report.

Usage: kas2lua.py <decomp_root> <Mission01> <mission_dir> <out.lua>
"""
import csv
import os
import re
import struct
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

# --------------------------------------------------------------------------------------------- data

KAS_LO, KAS_HI, MIS_LO, MIS_HI = 0x490000, 0x4A8000, 0x5D6FE0, 0x672000  # below 0x5d6fe0: JPEG library
TEAM, SCOPE_KIND, SCOPE, LANG = "DAT_00a43ee8", "DAT_00c3749c", "DAT_00c374a0", "DAT_00a6b00c"
TYPES = {"int", "uint", "char", "uchar", "byte", "bool", "short", "ushort", "long", "ulong", "float", "double",
         "float10", "undefined", "undefined1", "undefined2", "undefined4", "undefined8", "code", "void", "sbyte",
         "word", "dword", "longlong", "ulonglong", "int3", "uint3", "_Bool", "unsigned", "signed", "const",
         "LPCSTR", "size_t", "wchar_t"}
LUA_RESERVED = {"and", "break", "do", "else", "elseif", "end", "for", "function", "if", "in", "local", "nil", "not",
                "or", "repeat", "return", "then", "until", "while"}


def kashash(s):
    h = 0
    for c in s.encode("latin-1"):
        h = ((c & 0xDF) + (h << 4)) & 0xFFFFFFFF
        g = h & 0xF0000000
        if g:
            h ^= g >> 24
            h &= ~g & 0xFFFFFFFF
    return h


def read_tsv(p):
    with open(p, encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))


class Data:
    def __init__(self, decomp, mission_dir):
        out = os.path.join(decomp, "out")
        self.api = {int(r["address"], 16): r for r in read_tsv(os.path.join(out, "kas_api.tsv"))}
        self.meta = {r["function"]: r for r in read_tsv(os.path.join(out, "kas_api_meta.tsv"))}
        self.strings = {}
        for r in read_tsv(os.path.join(out, "strings.tsv")):
            self.strings[int(r["address"], 16)] = r["string"].replace("\\n", "\n").replace("\\t", "\t").replace("\\r", "\r")
        self.hash_names = {}
        for r in read_tsv(os.path.join(out, "hash_names.tsv")):
            self.hash_names[int(r["hash"], 16)] = r["names"].split("|")
        self.exe = open(os.path.join(decomp, "bin", "cataclysm.exe"), "rb").read()
        self._sections()
        # labels defined by this mission's MissionMan files: exact names for team/volume/path/point hashes
        self.labels = {}
        for f in os.listdir(mission_dir):
            p = os.path.join(mission_dir, f)
            if not os.path.isfile(p) or not (f.endswith((".mission", ".missphere")) or "." not in f):
                continue
            for line in open(p, encoding="latin-1"):
                m = re.match(r"^(Ships|AIPoint|AIPath|AISphere|AIBox)\s+([^,\s]+)", line)
                if m and m.group(2) != "?":
                    self.labels.setdefault(kashash(m.group(2)), m.group(2))

    def _sections(self):
        b = self.exe
        pe = struct.unpack_from("<I", b, 0x3C)[0]
        n = struct.unpack_from("<H", b, pe + 6)[0]
        opt = struct.unpack_from("<H", b, pe + 20)[0]
        self.base = struct.unpack_from("<I", b, pe + 24 + 28)[0]
        self.secs = [struct.unpack_from("<8sIIII", b, pe + 24 + opt + 40 * i) for i in range(n)]

    def read_u32(self, va):
        for _, vs, rva, rs, raw in self.secs:
            if rva <= va - self.base < rva + rs:
                return struct.unpack_from("<I", self.exe, raw + va - self.base - rva)[0]
        return None

    def read_cstr(self, va):
        if va in self.strings:
            return self.strings[va]
        for _, vs, rva, rs, raw in self.secs:
            if rva <= va - self.base < rva + rs:
                o = raw + va - self.base - rva
                return self.exe[o:self.exe.index(b"\0", o)].decode("latin-1")
        return None

    def label(self, h):
        if h in self.labels:
            return self.labels[h]
        names = self.hash_names.get(h)
        if names:
            mixed = [n for n in names if not (n.islower() or n.isupper())]
            return (mixed or names)[0]
        return None

    def hash_comment(self, h):
        if h & 0x80000000:
            n = self.label(h & 0x7FFFFFFF)
            return f"global {n}" if n else "global"
        return self.label(h)


# --------------------------------------------------------------------------------------------- lexer

TOKEN = re.compile(r"""
    (?P<ws>\s+|/\*.*?\*/|//[^\n]*) |
    (?P<num>0x[0-9a-fA-F]+[uUlL]*|\d+\.\d*(?:[eE][+-]?\d+)?[fF]?|\d+[uUlL]*) |
    (?P<str>"(?:\\.|[^"\\])*") |
    (?P<chr>'(?:\\.|[^'\\])+') |
    (?P<id>[A-Za-z_]\w*) |
    (?P<op>>>=|<<=|->|\+\+|--|<<|>>|<=|>=|==|!=|&&|\|\||\+=|-=|\*=|/=|%=|&=|\|=|\^=|[{}()\[\];,:?.~!%^&*+\-/<>=|])
""", re.S | re.X)


def lex(text):
    toks = []
    for m in TOKEN.finditer(text):
        k = m.lastgroup
        if k != "ws":
            toks.append((k, m.group(0)))
    return toks


# --------------------------------------------------------------------------------------------- parser

class Parser:
    def __init__(self, toks):
        self.t, self.i = toks, 0

    def peek(self, k=0):
        j = self.i + k
        return self.t[j] if j < len(self.t) else ("eof", "")

    def take(self, v=None):
        tok = self.peek()
        if v is not None and tok[1] != v:
            raise SyntaxError(f"expected {v!r} got {tok[1]!r} at token {self.i}")
        self.i += 1
        return tok

    def is_type_start(self, k=0):
        tok = self.peek(k)
        return tok[0] == "id" and (tok[1] in TYPES or tok[1].startswith("undefined"))

    # statements -------------------------------------------------------------
    def block(self):
        self.take("{")
        out = []
        while self.peek()[1] != "}":
            s = self.stmt()
            if s is not None:
                out.extend(s if isinstance(s, list) else [s])
        self.take("}")
        return ("block", out)

    def stmt(self):
        k, v = self.peek()
        if v == "{":
            return self.block()
        if v == ";":
            self.take()
            return None
        if k == "id" and self.peek(1)[1] == ":" and v not in ("default",):
            self.take()
            self.take(":")
            return ("label", v)
        if v == "if":
            self.take()
            self.take("(")
            c = self.expr()
            self.take(")")
            a = self.stmt()
            b = None
            if self.peek()[1] == "else":
                self.take()
                b = self.stmt()
            return ("if", c, a, b)
        if v == "while":
            self.take()
            self.take("(")
            c = self.expr()
            self.take(")")
            return ("while", c, self.stmt())
        if v == "do":
            self.take()
            body = self.stmt()
            self.take("while")
            self.take("(")
            c = self.expr()
            self.take(")")
            self.take(";")
            return ("dowhile", body, c)
        if v == "for":
            self.take()
            self.take("(")
            init = None if self.peek()[1] == ";" else self.expr()
            self.take(";")
            cond = None if self.peek()[1] == ";" else self.expr()
            self.take(";")
            step = None if self.peek()[1] == ")" else self.expr()
            self.take(")")
            return ("for", init, cond, step, self.stmt())
        if v == "switch":
            self.take()
            self.take("(")
            c = self.expr()
            self.take(")")
            self.take("{")
            items = []
            while self.peek()[1] != "}":
                if self.peek()[1] == "case":
                    self.take()
                    val = self.expr()
                    self.take(":")
                    items.append(("case", val))
                elif self.peek()[1] == "default":
                    self.take()
                    self.take(":")
                    items.append(("default",))
                else:
                    s = self.stmt()
                    if s is not None:
                        items.extend(s if isinstance(s, list) else [s])
            self.take("}")
            return ("switch", c, items)
        if v == "return":
            self.take()
            e = None if self.peek()[1] == ";" else self.expr()
            self.take(";")
            return ("return", e)
        if v in ("break", "continue"):
            self.take()
            self.take(";")
            return (v,)
        if v == "goto":
            self.take()
            lbl = self.take()[1]
            self.take(";")
            return ("goto", lbl)
        if self.is_type_start() or (v == "struct"):
            return self.decl()
        e = self.expr()
        self.take(";")
        return ("expr", e)

    def decl(self):
        while self.is_type_start() or self.peek()[1] in ("struct", "*"):
            self.take()
            if self.peek(-1)[1] == "struct":
                self.take()
        out = []
        while True:
            while self.peek()[1] == "*":
                self.take()
            name = self.take()[1]
            size = None
            if self.peek()[1] == "[":
                self.take()
                size = self.expr()
                self.take("]")
            init = None
            if self.peek()[1] == "=":
                self.take()
                init = self.assign()
            out.append(("decl", name, size, init))
            if self.peek()[1] == ",":
                self.take()
                continue
            break
        self.take(";")
        return out

    # expressions ------------------------------------------------------------
    def expr(self):
        e = self.assign()
        while self.peek()[1] == ",":
            self.take()
            e = ("comma", e, self.assign())
        return e

    ASSIGN = {"=", "+=", "-=", "*=", "/=", "%=", "&=", "|=", "^=", "<<=", ">>="}

    def assign(self):
        left = self.binary(0)
        if self.peek()[1] in self.ASSIGN:
            op = self.take()[1]
            return ("assign", op, left, self.assign())
        return left

    LEVELS = [["||"], ["&&"], ["|"], ["^"], ["&"], ["==", "!="], ["<", ">", "<=", ">="], ["<<", ">>"],
              ["+", "-"], ["*", "/", "%"]]

    def binary(self, lvl):
        if lvl == len(self.LEVELS):
            return self.unary()
        left = self.binary(lvl + 1)
        while self.peek()[0] == "op" and self.peek()[1] in self.LEVELS[lvl]:
            op = self.take()[1]
            left = ("bin", op, left, self.binary(lvl + 1))
        return left

    def is_cast(self):
        if self.peek()[1] != "(":
            return False
        j = 1
        if not (self.peek(j)[0] == "id" and (self.peek(j)[1] in TYPES or self.peek(j)[1].startswith("undefined")
                                             or self.peek(j)[1] in ("struct",))):
            return False
        while self.peek(j)[1] not in (")", "eof"):
            if self.peek(j)[0] not in ("id", "op") or self.peek(j)[1] not in TYPES | {"*", "struct"} and \
                    not self.peek(j)[1].startswith("undefined") and self.peek(j)[0] != "id":
                return False
            j += 1
        return True

    def unary(self):
        k, v = self.peek()
        if v in ("-", "!", "~", "*", "&", "++", "--", "+"):
            self.take()
            return ("un", v, self.unary())
        if v == "sizeof":
            self.take()
            self.take("(")
            depth = 1
            while depth:
                t = self.take()[1]
                depth += {"(": 1, ")": -1}.get(t, 0)
            return ("num", 4)
        if self.is_cast():
            self.take("(")
            ty = []
            while self.peek()[1] != ")":
                ty.append(self.take()[1])
            self.take(")")
            return ("cast", " ".join(ty), self.unary())
        return self.postfix()

    def postfix(self):
        e = self.primary()
        while True:
            v = self.peek()[1]
            if v == "(":
                self.take()
                args = []
                while self.peek()[1] != ")":
                    args.append(self.assign())
                    if self.peek()[1] == ",":
                        self.take()
                self.take(")")
                e = ("call", e, args)
            elif v == "[":
                self.take()
                idx = self.expr()
                self.take("]")
                e = ("index", e, idx)
            elif v in ("++", "--"):
                self.take()
                e = ("post", v, e)
            elif v in ("->", "."):
                self.take()
                e = ("member", e, self.take()[1])
            else:
                return e

    def primary(self):
        k, v = self.take()
        if k == "num":
            if v.lower().startswith("0x"):
                return ("num", int(v.rstrip("uUlL"), 16))
            s = v.rstrip("uUlLfF")
            return ("num", float(s) if "." in s else int(s))
        if k == "str":
            return ("str", bytes(v[1:-1], "latin-1").decode("unicode_escape"))
        if k == "chr":
            return ("num", ord(bytes(v[1:-1], "latin-1").decode("unicode_escape")))
        if k == "id":
            return ("id", v)
        if v == "(":
            e = self.expr()
            self.take(")")
            return e
        raise SyntaxError(f"unexpected {v!r}")


def parse_functions(text):
    """Split a DecompileMissions file into (address, name, params, body AST)."""
    funcs = []
    for chunk in re.split(r"^// ---- ", text, flags=re.M)[1:]:
        m = re.match(r"(\S+) @ ([0-9a-f]{8})", chunk)
        name, addr = m.group(1), int(m.group(2), 16)
        if addr < MIS_LO:
            continue
        code = chunk.split("\n", 1)[1]
        hdr = re.search(r"^\S[^\n]*?(\w+)\s*\(([^)]*)\)\s*\n\s*\{", code, re.M)
        if not hdr:
            funcs.append((addr, name, [], None, "no header"))
            continue
        params = [p.split()[-1].lstrip("*") for p in hdr.group(2).split(",") if p.strip() not in ("", "void")]
        body_text = code[hdr.end() - 1:]
        try:
            p = Parser(lex(body_text))
            funcs.append((addr, name, params, p.block(), None))
        except (SyntaxError, IndexError, ValueError) as e:
            funcs.append((addr, name, params, None, f"parse error: {e}"))
    return funcs


# --------------------------------------------------------------------------------------------- translator

class Unsupported(Exception):
    pass


class Translator:
    def __init__(self, data, mission):
        self.d, self.mission = data, mission
        self.report = Counter()
        self.used_api = Counter()
        self.fnames = {}

    # naming ----------------------------------------------------------------
    def fn_name(self, addr):
        return self.fnames.get(addr, f"F_{addr:06x}")

    def lua_ident(self, name):
        return name + "_" if name in LUA_RESERVED else name

    def label_str(self, h, kind):
        n = self.d.label(h & 0x7FFFFFFF)
        if n is None:
            self.report[f"unresolved {kind} hash"] += 1
            return f'"{kind}_{h:08x}"'
        return '"' + n + '"'

    def string_at(self, va):
        s = self.d.read_cstr(va)
        if s is None:
            return None
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "") + '"'

    # expressions: return (lua, kind) with kind in num|bool|str|team|fn ----------------------------
    def num_lit(self, v):
        if isinstance(v, float):
            return repr(v)
        if v >= 0x80000000:
            v -= 0x100000000  # Ghidra prints negative constants as large unsigned values
        return str(v)

    def is_team(self, e):
        return e == ("id", TEAM)

    def strip(self, e):
        while e[0] == "cast":
            e = e[2]
        return e

    def team_field(self, e):
        """Recognise *(T *)(DAT_00a43ee8 + off) and **(...) patterns on the current team."""
        e = self.strip(e)
        if e[0] == "un" and e[1] == "*":
            inner = self.strip(e[2])
            if inner[0] == "un" and inner[1] == "*":
                f = self.team_off(self.strip(inner[2]))
                return ("**", f) if f is not None else None
            f = self.team_off(inner)
            return ("*", f) if f is not None else None
        return None

    def team_off(self, e):
        if e[0] == "bin" and e[1] == "+" and self.is_team(self.strip(e[2])) and e[3][0] == "num":
            return e[3][1]
        return None

    def ex(self, e):
        t = e[0]
        if t == "num":
            return self.num_lit(e[1]), "num"
        if t == "lua":                                    # already translated (simple(): a dropped lookup)
            return e[1], "str"
        if t == "str":
            return '"' + e[1].replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"', "str"
        if t == "cast":
            return self.ex(e[2])
        if t == "id":
            return self.ident(e[1])
        if t == "comma":
            raise Unsupported("comma expression")
        if t == "assign":
            raise Unsupported("assignment inside expression")
        if t == "post":
            raise Unsupported("post-increment inside expression")
        if t == "member":
            raise Unsupported("struct member")
        if t == "index":
            return self.index(e)
        if t == "call":
            return self.call(e)
        if t == "un":
            return self.unop(e)
        if t == "bin":
            return self.binop(e)
        raise Unsupported(f"expr {t}")

    def ident(self, name):
        if name in ("true", "false"):  # Lua 4 has no booleans
            return ("1" if name == "true" else "0"), "num"
        if name == TEAM:
            return "TeamName", "team"
        if name == SCOPE:
            return "KAS_Scope", "num"
        if name == SCOPE_KIND:
            return "KAS_ScopeKind", "num"
        if name == LANG:
            return "0", "num"
        m = re.match(r"s_.*_([0-9a-f]{8})$", name)
        if m:
            s = self.string_at(int(m.group(1), 16))
            if s:
                return s, "str"
        m = re.match(r"(?:FUN|LAB)_([0-9a-f]{8})$", name)
        if m:
            return f'"{self.fn_name(int(m.group(1), 16))}"', "fn"
        m = re.match(r"_?DAT_([0-9a-f]{8})$", name)
        if m:
            self.report["global read"] += 1
            return f'KAS_G({int(m.group(1), 16)})', "num"
        if name.startswith("PTR_"):
            raise Unsupported(f"pointer table {name} without index")
        return self.lua_ident(name), "num"

    def index(self, e):
        base = self.strip(e[1])
        # (&PTR_s_xxx_ADDR)[DAT_00a6b00c] : localized string table -> English entry
        if base[0] == "un" and base[1] == "&" and base[2][0] == "id" and base[2][1].startswith("PTR_"):
            m = re.search(r"_([0-9a-f]{8})$", base[2][1])
            if m:
                ptr = self.d.read_u32(int(m.group(1), 16))
                s = self.string_at(ptr) if ptr else None
                if s:
                    return s, "str"
        raise Unsupported("array index")

    def unop(self, e):
        op, a = e[1], e[2]
        if op == "&":
            inner = self.strip(a)
            if inner[0] == "id":
                m = re.match(r"(?:DAT|LAB|FUN)_([0-9a-f]{8})$", inner[1])
                if m:  # Ghidra shows some hash constants as addresses of data symbols
                    v = int(m.group(1), 16)
                    if inner[1].startswith(("LAB", "FUN")):
                        return f'"{self.fn_name(v)}"', "fn"
                    return self.num_lit(v), "num"
                m = re.match(r"s_.*_([0-9a-f]{8})$", inner[1])
                if m:
                    return self.ident(inner[1])
            raise Unsupported("address-of")
        if op == "*":
            tf = self.team_field(e)
            if tf == ("*", 0x58):
                return "KAS_TeamHash(TeamName)", "num"
            if tf == ("*", 0x50):
                return "KAS_TeamMsgQueue(TeamName)", "num"
            if tf == ("**", 0x50):
                return "KAS_TeamMsgCount(TeamName)", "num"
            raise Unsupported("pointer dereference")
        s, k = self.ex(a)
        if op == "-":
            return f"(-{s})", "num"
        if op == "+":
            return s, k
        if op == "!":
            return f"({self.cond_of(s, k)} == nil)" if False else f"(not {self.cond_of(s, k)})", "bool"
        if op == "~":
            return f"KAS_bnot({s})", "num"
        raise Unsupported(f"unary {op}")

    def cond_of(self, s, k):
        return s if k == "bool" else f"({s} ~= 0)"

    def val_of(self, s, k):
        return f"KAS_B({s})" if k == "bool" else s

    def binop(self, e):
        op, a, b = e[1], e[2], e[3]
        # team ship list: DAT_00a43ee8 + 0x1c
        if op == "+" and self.is_team(self.strip(a)) and b[0] == "num" and b[1] == 0x1C:
            return "TeamName", "team"
        sa, ka = self.ex(a)
        sb, kb = self.ex(b)
        if op in ("&&", "||"):
            return f"({self.cond_of(sa, ka)} {'and' if op == '&&' else 'or'} {self.cond_of(sb, kb)})", "bool"
        if op in ("==", "!=", "<", ">", "<=", ">="):
            lop = {"!=": "~="}.get(op, op)
            if ka == "bool" or kb == "bool":
                sa, sb = self.val_of(sa, ka), self.val_of(sb, kb)
            return f"({sa} {lop} {sb})", "bool"
        sa, sb = self.val_of(sa, ka), self.val_of(sb, kb)
        if op in ("+", "-", "*"):
            return f"({sa} {op} {sb})", "num"
        fn = {"/": "KAS_div", "%": "KAS_mod", "&": "KAS_band", "|": "KAS_bor", "^": "KAS_bxor",
              "<<": "KAS_shl", ">>": "KAS_shr"}[op]
        return f"{fn}({sa}, {sb})", "num"

    # calls -------------------------------------------------------------------
    def callee_addr(self, f):
        f = self.strip(f)
        if f[0] != "id":
            return None, None
        n = f[1]
        m = re.match(r"FUN_([0-9a-f]{8})$", n)
        if m:
            return int(m.group(1), 16), n
        # ApplyKasSignatures.java names every KAS API function K_<addr>: translate by address, never by name
        m = re.match(r"K_([0-9a-f]{6})$", n)
        if m:
            a = int(m.group(1), 16)
            return a, self.d.api.get(a, {}).get("name") or n
        for a, r in self.d.api.items():
            if r["name"] == n and r["score"] == "helper":
                return a, n
        raise Unsupported(f"call to unknown function {n}")

    def arg_values(self, args, ptypes=None):
        out = []
        for i, a in enumerate(args):
            ptype = ptypes[i] if ptypes and i < len(ptypes) else ""
            a0 = self.strip(a)
            if a0[0] == "num" and isinstance(a0[1], int) and "char*" in ptype:
                s = self.string_at(a0[1])
                if s:
                    out.append(s)
                    continue
            if a0[0] == "num" and isinstance(a0[1], int) and ptype == "" and self.d.base <= a0[1] < 0x900000 \
                    and a0[1] % 4 == 0:
                # unnamed function: a pointer into the exe's data at a name (Mission02 passes ship types as
                # 8960500 = "sRecon"); hashes are not 4-aligned addresses of identifiers
                raw = self.d.read_cstr(a0[1])
                if raw and re.match(r"[A-Za-z][A-Za-z0-9_ ]{2,}$", raw):
                    out.append(self.string_at(a0[1]))
                    continue
            s, k = self.ex(a)
            if a0[0] == "num" and isinstance(a0[1], int) and ("udword" in ptype or ptype == ""):
                c = self.d.hash_comment(a0[1]) if a0[1] > 0xFFFF else None
                if c:
                    s = f"{s} --[[{c}]]"
            out.append(self.val_of(s, k))
        return out

    HELPER_KIND = {"kasAITeamPtr": "team", "kasAITeamShipsPtr": "team", "kasVolumePtr": "vol", "kasPathPtr": "path",
                   "kasPathPtrNoErrorChecking": "path", "kasVectorPtr": "vec", "kasGrowSelectionPtr": "gs",
                   "kasGetGrowSelectionPtrIfExists": "gs"}

    def call(self, e):
        addr, name = self.callee_addr(e[1])
        args = e[2]
        if name in self.HELPER_KIND and args and self.strip(args[0])[0] == "num":
            h = self.strip(args[0])[1]
            kind = self.HELPER_KIND[name]
            lbl = self.label_str(h, kind)
            if kind == "gs":
                return f"KAS_GS({lbl})", "str"
            if kind == "vec":
                return f"KAS_Vector({lbl})", "str"
            return lbl, "team" if kind == "team" else "str"
        if name in ("kasTeamsVectorPtr", "kasVolumeVectorPtr") and args:
            a0 = self.strip(args[0])
            lbl = self.label_str(a0[1], "team") if a0[0] == "num" else self.ex(args[0])[0]
            return f"{'KAS_TeamVector' if name == 'kasTeamsVectorPtr' else 'KAS_VolumeVector'}({lbl})", "str"
        if name == "kasThisTeamsVectorPtr":
            return "KAS_TeamVector(TeamName)", "str"
        if name == "kasShipsVectorPtr":
            a0 = self.strip(args[0])
            if a0[0] == "num":       # a selection by hash (Mission02: kasShipsVectorPtr(0xcff5860) = "Smothership")
                return f"KAS_ShipsVector(KAS_GS({self.label_str(a0[1], 'gs')}))", "str"
            return f"KAS_ShipsVector({self.arg_values(args)[0]})", "str"
        if name in ("kasJump", "kasFSMCreate"):
            raise Unsupported(f"{name} used as a value")
        if addr == 0x417EC0:
            return f"KAS_TeamMsgGet({', '.join(self.arg_values(args))})", "num"
        if addr == 0x417E10:
            return f"KAS_MsgSendRaw({', '.join(self.arg_values(args))})", "num"
        if addr is not None and KAS_LO <= addr < KAS_HI:
            r = self.d.api.get(addr, {})
            nm = r.get("name") or ""
            meta = self.d.meta.get(nm)
            ptypes = [p.split(" ")[0] for p in meta["params"].split("; ")] if meta and meta["params"] else None
            self.used_api[(addr, nm)] += 1
            return f"K_{addr:06x}({', '.join(self.arg_values(args, ptypes))})" + (f" --[[{nm}]]" if nm else ""), "num"
        if addr is not None and MIS_LO <= addr < MIS_HI:
            return f"{self.fn_name(addr)}(TeamName)", "num"
        if addr is not None:
            self.report["native call"] += 1
            return f"KAS_Native({addr}{''.join(', ' + a for a in self.arg_values(args))})", "num"
        raise Unsupported(f"call through {name}")

    # statements: simple statements shared by both emitters ---------------------------------------
    def simple(self, s):
        """Translate an expression statement / declaration / special call to Lua lines (no control flow)."""
        if s[0] == "decl":
            return []
        e = s[1]
        pending, self.pending_arg = getattr(self, "pending_arg", None), None
        if e[0] == "call":
            addr, name = self.callee_addr(e[1])
            if name in ("kasJump", "kasFSMCreate"):
                return self.fsm_call(name, e[2])
            if name in self.HELPER_KIND and not e[2][1:]:
                # a lookup whose value is dropped: the argument of the next call, which Ghidra shows with none
                # (Mission02: kasAITeamShipsPtr(0x712bfb4); K_499330(); = K_499330("dMessagePod"))
                self.pending_arg = self.ex(e)[0]
                return []
            if pending and not e[2] and addr is not None and KAS_LO <= addr < KAS_HI:
                e = ("call", e[1], [("lua", pending)])
            # Ghidra shows the result of a call made as a statement as "extraout_EAX" when it is used later.
            if "extraout_EAX" in getattr(self, "cur_locals", ()):
                return [f"extraout_EAX = {self.ex(e)[0]}"]
            return [self.ex(e)[0]]
        if e[0] == "assign":
            op, lhs, rhs = e[1], self.strip(e[2]), e[3]
            if lhs == ("id", SCOPE_KIND):
                return [f"KAS_ScopeKind = {self.val_of(*self.ex(rhs))}"]
            if lhs == ("id", SCOPE):
                return [f"KAS_Scope = {self.val_of(*self.ex(rhs))}"]
            if lhs[0] != "id":
                tgt = self.team_field(("un", "*", lhs)) if lhs[0] == "un" else None
                raise Unsupported("assignment to memory")
            m = re.match(r"_?DAT_([0-9a-f]{8})$", lhs[1])
            v, k = self.ex(rhs)
            v = self.val_of(v, k)
            if op != "=":
                cur = f"KAS_G({int(m.group(1), 16)})" if m else self.lua_ident(lhs[1])
                v = self.ex(("bin", op[:-1], lhs, rhs))[0]
            if m:
                self.report["global write"] += 1
                return [f"KAS_SetG({int(m.group(1), 16)}, {v})"]
            return [f"{self.lua_ident(lhs[1])} = {v}"]
        if e[0] in ("post", "un") and e[1] in ("++", "--"):
            tgt = self.strip(e[2])
            if tgt[0] == "id":
                n = self.lua_ident(tgt[1])
                return [f"{n} = {n} {'+' if e[1] == '++' else '-'} 1"]
            raise Unsupported("increment of memory")
        return [self.ex(e)[0]]

    def fsm_call(self, name, args):
        a = [self.strip(x) for x in args]
        h = a[0][1] if a[0][0] == "num" else None
        init = self.fn_addr(a[1])
        watch = self.fn_addr(a[2])
        winit = f"{self.fn_name(init)}" if init else None
        wwatch = f"{self.fn_name(watch)}" if watch else None
        if name == "kasJump":
            lines = [f"-- kasJump(state {h:#x})" if h is not None else "-- kasJump"]
            lines.append(f'KAS_TraceJump(TeamName, "{self.cur}", "{wwatch}")')
            lines.append(f'KASRule_Add(TeamName, "{wwatch}", "{self.cur}")' if wwatch else "KAS_ClearStateRule(TeamName)")
            if winit:
                lines.append(f"{winit}(TeamName)")
            lines.append("do return end")
            return lines
        team = self.val_of(*self.ex(args[3])) if len(args) > 3 else "TeamName"
        lines = [f"-- kasFSMCreate(fsm {h:#x})" if h is not None else "-- kasFSMCreate"]
        lines.append(f'KASRule_AddFSM({team}, "{wwatch}", "{self.cur}")' if wwatch else f"KAS_ClearFSMRule({team})")
        if winit:
            # C saves CurrentTeamP and the variable scope around the new FSM's Init, then restores them
            lines += ["KAS_Push()", f"{winit}({team})", "KAS_Pop()"]
        return lines

    def fn_addr(self, e):
        if e[0] == "num" and MIS_LO <= e[1] < MIS_HI:
            return e[1]
        if e[0] == "id":
            m = re.match(r"(?:FUN|LAB)_([0-9a-f]{8})$", e[1])
            if m:
                return int(m.group(1), 16)
        if e[0] == "un" and e[1] == "&":
            return self.fn_addr(self.strip(e[2]))
        return None

    # structured emitter ------------------------------------------------------------------------
    _in_cond = False

    def needs_cfg(self, node):
        if isinstance(node, tuple) and node[0] in ("if", "while", "dowhile", "for"):
            cond = {"if": 1, "while": 1, "dowhile": 2, "for": 2}[node[0]]
            self._in_cond = True
            hit = node[cond] is not None and self.needs_cfg(node[cond])
            self._in_cond = False
            if hit:
                return True
        if isinstance(node, list):
            return any(self.needs_cfg(n) for n in node)
        if not isinstance(node, tuple):
            return False
        if node[0] in ("goto", "label", "switch", "continue", "comma"):
            return True
        if node[0] == "assign" and self._in_cond:
            return True
        return any(self.needs_cfg(x) for x in node[1:] if isinstance(x, (tuple, list)))

    def structured(self, node, ind):
        out = []
        p = "  " * ind
        if node is None:
            return out
        t = node[0]
        if t == "block":
            for s in node[1]:
                out += self.structured(s, ind)
        elif t in ("expr", "decl"):
            out += [p + l for l in self.simple(node)]
        elif t == "if":
            c = self.cond_of(*self.ex(node[1]))
            out.append(f"{p}if {c} then")
            out += self.structured(node[2], ind + 1)
            b = node[3]
            while b is not None and b[0] == "if":
                out.append(f"{p}elseif {self.cond_of(*self.ex(b[1]))} then")
                out += self.structured(b[2], ind + 1)
                b = b[3]
            if b is not None:
                out.append(f"{p}else")
                out += self.structured(b, ind + 1)
            out.append(f"{p}end")
        elif t == "while":
            out.append(f"{p}while {self.cond_of(*self.ex(node[1]))} do")
            out += self.structured(node[2], ind + 1)
            out.append(f"{p}end")
        elif t == "dowhile":
            out.append(f"{p}repeat")
            out += self.structured(node[1], ind + 1)
            out.append(f"{p}until not {self.cond_of(*self.ex(node[2]))}")
        elif t == "for":
            if node[1] is not None:
                out += [p + l for l in self.simple(("expr", node[1]))]
            cond = self.cond_of(*self.ex(node[2])) if node[2] is not None else "1"
            out.append(f"{p}while {cond} do")
            out += self.structured(node[4], ind + 1)
            if node[3] is not None:
                out += ["  " + p + l for l in self.simple(("expr", node[3]))]
            out.append(f"{p}end")
        elif t == "return":
            if node[1] is None:
                out.append(f"{p}do return end")
            else:
                out.append(f"{p}do return {self.val_of(*self.ex(node[1]))} end")
        elif t == "break":
            out.append(f"{p}break")
        else:
            raise Unsupported(f"statement {t}")
        return out

    # CFG emitter -------------------------------------------------------------------------------
    def cfg(self, body):
        blocks = [[]]          # list of lists of lines; terminator appended as lines
        cur = [0]
        labels = {}

        def new():
            blocks.append([])
            return len(blocks) - 1

        def lbl(name):
            if name not in labels:
                labels[name] = new()
            return labels[name]

        def emit(line):
            blocks[cur[0]].append(line)

        def jump(target):
            emit(f"_pc = {target}")

        def start(b):
            cur[0] = b

        def branch(c, bt, bf):
            """Emit a conditional jump, lowering &&, ||, !, comma and assignments into separate blocks."""
            c0 = self.strip(c)
            if c0[0] == "bin" and c0[1] in ("&&", "||"):
                mid = new()
                if c0[1] == "&&":
                    branch(c0[2], mid, bf)
                else:
                    branch(c0[2], bt, mid)
                start(mid)
                branch(c0[3], bt, bf)
                return
            if c0[0] == "un" and c0[1] == "!":
                branch(c0[2], bf, bt)
                return
            if c0[0] == "comma":
                for l in self.simple(("expr", c0[1])):
                    emit(l)
                branch(c0[2], bt, bf)
                return
            if c0[0] == "assign":
                for l in self.simple(("expr", c0)):
                    emit(l)
                branch(c0[2], bt, bf)
                return
            emit(f"if {self.cond_of(*self.ex(c))} then _pc = {bt} else _pc = {bf} end")

        def walk(node, brk, cont):
            if node is None:
                return
            t = node[0]
            if t == "block":
                for s in node[1]:
                    walk(s, brk, cont)
            elif t in ("expr", "decl"):
                lines = self.simple(node)
                if lines and lines[-1] == "do return end":  # kasJump: ends the function
                    for l in lines[:-1]:
                        emit(l)
                    emit("do return end")
                    start(new())
                else:
                    for l in lines:
                        emit(l)
            elif t == "label":
                b = lbl(node[1])
                jump(b)
                start(b)
            elif t == "goto":
                jump(lbl(node[1]))
                start(new())
            elif t == "if":
                bt, after = new(), None
                bf = new() if node[3] is not None else None
                after = new()
                branch(node[1], bt, bf if bf is not None else after)
                start(bt)
                walk(node[2], brk, cont)
                jump(after)
                if bf is not None:
                    start(bf)
                    walk(node[3], brk, cont)
                    jump(after)
                start(after)
            elif t == "while":
                head, body_b, after = new(), new(), new()
                jump(head)
                start(head)
                branch(node[1], body_b, after)
                start(body_b)
                walk(node[2], after, head)
                jump(head)
                start(after)
            elif t == "dowhile":
                body_b, test, after = new(), new(), new()
                jump(body_b)
                start(body_b)
                walk(node[1], after, test)
                jump(test)
                start(test)
                branch(node[2], body_b, after)
                start(after)
            elif t == "for":
                if node[1] is not None:
                    for l in self.simple(("expr", node[1])):
                        emit(l)
                head, body_b, step, after = new(), new(), new(), new()
                jump(head)
                start(head)
                if node[2] is not None:
                    branch(node[2], body_b, after)
                else:
                    jump(body_b)
                start(body_b)
                walk(node[4], after, step)
                jump(step)
                start(step)
                if node[3] is not None:
                    for l in self.simple(("expr", node[3])):
                        emit(l)
                jump(head)
                start(after)
            elif t == "switch":
                emit(f"_sw = {self.val_of(*self.ex(node[1]))}")
                after = new()
                case_blocks, default_b = [], None
                for it in node[2]:
                    if it[0] == "case":
                        case_blocks.append((self.val_of(*self.ex(it[1])), new()))
                    elif it[0] == "default":
                        default_b = new()
                tests = " else".join(f"if _sw == {v} then _pc = {b}" for v, b in case_blocks) if case_blocks else ""
                fallback = default_b if default_b is not None else after
                emit((tests + f" else _pc = {fallback} end") if tests else f"_pc = {fallback}")
                start(new())
                ci = iter(case_blocks)
                for it in node[2]:
                    if it[0] in ("case", "default"):
                        b = next(ci)[1] if it[0] == "case" else default_b
                        jump(b)   # fallthrough from the previous case
                        start(b)
                    else:
                        walk(it, after, cont)
                jump(after)
                start(after)
            elif t == "return":
                if node[1] is None:
                    emit("do return end")
                else:
                    emit(f"do return {self.val_of(*self.ex(node[1]))} end")
                start(new())
            elif t == "break":
                if brk is None:
                    raise Unsupported("break outside loop")
                jump(brk)
                start(new())
            elif t == "continue":
                jump(cont)
                start(new())
            else:
                raise Unsupported(f"statement {t}")

        walk(body, None, None)
        emit("do return end")
        lines = ["local _pc, _sw = 0, 0", "while 1 do"]
        first = True
        for i, b in enumerate(blocks):
            if not b:
                continue
            lines.append(f"  {'if' if first else 'elseif'} _pc == {i} then")
            first = False
            lines += ["    " + l for l in b]
        lines += ["  end", "end"]
        return lines

    # functions ---------------------------------------------------------------------------------
    def function(self, addr, name, params, body):
        lname = self.fn_name(addr)
        self.cur = lname
        locals_ = []

        def collect(node):
            if isinstance(node, tuple):
                if node[0] == "decl":
                    locals_.append(self.lua_ident(node[1]))
                for x in node[1:]:
                    collect(x)
            elif isinstance(node, list):
                for x in node:
                    collect(x)
        collect(body)
        self.cur_locals = set(locals_)
        head = [f"-- {name} @ {addr:08x}", f"function {lname}(TeamName)"]
        pre = ["  KAS_Team = TeamName"]  # the C code reads the current team from a global (CurrentTeamP)
        if locals_:
            for i in range(0, len(locals_), 20):
                chunk = locals_[i:i + 20]
                pre.append(f"  local {', '.join(chunk)} = {', '.join('0' for _ in chunk)}")
        try:
            if self.needs_cfg(body):
                lines = self.cfg(body)
                self.report["cfg functions"] += 1
            else:
                lines = self.structured(body, 0)
                self.report["structured functions"] += 1
            return head + pre + ["  " + l for l in lines] + ["end", ""]
        except Unsupported as ex:
            self.report[f"unsupported: {ex}"] += 1
            return head + [f'  KAS_Unsupported("{lname}", "{ex}")', "end", ""]


# --------------------------------------------------------------------------------------------- driver

def main():
    decomp, mission, mission_dir, out = sys.argv[1:5]
    d = Data(decomp, mission_dir)
    # The linker folded identical functions across missions (COMDAT folding), so a mission can reference state
    # functions that live in another mission's address range. Index every mission file and translate the
    # transitive closure of functions reachable from this mission's Init/Watch.
    mdir = os.path.join(decomp, "out", "missions")
    index = {}
    for fn in sorted(os.listdir(mdir)):
        if fn.endswith(".c"):
            for f in parse_functions(open(os.path.join(mdir, fn), encoding="utf-8", errors="replace").read()):
                index[f[0]] = f
    tr = Translator(d, mission)
    for addr, (_, name, _, _, _) in index.items():
        if name.startswith(("Init_", "Watch_")):
            tr.fnames[addr] = name
    roots = [a for a, f in index.items() if f[1] in (f"Init_{mission}", f"Watch_{mission}")]
    lines = [f"-- {mission}.lua: generated by tools/kas2lua.py from Ghidra's decompile of cataclysm.exe.",
             "-- Do not edit; regenerate. Calls K_<addr> are KAS API functions implemented in cataclysmkas.lua.", ""]
    parse_fail, done, todo = 0, set(), list(roots)
    order = []
    while todo:
        a = todo.pop()
        if a in done or a not in index:
            continue
        done.add(a)
        order.append(a)
        before = len(lines)
        addr, name, params, body, err = index[a]
        if body is None:
            parse_fail += 1
            lines += [f"-- {name} @ {addr:08x}: {err}", f"function {tr.fn_name(addr)}(TeamName)",
                      f'  KAS_Unsupported("{tr.fn_name(addr)}", "parse")', "end", ""]
            continue
        lines += tr.function(addr, name, params, body)
        for ref in re.findall(r"\bF_([0-9a-f]{6})\b", "\n".join(lines[before:])):
            r = int(ref, 16)
            if r not in done:
                todo.append(r)
    funcs = [index[a] for a in order]
    missing = sorted({int(m, 16) for m in re.findall(r"\bF_([0-9a-f]{6})\b", "\n".join(lines))} - done)
    if missing:
        tr.report["referenced functions not decompiled"] = len(missing)
    # Lua 4 has no block comments: "--" always runs to the end of the line. Move every inline --[[note]] to a
    # trailing comment so it can't swallow the rest of an expression.
    def trailing(line):
        notes = re.findall(r"--\[\[(.*?)\]\]", line)
        if not notes:
            return line
        return re.sub(r"\s*--\[\[.*?\]\]", "", line) + "  -- " + "; ".join(notes)
    lines = [trailing(l) for l in lines]
    # label -> kasLabelHash, so the runtime can give a team's hash (variable scope) without bit arithmetic in Lua 4
    # (and every vector name: kasfVectorSet & co. get the hash, KAS_Vector the name)
    vec_names = {n for n in re.findall(r'KAS_Vector\("([A-Za-z]\w*)"\)', "\n".join(lines))
                 if not n.startswith("vec_")}        # unresolved: the runtime keys those "vec_%08x" too
    labels = sorted(set(d.labels.values()) | {mission} | vec_names)
    lines += ["KAS_LabelHash = KAS_LabelHash or {}"]
    lines += [f'KAS_LabelHash["{n}"] = {kashash(n)}' for n in labels]
    with open(out, "w", encoding="latin-1", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    print(f"{out}: {len(funcs)} functions ({parse_fail} parse failures)")
    for k, v in sorted(tr.report.items()):
        print(f"  {k}: {v}")
    print(f"  KAS API functions used: {len(tr.used_api)}")


if __name__ == "__main__":
    main()
