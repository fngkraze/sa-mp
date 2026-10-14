"""Minimal CLEO (GTA SA) bytecode disassembler for headerless .cs scripts.

Usage: python -I disasm.py <script.cs> <sa.json> <out.txt>
Uses Sanny Builder's opcode library (sa.json) for names / param counts.
Parameter types are self-describing in SA SCM, so decoding is exact;
names are only annotations.
"""
import json
import struct
import sys

EXT_PRIORITY = ["default", "CLEO", "SAMPFUNCS", "memory", "file", "math",
                "bitwise", "input", "text", "audio", "ini", "debug",
                "clipboard", "CLEO+", "NewOpcodes", "imgui", "Sphere"]


def load_ops(path):
    d = json.load(open(path, encoding="utf8"))
    exts = {e["name"]: e for e in d["extensions"]}
    ops = {}
    for name in reversed(EXT_PRIORITY):
        for c in exts.get(name, {}).get("commands", []):
            ops[int(c["id"], 16)] = (name, c)
    return ops


def read_footer(data):
    """Sanny Builder extra-info footer: last 4 bytes before '__SBFTR\\0' = start offset."""
    if not data.endswith(b"__SBFTR\x00"):
        return len(data), []
    start = struct.unpack_from("<I", data, len(data) - 12)[0]
    hexblocks = []
    if data[start:start + 4] == b"HEX\x00":
        n = struct.unpack_from("<I", data, start + 4)[0]
        for i in range(n):
            off, ln = struct.unpack_from("<II", data, start + 8 + i * 8)
            hexblocks.append((off, ln))
    return start, hexblocks


def read_param(data, p):
    t = data[p]
    p += 1
    if t == 0x00:
        return None, p
    if t == 0x01:
        return ("int", struct.unpack_from("<i", data, p)[0]), p + 4
    if t == 0x02:
        return ("gvar", struct.unpack_from("<H", data, p)[0]), p + 2
    if t == 0x03:
        return ("lvar", struct.unpack_from("<H", data, p)[0]), p + 2
    if t == 0x04:
        return ("int", struct.unpack_from("<b", data, p)[0]), p + 1
    if t == 0x05:
        return ("int", struct.unpack_from("<h", data, p)[0]), p + 2
    if t == 0x06:
        return ("float", struct.unpack_from("<f", data, p)[0]), p + 4
    if t in (0x07, 0x08, 0x0C, 0x0D, 0x12, 0x13):
        off, idx, size, flags = struct.unpack_from("<HHBB", data, p)
        return ("arr", t, off, idx, size, flags), p + 6
    if t == 0x09:
        return ("str8", data[p:p + 8].split(b"\0")[0]), p + 8
    if t in (0x0A, 0x10):
        return ("gsvar", t, struct.unpack_from("<H", data, p)[0]), p + 2
    if t in (0x0B, 0x11):
        return ("lsvar", t, struct.unpack_from("<H", data, p)[0]), p + 2
    if t == 0x0E:
        ln = data[p]
        return ("strv", data[p + 1:p + 1 + ln]), p + 1 + ln
    if t == 0x0F:
        return ("str16", data[p:p + 16].split(b"\0")[0]), p + 16
    # legacy: untyped 8-byte string
    return ("str8", data[p - 1:p + 7].split(b"\0")[0]), p + 7


def fmt(pr):
    k = pr[0]
    if k == "int":
        v = pr[1]
        return str(v)
    if k == "float":
        return repr(round(pr[1], 6))
    if k == "lvar":
        return "%d@" % pr[1]
    if k == "gvar":
        return "$%d" % (pr[1] // 4)
    if k == "lsvar":
        return ("%d@s" if pr[1] == 0x0B else "%d@v") % pr[2]
    if k == "gsvar":
        return ("s$%d" if pr[1] == 0x0A else "v$%d") % (pr[2] // 4)
    if k == "arr":
        _, t, off, idx, size, flags = pr
        base = "%d@" % off if t in (0x08, 0x0D, 0x13) else "$%d" % (off // 4)
        iv = "%d@" % idx if flags & 0x80 else "$%d" % (idx // 4)
        return "%s(%s,%di)" % (base, iv, size)
    if k in ("str8", "str16", "strv"):
        return '"%s"' % pr[1].decode("latin1").replace("\n", "\\n")
    return str(pr)


def label_of(pr):
    if pr and pr[0] == "int" and pr[1] < 0:
        return -pr[1]
    return None


def main():
    src, libp, outp = sys.argv[1:4]
    data = open(src, "rb").read()
    ops = load_ops(libp)
    code_end, hexblocks = read_footer(data)
    hexmap = dict(hexblocks)
    insns = []
    unknown = set()
    p = 0
    while p < code_end:
        if p in hexmap:
            ln = hexmap[p]
            insns.append((p, "hex", data[p:p + ln]))
            p += ln
            continue
        start = p
        raw = struct.unpack_from("<H", data, p)[0]
        p += 2
        neg = bool(raw & 0x8000)
        op = raw & 0x7FFF
        ext, c = ops.get(op, (None, None))
        params = []
        if c is None:
            unknown.add(op)
            # fall back: read typed params until something implausible
            n = None
        else:
            n = c.get("num_params", 0)
            if c.get("attrs", {}).get("is_variadic") or any(
                    i.get("type") == "arguments"
                    for i in c.get("input", []) + c.get("output", [])):
                n = None
        if n is None:
            while p < code_end:
                pr, p = read_param(data, p)
                if pr is None:
                    break
                params.append(pr)
        else:
            for _ in range(n):
                pr, p = read_param(data, p)
                params.append(pr)
        insns.append((start, "op", (neg, op, ext, c, params)))

    labels = set()
    for off, kind, v in insns:
        if kind == "op":
            for pr in v[4]:
                lb = label_of(pr)
                if lb is not None and v[3] and any(
                        i.get("type") == "label" for i in v[3].get("input", [])):
                    labels.add(lb)
    # also catch 0AB1 / jumps whose metadata lacks a label type
    for off, kind, v in insns:
        if kind == "op" and v[1] in (0x0002, 0x004C, 0x004D, 0x0050, 0x0AB1, 0x004F, 0x0A92):
            lb = label_of(v[4][0]) if v[4] else None
            if lb is not None:
                labels.add(lb)

    out = []
    for off, kind, v in insns:
        if off in labels:
            out.append("")
            out.append(":L%04X" % off)
        if kind == "hex":
            out.append("%04X:  hex  %s   ; %r" % (off, v.hex(" "), v))
            continue
        neg, op, ext, c, params = v
        name = c["name"] if c else "UNKNOWN"
        ps = []
        for pr in params:
            lb = label_of(pr)
            if lb is not None and lb in labels:
                ps.append("@L%04X" % lb)
            else:
                ps.append(fmt(pr))
        out.append("%04X:  %s%04X: %s%s %s   [%s]" % (
            off, "8" if neg else "0", op if not neg else op, "not " if neg else "",
            name, " ".join(ps), ext or "?"))
    out.append("")
    out.append("; code end 0x%04X, footer hex blocks %s, unknown opcodes %s" % (
        code_end, [(hex(a), b) for a, b in hexblocks], sorted(hex(u) for u in unknown)))
    open(outp, "w", encoding="utf8").write("\n".join(out))
    print("insns", len(insns), "labels", len(labels), "unknown", sorted(hex(u) for u in unknown))


if __name__ == "__main__":
    main()
