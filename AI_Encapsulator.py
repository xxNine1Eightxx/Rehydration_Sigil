cat > ~/SigilAGI-Local/gngm_superparagraph_encoder.py <<'EOF'
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GNGM Superparagraph Encapsulator Encoder
=======================================

This component takes a "superparagraph" — a structured unit of meaning
(word, definition, glyphstring, semantic metadata, crosslinks) — and
encodes it as a **GNGM container page** using the GLYPH-LLM v2/v3 framing.

OUTPUT FORMAT:
 - A single Braille-encoded line suitable for durable archival in .txt books.
 - Fully reversible via the included decode pipeline.

DEPENDENCIES:
 - Python stdlib only (json, struct, zlib, binascii)

LOGICAL PIPELINE:
 superparagraph → v2_leaf → compressed_v2+CRC → v3_page → compressed_v3+CRC → Braille_line
"""

import json, struct, zlib, binascii
from pathlib import Path
from typing import Dict, Any, List

MAGIC = b"GLYPHLLM"
BRAILLE_BASE = 0x2800

# -----------------------
# Low-level helpers
# -----------------------
def u8(x):  return struct.pack("<B", x & 0xFF)
def u16(x): return struct.pack("<H", x & 0xFFFF)
def u32(x): return struct.pack("<I", x & 0xFFFFFFFF)
def f32(x): return struct.pack("<f", float(x))

def crc32(b: bytes) -> int:
    return binascii.crc32(b) & 0xFFFFFFFF

def to_braille(b: bytes) -> str:
    return "".join(chr(BRAILLE_BASE + (x & 0xFF)) for x in b)

def from_braille(text: str) -> bytes:
    return bytes((ord(ch)-BRAILLE_BASE) & 0xFF
                 for ch in text if 0x2800 <= ord(ch) <= 0x28FF)


# -----------------------
# V2 LEAF ENCODER
# -----------------------
def encode_v2_leaf(v2_meta: Dict[str, Any],
                   blocks: List[Dict[str, Any]]) -> bytes:
    """
    Encode an inner v2 leaf.
    blocks = [{ "name": str, "payload": bytes,
                "ndim": int, "vmin": float, "vmax": float }]
    """

    # header
    out = MAGIC + u8(2)

    # meta
    meta_bytes = json.dumps(
        v2_meta, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    out += u16(len(meta_bytes)) + meta_bytes

    # blocks
    for blk in blocks:
        nm = blk["name"].encode("ascii")[:255]
        payload = blk["payload"]

        out += (
            u8(1) +                     # type = BLOB
            u8(len(nm)) + nm +          # name
            u16(blk["ndim"]) +          # dims
            f32(blk["vmin"]) +
            f32(blk["vmax"]) +
            u32(len(payload)) + payload
        )

    # optional terminator
    out += u8(0)

    # compress + crc
    comp = zlib.compress(out, 9)
    return comp + u32(crc32(comp))


# -----------------------
# V3 PAGE ENCODER
# -----------------------
def encode_v3_page(title: str,
                   v2_framed: bytes,
                   extra_meta: Dict[str, Any] | None=None) -> bytes:

    meta = {
        "comp": "book_page",
        "title": title,
        "page_index": 1,
        "page_count": 1,
        "inner_version": 2,
        "scheme": "single-leaf"
    }
    if extra_meta:
        meta.update(extra_meta)

    meta_bytes = json.dumps(
        meta, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")

    out = (
        MAGIC +
        u8(3) +
        u16(len(meta_bytes)) + meta_bytes +
        u32(len(v2_framed)) +
        v2_framed
    )

    comp = zlib.compress(out, 9)
    return comp + u32(crc32(comp))


# -----------------------
# GNGM SUPERPARAGRAPH ENCODER
# -----------------------
def encode_superparagraph(sp: Dict[str, Any],
                          title: str="GNGM-SUPERPARAGRAPH") -> str:
    """
    SUPERPARAGRAPH FORMAT (input):
    {
      "word": "entropy",
      "definition": "...",
      "glyphs": "✱✶✷★…",
      "meta": {
          "pos": "noun",
          "language": "en",
          "tags": ["physics","information"]
      }
    }

    Produces a single-line Braille page.
    """

    # ---- prepare v2 leaf ----
    v2_meta = {
        "comp": "superparagraph",
        "version": "1.0.0",
        "word": sp.get("word"),
        "meta": sp.get("meta", {})
    }

    # embed full superparagraph JSON as payload
    payload = json.dumps(
        sp, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")

    blocks = [{
        "name": "superparagraph",
        "ndim": 0,
        "vmin": 0.0,
        "vmax": 0.0,
        "payload": payload
    }]

    v2_framed = encode_v2_leaf(v2_meta, blocks)
    v3_framed = encode_v3_page(title, v2_framed)

    # ---- wrap with Braille ----
    line = (
        f"⧈ΩϞ⧉ GNGM:{title} •" +
        to_braille(v3_framed) +
        "• ⧉ϞΩ⧈"
    )
    return line


# -----------------------
# DECODER
# -----------------------
def decode_superparagraph(line: str) -> Dict[str, Any]:
    """
    Reverse the full GNGM pipeline:
    Braille → framed_v3 → raw_v3 → framed_v2 → raw_v2 → blocks → superparagraph
    """
    # extract bytes
    b = from_braille(line)

    # ----- verify+unzip v3 -----
    comp3, crc3 = b[:-4], b[-4:]
    if crc32(comp3) != int.from_bytes(crc3, "little"):
        raise ValueError("V3 CRC mismatch")

    v3_raw = zlib.decompress(comp3)
    if v3_raw[:8] != MAGIC or v3_raw[8] != 3:
        raise ValueError("Bad V3 MAGIC or version")

    off = 9
    mlen = int.from_bytes(v3_raw[off:off+2], "little")
    off += 2
    # meta3 = json.loads(v3_raw[off:off+mlen])
    off += mlen

    inner_len = int.from_bytes(v3_raw[off:off+4], "little")
    off += 4
    framed_v2 = v3_raw[off:off+inner_len]

    # ----- verify+unzip v2 -----
    comp2, crc2 = framed_v2[:-4], framed_v2[-4:]
    if crc32(comp2) != int.from_bytes(crc2, "little"):
        raise ValueError("V2 CRC mismatch")

    v2_raw = zlib.decompress(comp2)
    if v2_raw[:8] != MAGIC or v2_raw[8] != 2:
        raise ValueError("Bad V2 MAGIC or version")

    off2 = 9
    mlen2 = int.from_bytes(v2_raw[off2:off2+2], "little")
    off2 += 2
    # meta2 = json.loads(v2_raw[off2:off2+mlen2])
    off2 += mlen2

    # read blocks
    blocks=[]
    while off2 < len(v2_raw):
        btype = v2_raw[off2]
        off2 += 1
        if btype == 0:
            break

        nlen = v2_raw[off2]; off2 += 1
        name = v2_raw[off2:off2+nlen].decode("ascii", "ignore")
        off2 += nlen

        ndim = int.from_bytes(v2_raw[off2:off2+2], "little"); off2 += 2
        vmin = struct.unpack_from("<f", v2_raw, off2)[0]; off2 += 4
        vmax = struct.unpack_from("<f", v2_raw, off2)[0]; off2 += 4
        plen = int.from_bytes(v2_raw[off2:off2+4], "little"); off2 += 4
        payload = v2_raw[off2:off2+plen]; off2 += plen

        blocks.append({"name": name, "payload": payload})

    # superparagraph block
    blk = next(b for b in blocks if b["name"] == "superparagraph")
    return json.loads(blk["payload"].decode("utf-8"))


# -----------------------
# CLI
# -----------------------
if __name__ == "__main__":
    import argparse, sys
    ap = argparse.ArgumentParser(
        description="GNGM Superparagraph Encapsulator"
    )
    ap.add_argument("--encode", action="store_true")
    ap.add_argument("--decode", action="store_true")
    ap.add_argument("--in_json")
    ap.add_argument("--out_txt")
    ap.add_argument("--line")

    args = ap.parse_args()

    if args.encode:
        if not args.in_json or not args.out_txt:
            raise SystemExit("--encode requires --in_json and --out_txt")
        sp = json.loads(Path(args.in_json).read_text())
        line = encode_superparagraph(sp, title=sp.get("word","SP"))
        Path(args.out_txt).write_text(line)
        print("✓ Encoded line →", args.out_txt)
        sys.exit(0)

    if args.decode:
        if not args.line:
            raise SystemExit("--decode requires --line")
        sp = decode_superparagraph(args.line)
        print(json.dumps(sp, indent=2, ensure_ascii=False))
        sys.exit(0)

EOF
