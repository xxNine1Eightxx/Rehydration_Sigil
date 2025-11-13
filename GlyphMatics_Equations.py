cat > ~/SigilAGI-Local/glyphmatics_equations.py <<'EOF'
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GlyphMatics Equations — Core Glyph Algebra for GlyphNotes / SigilAGI

This module defines:
  - A canonical 111-glyph alphabet
  - Algebra over glyphstrings (GlyphMatic Equations)
  - A 2-glyph-per-byte codec using base-111 arithmetic
  - Text/bytes <-> glyphstring round-trip encoders
  - Basic metrics (distance, similarity) and integrity checks

All operations are:
  - Deterministic
  - Invertible where specified
  - Safe for inner-dialog and glyphstore encoding
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Iterable, Tuple, Optional
import zlib
import math

# ---------------------------------------------------------------------------
# 1. Canonical 111-Glyph Alphabet
# ---------------------------------------------------------------------------

GLYPH_ALPHABET: List[str] = [
    "✶", "✷", "✸", "✹", "✺", "✻", "✼", "✽", "✾", "✿",
    "❀", "❁", "❂", "❃", "❄", "❅", "❆", "❇", "❈", "❉",
    "❊", "❋", "❖", "❘", "❙", "❚", "❛", "❜", "❝", "❞",
    "❡", "❢", "❣", "❤", "❥", "❦", "❧", "⟡", "⟢", "⟣",
    "⟤", "⟥", "⟦", "⟧", "⟨", "⟩", "⟪", "⟫", "⟬", "⟭",
    "⟮", "⟯", "⧈", "⧉", "⧊", "⧋", "⧌", "⧍", "⧎", "⧏",
    "⬒", "⬓", "⬔", "⬕", "⬖", "⬗", "⬘", "⬙", "⬚", "⬛",
    "⬜", "⬝", "⬞", "⬟", "★", "☆", "✦", "✧", "✩", "✪",
    "✫", "✬", "✭", "✮", "✯", "✰", "☀", "☁", "☂", "☃",
    "☄", "☇", "☈", "☉", "☊", "☋", "☌", "☍", "☗", "☖",
    "♠", "♣", "♥", "♦", "♤", "♧", "♡", "♢", "⚗", "⊏",
    "⊐",
]

ALPHABET_SIZE: int = len(GLYPH_ALPHABET)
if ALPHABET_SIZE != 111:
    raise RuntimeError(f"Glyph alphabet must have length 111, got {ALPHABET_SIZE}")

GLYPH_TO_INDEX: Dict[str, int] = {g: i for i, g in enumerate(GLYPH_ALPHABET)}
INDEX_TO_GLYPH: Dict[int, str] = {i: g for i, g in enumerate(GLYPH_ALPHABET)}


# ---------------------------------------------------------------------------
# 2. Core GlyphMatic Equations (Algebra over glyphstrings)
# ---------------------------------------------------------------------------

def normalize_glyphstring(s: str) -> str:
    """
    Strip whitespace and keep only characters in GLYPH_ALPHABET.
    This is the canonical form used by all algebraic operations.
    """
    return "".join(c for c in s if c in GLYPH_TO_INDEX)


def glen(s: str) -> int:
    """
    Glyph length (number of glyphs, not bytes).

    Equation:
        GLEN(s) = |normalize_glyphstring(s)|

    Equivalent to len() after normalization.
    """
    return len(normalize_glyphstring(s))


def gcat(a: str, b: str) -> str:
    """
    Glyph concatenation.

    Equation:
        GCAT(a, b) = normalize(a) || normalize(b)
    """
    return normalize_glyphstring(a) + normalize_glyphstring(b)


def _glyph_add_idx(i: int, j: int) -> int:
    """
    Modular addition over glyph indices.

    Equation:
        ADD(i, j) = (i + j) mod 111
    """
    return (i + j) % ALPHABET_SIZE


def _glyph_sub_idx(i: int, j: int) -> int:
    """
    Modular subtraction over glyph indices.

    Equation:
        SUB(i, j) = (i - j) mod 111
    """
    return (i - j) % ALPHABET_SIZE


def gadd(a: str, b: str) -> str:
    """
    Pointwise modular addition of two glyphstrings.

    Equation (broadcasting on shorter string):

        Let A = normalize(a), B = normalize(b)
        For k from 0..max(len(A), len(B)) - 1:

           i_k = index(A[k mod len(A)])
           j_k = index(B[k mod len(B)])
           r_k = (i_k + j_k) mod 111

        GADD(a, b) = ⨁_k glyph(r_k)

    This is useful for creating derived channels or
    secret mixing layers between glyphstreams.
    """
    A = normalize_glyphstring(a)
    B = normalize_glyphstring(b)
    if not A or not B:
        return A or B

    out: List[str] = []
    n = max(len(A), len(B))
    for k in range(n):
        gi = GLYPH_TO_INDEX[A[k % len(A)]]
        gj = GLYPH_TO_INDEX[B[k % len(B)]]
        out.append(INDEX_TO_GLYPH[_glyph_add_idx(gi, gj)])
    return "".join(out)


def gsub(a: str, b: str) -> str:
    """
    Pointwise modular subtraction of two glyphstrings.

    Equation:

        GSub(a, b) = GAdd(a, NEG(b))

    implemented as index subtraction.
    """
    A = normalize_glyphstring(a)
    B = normalize_glyphstring(b)
    if not A or not B:
        return A or ""

    out: List[str] = []
    n = max(len(A), len(B))
    for k in range(n):
        gi = GLYPH_TO_INDEX[A[k % len(A)]]
        gj = GLYPH_TO_INDEX[B[k % len(B)]]
        out.append(INDEX_TO_GLYPH[_glyph_sub_idx(gi, gj)])
    return "".join(out)


def ginv(s: str) -> str:
    """
    Glyph inverse under index reflection.

    Equation:

        For each glyph g with index i:
            INV(i) = (111 - 1 - i)
        GINV(s) = ⨁ glyph(INV(index(g)))

    This is a simple involution:
        GINV(GINV(s)) = s  (for normalized s)
    """
    A = normalize_glyphstring(s)
    out: List[str] = []
    for g in A:
        idx = GLYPH_TO_INDEX[g]
        inv = (ALPHABET_SIZE - 1 - idx) % ALPHABET_SIZE
        out.append(INDEX_TO_GLYPH[inv])
    return "".join(out)


def gdist(a: str, b: str) -> float:
    """
    Glyphstring distance (normalized Hamming-like distance).

    Equation:

        Let A,B be normalized and padded via repetition to length N = max(|A|,|B|).
        D(A,B) = (1/N) * Σ_k [ index(A_k) ⊕ index(B_k) != 0 ]

    Value in [0, 1]. 0 means identical (under repetition), 1 means completely
    non-matching indices.
    """
    A = normalize_glyphstring(a)
    B = normalize_glyphstring(b)
    if not A and not B:
        return 0.0
    if not A or not B:
        return 1.0

    n = max(len(A), len(B))
    mismatches = 0
    for k in range(n):
        gi = GLYPH_TO_INDEX[A[k % len(A)]]
        gj = GLYPH_TO_INDEX[B[k % len(B)]]
        if gi != gj:
            mismatches += 1
    return mismatches / float(n)


def gsim(a: str, b: str) -> float:
    """
    Glyphstring similarity.

    Equation:
        GSIM(a, b) = 1 - GDIST(a, b)
    """
    return 1.0 - gdist(a, b)


# ---------------------------------------------------------------------------
# 3. 2-Glyph-Per-Byte Codec (Base-111 arithmetic)
# ---------------------------------------------------------------------------

# Design:
#   Encode a byte b in [0,255] as pair (hi, lo) with:
#
#       hi = b // 111      ∈ {0,1,2}
#       lo = b % 111       ∈ {0..110}
#
#   Each pair corresponds to:
#
#       code = hi * 111 + lo  ∈ [0, 333)
#
#   We only use the first 256 codes; when decoding:
#
#       b = hi * 111 + lo
#       if b >= 256 -> error (invalid glyphstream for this codec)


def _byte_to_pair(b: int) -> Tuple[int, int]:
    if not (0 <= b <= 255):
        raise ValueError(f"Byte out of range: {b}")
    hi = b // ALPHABET_SIZE
    lo = b % ALPHABET_SIZE
    return hi, lo


def _pair_to_byte(hi: int, lo: int) -> int:
    if not (0 <= hi < ALPHABET_SIZE and 0 <= lo < ALPHABET_SIZE):
        raise ValueError(f"Index out of range: hi={hi}, lo={lo}")
    code = hi * ALPHABET_SIZE + lo
    if code >= 256:
        raise ValueError(f"Invalid glyph pair: code={code} >= 256")
    return code


def encode_bytes_to_glyphs(data: bytes) -> str:
    """
    Encode a bytes object into a glyphstring using 2 glyphs per byte.

    Equation:

        For each byte b:
           (hi,lo) = BYTE_TO_PAIR(b)
           g_hi    = glyph(hi)
           g_lo    = glyph(lo)
        Concatenate all (g_hi g_lo).

    Result length = 2 * len(data)
    """
    out: List[str] = []
    for b in data:
        hi, lo = _byte_to_pair(b)
        out.append(INDEX_TO_GLYPH[hi])
        out.append(INDEX_TO_GLYPH[lo])
    return "".join(out)


def decode_glyphs_to_bytes(s: str) -> bytes:
    """
    Decode a glyphstring back into bytes using the 2-glyph-per-byte codec.

    Requirements:
      - glyphstring length must be even
      - all glyphs must be in GLYPH_ALPHABET
      - pairs must correspond to codes < 256

    Raises ValueError on invalid encoding.
    """
    s_norm = normalize_glyphstring(s)
    if len(s_norm) % 2 != 0:
        raise ValueError("Glyphstring length must be even for 2-glyph-per-byte codec.")
    out = bytearray()
    for i in range(0, len(s_norm), 2):
        g_hi = s_norm[i]
        g_lo = s_norm[i + 1]
        hi = GLYPH_TO_INDEX[g_hi]
        lo = GLYPH_TO_INDEX[g_lo]
        b = _pair_to_byte(hi, lo)
        out.append(b)
    return bytes(out)


def encode_text_to_glyphs(text: str, encoding: str = "utf-8") -> str:
    """
    Encode arbitrary text to glyphstring.

    Equation:
        GLYPH(text) = encode_bytes_to_glyphs(text.encode(encoding))
    """
    return encode_bytes_to_glyphs(text.encode(encoding))


def decode_glyphs_to_text(s: str, encoding: str = "utf-8") -> str:
    """
    Decode glyphstring to text.

    Equation:
        text = decode_glyphs_to_bytes(s).decode(encoding)
    """
    return decode_glyphs_to_bytes(s).decode(encoding, errors="strict")


# ---------------------------------------------------------------------------
# 4. Integrity & Fingerprints
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GlyphFingerprint:
    """
    Compact fingerprint for a glyphstring.

    Fields:
        glyph_crc   : CRC32 over utf-8 bytes of glyphstring
        byte_crc    : CRC32 over decoded bytes (if decodable; else 0)
        length      : glyph length
        entropy_est : crude entropy estimate from byte frequencies (0..8)
    """
    glyph_crc: int
    byte_crc: int
    length: int
    entropy_est: float


def glyph_crc32(s: str) -> int:
    """
    CRC32 over the UTF-8 representation of the glyphstring.
    """
    return zlib.crc32(normalize_glyphstring(s).encode("utf-8")) & 0xFFFFFFFF


def _entropy_estimate(data: bytes) -> float:
    """
    Crude Shannon entropy estimate in bits per byte.
    """
    if not data:
        return 0.0
    freq = {}
    for b in data:
        freq[b] = freq.get(b, 0) + 1
    n = len(data)
    h = 0.0
    for c in freq.values():
        p = c / n
        h -= p * math.log2(p)
    return h


def fingerprint_glyphstring(s: str) -> GlyphFingerprint:
    """
    Compute a GlyphFingerprint for a glyphstring.

    If the glyphstring cannot be decoded under the 2-glyph-per-byte codec,
    byte_crc and entropy_est are set to 0.
    """
    s_norm = normalize_glyphstring(s)
    crc_g = glyph_crc32(s_norm)
    try:
        data = decode_glyphs_to_bytes(s_norm)
        crc_b = zlib.crc32(data) & 0xFFFFFFFF
        ent = _entropy_estimate(data)
    except Exception:
        crc_b = 0
        ent = 0.0

    return GlyphFingerprint(
        glyph_crc=crc_g,
        byte_crc=crc_b,
        length=len(s_norm),
        entropy_est=ent,
    )


# ---------------------------------------------------------------------------
# 5. High-Level Utilities for GlyphNotes / SigilAGI
# ---------------------------------------------------------------------------

def glyph_inner_dialog(text: str, channel_key: Optional[str] = None) -> str:
    """
    Convert human text into a glyph-only inner dialog string.

    Steps:
        1. Encode text as glyphstring (2 glyphs per byte).
        2. If channel_key is provided, mix via GADD with key-glyphs
           derived from channel_key.
    """
    base = encode_text_to_glyphs(text)
    if not channel_key:
        return base
    key_glyphs = encode_text_to_glyphs(channel_key)
    mixed = gadd(base, key_glyphs)
    return mixed


def glyph_inner_dialog_decode(glyphs: str, channel_key: Optional[str] = None) -> str:
    """
    Inverse of glyph_inner_dialog(text, channel_key).

    If channel_key was used, we undo the mixing via GSub.
    """
    s_norm = normalize_glyphstring(glyphs)
    if not channel_key:
        return decode_glyphs_to_text(s_norm)

    key_glyphs = encode_text_to_glyphs(channel_key)
    unmixed = gsub(s_norm, key_glyphs)
    return decode_glyphs_to_text(unmixed)


# ---------------------------------------------------------------------------
# 6. Self-test (optional)
# ---------------------------------------------------------------------------

def _self_test() -> None:
    """
    Minimal self-test to validate round-trip properties.
    """
    msg = "SigilAGI / GlyphNotes Canonical Test"
    g = encode_text_to_glyphs(msg)
    back = decode_glyphs_to_text(g)
    assert back == msg, "Text <-> glyph round-trip failed"

    g2 = gadd(g, ginv(g))
    # g + inv(g) should yield a constant glyphstring, but we only assert length
    assert glen(g2) == glen(g), "GADD + GINV length invariant failed"

    fp = fingerprint_glyphstring(g)
    assert fp.length == glen(g), "Fingerprint length mismatch"

    # Inner dialog round-trip
    key = "inner-channel-key"
    ch = glyph_inner_dialog(msg, key)
    back2 = glyph_inner_dialog_decode(ch, key)
    assert back2 == msg, "Inner dialog channel round-trip failed"


if __name__ == "__main__":
    _self_test()
    print("✓ glyphmatics_equations: self-test passed.")
EOF
