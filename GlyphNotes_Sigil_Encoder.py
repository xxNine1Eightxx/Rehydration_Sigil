cat > ~/SigilAGI-Local/glyphnotes_sigil_encoder.py <<'EOF'
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GlyphNotes Sigil Encoder
========================

Word-definition GLYPH STRINGS → SINGLE-CHARACTER REHYDRATION SIGILS

This component takes a GlyphNotes word/definition lexicon (where each entry
already has a glyphstring representation) and assigns a UNIQUE SINGLE UNICODE
CHARACTER per entry, forming a compact "rehydration sigil" code.

Each sigil is:
  - A single Unicode Private-Use-Area (PUA) character (by default U+E000+N)
  - Uniquely bound to a word + glyphstring + integrity fingerprints
  - Fully rehydratable back to definition + glyphstring

Inputs
------
- A JSON file created by glyphnotes_worddef_encoder.py
  (schema_version=1.0.0, entries[] with .glyphs, .word, .definition, etc.)

Outputs
-------
- A JSON sigil lexicon:
    - schema_version
    - source_lexicon
    - base_codepoint
    - entries: list of:
        {
          word,
          definition,
          glyphs,
          glyph_crc,
          byte_crc,
          glyph_length,
          entropy_est,
          sigil,
          codepoint,
          index
        }

Usage
-----
# 1) Encode sigils from an existing glyph lexicon
python3 glyphnotes_sigil_encoder.py encode \
    --in glyph_worddefs.json \
    --out glyph_worddefs_sigil.json

# 2) Inspect sigil assignment summary
python3 glyphnotes_sigil_encoder.py inspect glyph_worddefs_sigil.json

# 3) Decode a sigil back to word + definition
python3 glyphnotes_sigil_encoder.py decode \
    --in glyph_worddefs_sigil.json \
    --sigil ""

# 4) Decode by word
python3 glyphnotes_sigil_encoder.py decode \
    --in glyph_worddefs_sigil.json \
    --word "energy"

# 5) Convert a sequence of words into sigil string
python3 glyphnotes_sigil_encoder.py encode-text \
    --in glyph_worddefs_sigil.json \
    --text "energy entropy"

# 6) Convert a sigil string back to words
python3 glyphnotes_sigil_encoder.py decode-text \
    --in glyph_worddefs_sigil.json \
    --sigils ""
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Any, List, Optional

import zlib

SCHEMA_VERSION = "1.0.0"

# Default Private-Use-Area block: U+E000..U+F8FF (6400 codepoints)
DEFAULT_BASE_CODEPOINT = 0xE000
DEFAULT_MAX_SIGILS = 6400


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class SigilEntry:
    word: str
    definition: str
    glyphs: str
    glyph_crc: int
    byte_crc: int
    glyph_length: int
    entropy_est: float
    sigil: str
    codepoint: str
    index: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SigilEntry":
        return cls(
            word=data["word"],
            definition=data["definition"],
            glyphs=data["glyphs"],
            glyph_crc=int(data["glyph_crc"]),
            byte_crc=int(data["byte_crc"]),
            glyph_length=int(data["glyph_length"]),
            entropy_est=float(data["entropy_est"]),
            sigil=data["sigil"],
            codepoint=data["codepoint"],
            index=int(data["index"]),
        )


@dataclass
class SigilLexicon:
    schema_version: str
    source_lexicon: str
    base_codepoint: int
    entries: List[SigilEntry]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_lexicon": self.source_lexicon,
            "base_codepoint": f"U+{self.base_codepoint:04X}",
            "entries": [e.to_dict() for e in self.entries],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SigilLexicon":
        base_str = data.get("base_codepoint", "U+E000")
        if isinstance(base_str, str) and base_str.startswith("U+"):
            base_codepoint = int(base_str[2:], 16)
        else:
            base_codepoint = int(base_str)

        entries = [SigilEntry.from_dict(e) for e in data.get("entries", [])]
        return cls(
            schema_version=data.get("schema_version", "0.0.0"),
            source_lexicon=data.get("source_lexicon", ""),
            base_codepoint=base_codepoint,
            entries=entries,
        )


# ---------------------------------------------------------------------------
# Helpers for reading the glyph lexicon produced by glyphnotes_worddef_encoder
# ---------------------------------------------------------------------------

def load_worddef_lexicon(path: Path) -> Dict[str, Any]:
    """
    Load the word-definition glyph lexicon created by glyphnotes_worddef_encoder.py.
    This function is schema-tolerant but expects:
      - data["entries"] list
      - each entry has .word, .definition, .glyphs, .glyph_crc, .byte_crc,
        .length or glyph_length, and entropy_est
    """
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data


# ---------------------------------------------------------------------------
# Sigil assignment
# ---------------------------------------------------------------------------

def _crc32(text: str) -> int:
    return zlib.crc32(text.encode("utf-8")) & 0xFFFFFFFF


def assign_sigils(
    worddef_data: Dict[str, Any],
    base_codepoint: int = DEFAULT_BASE_CODEPOINT,
    max_sigils: int = DEFAULT_MAX_SIGILS,
) -> SigilLexicon:
    """
    Assign a UNIQUE single-character sigil to each word/definition glyph entry,
    using contiguous codepoints starting at base_codepoint.

    If there are more entries than max_sigils, raise an error.

    worddef_data is the JSON decoded content of glyph_worddefs.json.
    """

    raw_entries = worddef_data.get("entries", [])
    n = len(raw_entries)
    if n == 0:
        raise ValueError("Input glyph lexicon has no entries.")

    if n > max_sigils:
        raise ValueError(
            f"Too many entries ({n}) for the configured sigil capacity ({max_sigils}). "
            "Increase max_sigils or use a different base codepoint range."
        )

    sigil_entries: List[SigilEntry] = []
    used_sigils: Dict[str, str] = {}

    for idx, e in enumerate(raw_entries):
        word = e.get("word", "").strip()
        definition = e.get("definition", "").strip()
        glyphs = e.get("glyphs", "")

        if not word or not glyphs:
            # Skip malformed entries
            continue

        # Integrity values: prefer stored; if missing, compute simple CRCs.
        glyph_crc = int(e.get("glyph_crc", _crc32(glyphs)))
        byte_crc = int(e.get("byte_crc", _crc32(glyphs)))
        glyph_length = int(e.get("length", len(glyphs)))
        entropy_est = float(e.get("entropy_est", 0.0))

        codepoint_int = base_codepoint + idx
        sigil_char = chr(codepoint_int)
        codepoint_str = f"U+{codepoint_int:04X}"

        if sigil_char in used_sigils:
            raise ValueError(
                f"Sigil collision at index {idx} (codepoint {codepoint_str}) "
                f"between words {used_sigils[sigil_char]!r} and {word!r}."
            )

        used_sigils[sigil_char] = word

        sig_entry = SigilEntry(
            word=word,
            definition=definition,
            glyphs=glyphs,
            glyph_crc=glyph_crc,
            byte_crc=byte_crc,
            glyph_length=glyph_length,
            entropy_est=entropy_est,
            sigil=sigil_char,
            codepoint=codepoint_str,
            index=idx,
        )
        sigil_entries.append(sig_entry)

    source_lexicon = worddef_data.get("source_path", "")

    return SigilLexicon(
        schema_version=SCHEMA_VERSION,
        source_lexicon=source_lexicon,
        base_codepoint=base_codepoint,
        entries=sigil_entries,
    )


# ---------------------------------------------------------------------------
# JSON I/O for SigilLexicon
# ---------------------------------------------------------------------------

def save_sigil_lexicon(lex: SigilLexicon, path: Path) -> None:
    payload = lex.to_dict()
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def load_sigil_lexicon(path: Path) -> SigilLexicon:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return SigilLexicon.from_dict(data)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_encode(args: argparse.Namespace) -> None:
    in_path = Path(args.in_path).expanduser().resolve()
    out_path = Path(args.out_path).expanduser().resolve()
    base_codepoint = int(args.base_codepoint, 16) if args.base_codepoint.startswith("0x") else int(args.base_codepoint, 16) if args.base_codepoint.startswith("U+") else int(args.base_codepoint, 16) if args.base_codepoint.upper().startswith("U+") else int(args.base_codepoint, 0)

    # Normalize base_codepoint arg:
    # Accept formats: "U+E000", "0xE000", "E000", "57344", etc.
    bc_arg = args.base_codepoint.strip().upper()
    if bc_arg.startswith("U+"):
        base = int(bc_arg[2:], 16)
    elif bc_arg.startswith("0X"):
        base = int(bc_arg, 16)
    elif all(c in "0123456789ABCDEF" for c in bc_arg):
        # bare hex
        base = int(bc_arg, 16)
    else:
        # decimal
        base = int(bc_arg, 10)

    worddef_data = load_worddef_lexicon(in_path)
    lex = assign_sigils(worddef_data, base_codepoint=base, max_sigils=args.max_sigils)
    save_sigil_lexicon(lex, out_path)

    print("⊏⚗$ GlyphNotes sigil encoding complete ⊐")
    print(f"- Input lexicon : {in_path}")
    print(f"- Output sigils : {out_path}")
    print(f"- Base codepoint: U+{lex.base_codepoint:04X}")
    print(f"- Entries       : {len(lex.entries)}")


def cmd_inspect(args: argparse.Namespace) -> None:
    path = Path(args.in_path).expanduser().resolve()
    lex = load_sigil_lexicon(path)

    print("=== Sigil Lexicon Summary ===")
    print(f"Schema        : {lex.schema_version}")
    print(f"Source lexicon: {lex.source_lexicon}")
    print(f"Base codepoint: U+{lex.base_codepoint:04X}")
    print(f"Entries       : {len(lex.entries)}")
    print("------------------------------")

    max_entries = args.max_entries
    for i, e in enumerate(lex.entries[:max_entries]):
        print(f"[{i}] {e.word} → {e.sigil} ({e.codepoint})")
        print(f"    glyph_len   = {e.glyph_length}")
        print(f"    glyph_crc32 = {e.glyph_crc}")
        print(f"    byte_crc32  = {e.byte_crc}")
        print(f"    entropy_est = {e.entropy_est:.3f}")
        print()


def _build_index_maps(lex: SigilLexicon):
    by_word: Dict[str, SigilEntry] = {}
    by_sigil: Dict[str, SigilEntry] = {}
    for e in lex.entries:
        if e.word not in by_word:
            by_word[e.word] = e
        if e.sigil not in by_sigil:
            by_sigil[e.sigil] = e
    return by_word, by_sigil


def cmd_decode(args: argparse.Namespace) -> None:
    path = Path(args.in_path).expanduser().resolve()
    lex = load_sigil_lexicon(path)
    by_word, by_sigil = _build_index_maps(lex)

    entry: Optional[SigilEntry] = None

    if args.word:
        entry = by_word.get(args.word)
        if entry is None:
            raise SystemExit(f"No entry for word {args.word!r}")
    elif args.sigil:
        if len(args.sigil) != 1:
            raise SystemExit("Sigil must be exactly one character.")
        entry = by_sigil.get(args.sigil)
        if entry is None:
            raise SystemExit(f"No entry for sigil {args.sigil!r}")
    else:
        raise SystemExit("Must provide --word or --sigil.")

    print(f"=== Rehydration for: {entry.word} ===")
    print(f"Sigil      : {entry.sigil} ({entry.codepoint})")
    print(f"Glyph len  : {entry.glyph_length}")
    print(f"Glyph CRC32: {entry.glyph_crc}")
    print(f"Byte  CRC32: {entry.byte_crc}")
    print()
    print("Definition:")
    print(entry.definition)
    print()
    print("Glyph string:")
    print(entry.glyphs)


def cmd_encode_text(args: argparse.Namespace) -> None:
    """
    Take a plain text of words and convert to a sigil string, e.g.:

        "energy entropy" → ""

    Words not in the lexicon are skipped (or optionally raise).
    """
    path = Path(args.in_path).expanduser().resolve()
    lex = load_sigil_lexicon(path)
    by_word, _ = _build_index_maps(lex)

    text = args.text.strip()
    if not text:
        raise SystemExit("Empty --text provided.")

    tokens = text.split()
    sigils: List[str] = []
    missing: List[str] = []

    for tok in tokens:
        e = by_word.get(tok)
        if e is None:
            missing.append(tok)
            continue
        sigils.append(e.sigil)

    sigil_str = "".join(sigils)

    print("=== Text → Sigils ===")
    print(f"Input text : {text!r}")
    print(f"Sigil text : {sigil_str!r}")
    if missing:
        print()
        print("Missing words (not in lexicon):")
        for m in missing:
            print(f" - {m}")


def cmd_decode_text(args: argparse.Namespace) -> None:
    """
    Take a sigil string and convert back to words, e.g.:

        "" → "energy entropy"
    """
    path = Path(args.in_path).expanduser().resolve()
    lex = load_sigil_lexicon(path)
    _, by_sigil = _build_index_maps(lex)

    sigil_text = args.sigils
    if not sigil_text:
        raise SystemExit("Empty --sigils provided.")

    words: List[str] = []
    missing: List[str] = []

    for ch in sigil_text:
        e = by_sigil.get(ch)
        if e is None:
            missing.append(ch)
            continue
        words.append(e.word)

    word_seq = " ".join(words)

    print("=== Sigils → Text ===")
    print(f"Sigil text : {sigil_text!r}")
    print(f"Words      : {word_seq!r}")
    if missing:
        print()
        print("Missing sigils (no mapping):")
        for m in missing:
            cp = f"U+{ord(m):04X}"
            print(f" - {m!r} ({cp})")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Word-definition glyphstrings → single-character rehydration sigil encoder"
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # encode
    p_enc = sub.add_parser("encode", help="Assign unique single-character sigils to glyph lexicon entries")
    p_enc.add_argument(
        "--in",
        dest="in_path",
        type=str,
        required=True,
        help="Input glyph lexicon JSON (from glyphnotes_worddef_encoder.py)",
    )
    p_enc.add_argument(
        "--out",
        dest="out_path",
        type=str,
        required=True,
        help="Output sigil lexicon JSON",
    )
    p_enc.add_argument(
        "--base-codepoint",
        dest="base_codepoint",
        type=str,
        default="U+E000",
        help="Base codepoint (default: U+E000, accepts U+E000 / 0xE000 / E000 / 57344)",
    )
    p_enc.add_argument(
        "--max-sigils",
        dest="max_sigils",
        type=int,
        default=DEFAULT_MAX_SIGILS,
        help=f"Maximum entries/sigils (default: {DEFAULT_MAX_SIGILS})",
    )
    p_enc.set_defaults(func=cmd_encode)

    # inspect
    p_ins = sub.add_parser("inspect", help="Inspect a sigil lexicon")
    p_ins.add_argument(
        "in_path",
        type=str,
        help="Sigil lexicon JSON file",
    )
    p_ins.add_argument(
        "--max-entries",
        dest="max_entries",
        type=int,
        default=20,
        help="Maximum entries to display (default: 20)",
    )
    p_ins.set_defaults(func=cmd_inspect)

    # decode
    p_dec = sub.add_parser("decode", help="Decode a single sigil or word back to definition + glyphs")
    p_dec.add_argument(
        "--in",
        dest="in_path",
        type=str,
        required=True,
        help="Sigil lexicon JSON file",
    )
    p_dec.add_argument(
        "--word",
        dest="word",
        type=str,
        default=None,
        help="Word to decode",
    )
    p_dec.add_argument(
        "--sigil",
        dest="sigil",
        type=str,
        default=None,
        help="Single-character sigil to decode",
    )
    p_dec.set_defaults(func=cmd_decode)

    # encode-text
    p_et = sub.add_parser("encode-text", help="Convert a sequence of words into sigil string")
    p_et.add_argument(
        "--in",
        dest="in_path",
        type=str,
        required=True,
        help="Sigil lexicon JSON file",
    )
    p_et.add_argument(
        "--text",
        dest="text",
        type=str,
        required=True,
        help="Plain text sequence of words (space-separated)",
    )
    p_et.set_defaults(func=cmd_encode_text)

    # decode-text
    p_dt = sub.add_parser("decode-text", help="Convert a sigil string back to word sequence")
    p_dt.add_argument(
        "--in",
        dest="in_path",
        type=str,
        required=True,
        help="Sigil lexicon JSON file",
    )
    p_dt.add_argument(
        "--sigils",
        dest="sigils",
        type=str,
        required=True,
        help="String of sigil characters",
    )
    p_dt.set_defaults(func=cmd_decode_text)

    return p


def main(argv: Optional[List[str]] = None) -> None:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
EOF
