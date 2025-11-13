cat > ~/SigilAGI-Local/glyphnotes_worddef_encoder.py <<'EOF'
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GlyphNotes Word-Definition → GlyphString Encoder
================================================

Fully defined, robust encoder for mapping word/definition paragraphs
into canonical glyphstrings using the GlyphMatics Equations core.

Depends on:
    glyphmatics_equations.py  (same directory)

Features
--------
- Parses word/definition data from a text file:
    1) Line mode:   word : definition paragraph...
    2) Block mode:  "### word" header + following lines as paragraph

- Encodes definitions into glyphstrings (2-glyph-per-byte codec)
- Optional channel key for inner-dialog style mixing
- Computes integrity fingerprints for each glyphstring
- Exports a single JSON artifact with metadata + entries
- Can decode and inspect existing JSON files

Usage
-----
# Encode from text file to JSON glyph-lexicon
python3 glyphnotes_worddef_encoder.py encode \
    --in worddefs.txt \
    --out glyph_worddefs.json \
    --channel-key "GlyphNotes-Inner"

# Inspect JSON summary
python3 glyphnotes_worddef_encoder.py inspect glyph_worddefs.json

# Decode one entry back to text
python3 glyphnotes_worddef_encoder.py decode \
    --in glyph_worddefs.json \
    --word EXAMPLE

Input Formats
-------------
1) Line mode (no '### ' headers present):

    energy: The capacity to do work; a scalar physical quantity...

    entropy: A measure of uncertainty or disorder in a system...

2) Block mode (when at least one line starts with '### '):

    ### energy
    The capacity to do work or produce change.
    Often measured in joules in physical systems.

    ### entropy
    A measure of uncertainty, disorder, or information content
    in thermodynamic or information-theoretic contexts.

The parser auto-detects which mode to use.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

# ---------------------------------------------------------------------------
# Dependency: GlyphMatics Equations Core
# ---------------------------------------------------------------------------

try:
    from glyphmatics_equations import (
        glyph_inner_dialog,
        glyph_inner_dialog_decode,
        fingerprint_glyphstring,
        GlyphFingerprint,
    )
except ImportError as e:
    raise SystemExit(
        "ERROR: glyphmatics_equations.py is required and must be "
        "importable from the same directory.\n"
        f"Details: {e}"
    )

# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------

SCHEMA_VERSION = "1.0.0"


@dataclass
class WordDefEntry:
    word: str
    definition: str
    glyphs: str
    glyph_crc: int
    byte_crc: int
    length: int
    entropy_est: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WordDefEntry":
        return cls(
            word=data["word"],
            definition=data["definition"],
            glyphs=data["glyphs"],
            glyph_crc=data["glyph_crc"],
            byte_crc=data["byte_crc"],
            length=data["length"],
            entropy_est=data["entropy_est"],
        )


@dataclass
class WordDefLexicon:
    schema_version: str
    channel_key: Optional[str]
    source_path: str
    entries: List[WordDefEntry]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "channel_key": self.channel_key,
            "source_path": self.source_path,
            "entries": [e.to_dict() for e in self.entries],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WordDefLexicon":
        entries = [WordDefEntry.from_dict(e) for e in data.get("entries", [])]
        return cls(
            schema_version=data.get("schema_version", "0.0.0"),
            channel_key=data.get("channel_key"),
            source_path=data.get("source_path", ""),
            entries=entries,
        )


# ---------------------------------------------------------------------------
# Parsing Word/Definition Source Text
# ---------------------------------------------------------------------------

def _parse_block_mode(lines: List[str]) -> List[Tuple[str, str]]:
    """
    Block mode:

        ### word
        paragraph line 1
        paragraph line 2
        ...
        <blank line>  # optional separator

    Returns list of (word, paragraph).
    """
    result: List[Tuple[str, str]] = []
    current_word: Optional[str] = None
    current_lines: List[str] = []

    def flush():
        nonlocal current_word, current_lines
        if current_word and current_lines:
            paragraph = "\n".join(line.rstrip() for line in current_lines).strip()
            if paragraph:
                result.append((current_word, paragraph))
        current_word = None
        current_lines = []

    for raw in lines:
        line = raw.rstrip("\n")
        if line.startswith("### "):
            flush()
            current_word = line[4:].strip()
            current_lines = []
        else:
            if current_word is not None:
                # Inside a block; collect lines (including blanks, but they
                # are used to structure paragraphs when joined)
                current_lines.append(line)

    flush()
    return result


def _parse_line_mode(lines: List[str]) -> List[Tuple[str, str]]:
    """
    Line mode:

        word : definition paragraph...

    Lines without ':' or with empty segments are skipped.
    Lines starting with '#' are treated as comments.
    """
    result: List[Tuple[str, str]] = []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            continue
        if ":" not in line:
            continue
        head, tail = line.split(":", 1)
        word = head.strip()
        definition = tail.strip()
        if not word or not definition:
            continue
        result.append((word, definition))
    return result


def parse_worddef_file(path: Path) -> List[Tuple[str, str]]:
    """
    Auto-detect and parse either block-mode or line-mode word/definition file.
    """
    with path.open("r", encoding="utf-8") as f:
        lines = f.readlines()

    has_block_header = any(line.startswith("### ") for line in lines)

    if has_block_header:
        entries = _parse_block_mode(lines)
    else:
        entries = _parse_line_mode(lines)

    return entries


# ---------------------------------------------------------------------------
# Encoding Logic
# ---------------------------------------------------------------------------

def encode_entries(
    pairs: List[Tuple[str, str]],
    channel_key: Optional[str],
    min_length: int = 1,
) -> List[WordDefEntry]:
    """
    Encode a list of (word, definition) pairs into glyph entries.

    - min_length filters out definitions shorter than min_length chars.
    - channel_key enables inner-dialog style mixing.
    """
    entries: List[WordDefEntry] = []

    for word, definition in pairs:
        definition = definition.strip()
        if len(definition) < min_length:
            continue

        glyphs = glyph_inner_dialog(definition, channel_key=channel_key)
        fp: GlyphFingerprint = fingerprint_glyphstring(glyphs)

        entry = WordDefEntry(
            word=word,
            definition=definition,
            glyphs=glyphs,
            glyph_crc=fp.glyph_crc,
            byte_crc=fp.byte_crc,
            length=fp.length,
            entropy_est=fp.entropy_est,
        )
        entries.append(entry)

    return entries


def build_lexicon(
    src_path: Path,
    channel_key: Optional[str],
    min_length: int = 1,
) -> WordDefLexicon:
    """
    High-level: parse → encode → package into a WordDefLexicon.
    """
    pairs = parse_worddef_file(src_path)
    entries = encode_entries(pairs, channel_key=channel_key, min_length=min_length)
    return WordDefLexicon(
        schema_version=SCHEMA_VERSION,
        channel_key=channel_key,
        source_path=str(src_path.resolve()),
        entries=entries,
    )


# ---------------------------------------------------------------------------
# JSON I/O
# ---------------------------------------------------------------------------

def save_lexicon(lex: WordDefLexicon, path: Path) -> None:
    payload = lex.to_dict()
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def load_lexicon(path: Path) -> WordDefLexicon:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return WordDefLexicon.from_dict(data)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_encode(args: argparse.Namespace) -> None:
    src_path = Path(args.in_path).expanduser().resolve()
    out_path = Path(args.out_path).expanduser().resolve()
    channel_key = args.channel_key
    min_len = args.min_length

    lex = build_lexicon(src_path, channel_key=channel_key, min_length=min_len)
    save_lexicon(lex, out_path)

    print("⊏⚗$ GlyphNotes word-definition encoding complete ⊐")
    print(f"- Input file : {src_path}")
    print(f"- Output     : {out_path}")
    print(f"- Entries    : {len(lex.entries)}")
    print(f"- Channel key: {channel_key!r}")


def cmd_inspect(args: argparse.Namespace) -> None:
    path = Path(args.in_path).expanduser().resolve()
    lex = load_lexicon(path)

    print("=== GlyphNotes WordDef Lexicon Summary ===")
    print(f"Schema      : {lex.schema_version}")
    print(f"Source path : {lex.source_path}")
    print(f"Channel key : {lex.channel_key!r}")
    print(f"Entries     : {len(lex.entries)}")
    print("------------------------------------------")

    max_show = args.max_entries
    for i, e in enumerate(lex.entries[:max_show]):
        print(f"[{i}] {e.word}")
        print(f"    glyph_len   = {e.length}")
        print(f"    glyph_crc32 = {e.glyph_crc}")
        print(f"    byte_crc32  = {e.byte_crc}")
        print(f"    entropy_est = {e.entropy_est:.3f}")
        print()


def cmd_decode(args: argparse.Namespace) -> None:
    path = Path(args.in_path).expanduser().resolve()
    lex = load_lexicon(path)
    word = args.word
    index = args.index

    entry: Optional[WordDefEntry] = None

    if word:
        for e in lex.entries:
            if e.word == word:
                entry = e
                break
        if entry is None:
            raise SystemExit(f"No entry found for word: {word!r}")
    else:
        if index is None:
            raise SystemExit("Either --word or --index must be provided.")
        if not (0 <= index < len(lex.entries)):
            raise SystemExit(f"Index out of range 0..{len(lex.entries)-1}")
        entry = lex.entries[index]

    print(f"=== Decoding entry: {entry.word} ===")
    print("Stored definition:")
    print(entry.definition)
    print("--------------------------------------")

    # Attempt to decode glyphs back to text via channel key if present.
    try:
        decoded = glyph_inner_dialog_decode(entry.glyphs, channel_key=lex.channel_key)
        print("Decoded from glyphs:")
        print(decoded)
        print("--------------------------------------")
        if decoded == entry.definition:
            print("✓ Round-trip match: decoded text == stored definition")
        else:
            print("⚠ Decoded text differs from stored definition.")
    except Exception as e:
        print(f"✖ Failed to decode glyphs: {e}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="GlyphNotes Word-Definition → GlyphString Encoder"
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # encode
    p_enc = sub.add_parser("encode", help="Encode word/definition text into glyph JSON lexicon")
    p_enc.add_argument(
        "--in",
        dest="in_path",
        type=str,
        required=True,
        help="Input text file with word/definition data",
    )
    p_enc.add_argument(
        "--out",
        dest="out_path",
        type=str,
        required=True,
        help="Output JSON file for glyph lexicon",
    )
    p_enc.add_argument(
        "--channel-key",
        dest="channel_key",
        type=str,
        default=None,
        help="Optional channel key for inner-dialog mixing",
    )
    p_enc.add_argument(
        "--min-length",
        dest="min_length",
        type=int,
        default=1,
        help="Minimum definition length (characters) to include (default: 1)",
    )
    p_enc.set_defaults(func=cmd_encode)

    # inspect
    p_ins = sub.add_parser("inspect", help="Inspect a glyph lexicon JSON file")
    p_ins.add_argument(
        "in_path",
        type=str,
        help="Path to glyph lexicon JSON file",
    )
    p_ins.add_argument(
        "--max-entries",
        dest="max_entries",
        type=int,
        default=20,
        help="Maximum entries to show (default: 20)",
    )
    p_ins.set_defaults(func=cmd_inspect)

    # decode
    p_dec = sub.add_parser("decode", help="Decode one entry from glyph lexicon")
    p_dec.add_argument(
        "--in",
        dest="in_path",
        type=str,
        required=True,
        help="Glyph lexicon JSON file",
    )
    p_dec.add_argument(
        "--word",
        dest="word",
        type=str,
        default=None,
        help="Headword to decode (exact match)",
    )
    p_dec.add_argument(
        "--index",
        dest="index",
        type=int,
        default=None,
        help="Entry index to decode (0-based)",
    )
    p_dec.set_defaults(func=cmd_decode)

    return p


def main(argv: Optional[List[str]] = None) -> None:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
EOF
