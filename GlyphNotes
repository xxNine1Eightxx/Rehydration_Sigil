

cat > glyphnotes_component.py <<'EOF'
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
GlyphNotes(918) Component for SigilAGI-Local

Features:
- Manages a persistent glyph alphabet (glyph_alphabet.json).
- Provides 2-glyph-per-byte encoding/decoding for arbitrary UTF-8 text.
- Stores glyph notes in glyphnotes_db.json with metadata, tags, and round-trip text.
- CLI for:
    - encode/decode text
    - add/list/show notes
    - export/import DB
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


ROOT = Path(__file__).resolve().parent

ALPHABET_PATH = ROOT / "glyph_alphabet.json"
DB_PATH = ROOT / "glyphnotes_db.json"


# ---------------------------------------------------------------------------
# Fallback alphabet
# ---------------------------------------------------------------------------

# GlyphNotes_111
FALLBACK_ALPHABET = list(
✶ ✷ ✸ ✹ ✺ ✻ ✼ ✽ ✾ ✿
❀ ❁ ❂ ❃ ❄ ❅ ❆ ❇ ❈ ❉
❊ ❋ ❖ ❘ ❙ ❚ ❛ ❜ ❝ ❞
❡ ❢ ❣ ❤ ❥ ❦ ❧ ⟡ ⟢ ⟣
⟤ ⟥ ⟦ ⟧ ⟨ ⟩ ⟪ ⟫ ⟬ ⟭
⟮ ⟯ ⧈ ⧉ ⧊ ⧋ ⧌ ⧍ ⧎ ⧏
⬒ ⬓ ⬔ ⬕ ⬖ ⬗ ⬘ ⬙ ⬚ ⬛
⬜ ⬝ ⬞ ⬟ ★ ☆ ✦ ✧ ✩ ✪
✫ ✬ ✭ ✮ ✯ ✰ ☀ ☁ ☂ ☃
☄ ☇ ☈ ☉ ☊ ☋ ☌ ☍ ☗ ☖
♠ ♣ ♥ ♦ ♤ ♧ ♡ ♢ ⚗ ⊏
⊐
)


# ---------------------------------------------------------------------------
# Alphabet Management
# ---------------------------------------------------------------------------

def load_alphabet() -> List[str]:
    """
    Load the glyph alphabet from glyph_alphabet.json.
    If it does not exist, initialize with FALLBACK_ALPHABET and save it.
    """
    if ALPHABET_PATH.exists():
        try:
            with ALPHABET_PATH.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list) or not all(isinstance(x, str) for x in data):
                raise ValueError("alphabet file is not a list of strings")
            if len(data) < 16:
                raise ValueError("alphabet length must be >= 16 for encoding")
            return data
        except Exception as e:
            print(f"⚠ Failed to load glyph alphabet, using fallback: {e}", file=sys.stderr)

    # Initialize with fallback
    alphabet = FALLBACK_ALPHABET[:]
    try:
        with ALPHABET_PATH.open("w", encoding="utf-8") as f:
            json.dump(alphabet, f, indent=2, ensure_ascii=False)
        print(f"✓ Initialized fallback alphabet → {ALPHABET_PATH}")
    except Exception as e:
        print(f"⚠ Failed to write fallback alphabet: {e}", file=sys.stderr)

    return alphabet


def save_alphabet(alphabet: List[str]) -> None:
    """
    Save a new alphabet to glyph_alphabet.json.
    """
    if len(alphabet) < 16:
        raise ValueError("alphabet length must be >= 16")
    with ALPHABET_PATH.open("w", encoding="utf-8") as f:
        json.dump(list(alphabet), f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Glyph Encoder / Decoder (2 glyphs per byte)
# ---------------------------------------------------------------------------

@dataclass
class GlyphEncoder:
    alphabet: List[str]

    def __post_init__(self) -> None:
        if len(self.alphabet) < 16:
            raise ValueError("alphabet length must be >= 16")
        self.index: Dict[str, int] = {ch: i for i, ch in enumerate(self.alphabet)}
        self.base: int = len(self.alphabet)

    def bytes_to_glyphs(self, data: bytes) -> str:
        """
        Encode bytes into glyph string using 2 glyphs per byte.
        Requires base^2 >= 256.
        """
        if self.base * self.base < 256:
            raise ValueError("alphabet too small: base^2 must be >= 256")

        out_chars: List[str] = []
        for b in data:
            hi = b // self.base
            lo = b % self.base
            if hi >= self.base:
                # Should not happen if base^2 >= 256
                raise ValueError(f"cannot encode byte {b} with base {self.base}")
            out_chars.append(self.alphabet[hi])
            out_chars.append(self.alphabet[lo])
        return "".join(out_chars)

    def glyphs_to_bytes(self, glyphs: str) -> bytes:
        """
        Decode glyph string back into bytes.
        Expects even length; each pair -> one byte.
        """
        if len(glyphs) % 2 != 0:
            raise ValueError("glyph string length must be even")

        out = bytearray()
        chars = list(glyphs)
        for i in range(0, len(chars), 2):
            g1, g2 = chars[i], chars[i + 1]
            if g1 not in self.index or g2 not in self.index:
                raise ValueError(f"unknown glyphs in pair: {g1}{g2}")
            hi = self.index[g1]
            lo = self.index[g2]
            value = hi * self.base + lo
            if value > 255:
                raise ValueError(f"decoded value {value} out of byte range")
            out.append(value)
        return bytes(out)

    def text_to_glyphs(self, text: str) -> str:
        """
        Encode UTF-8 text to glyph string.
        """
        return self.bytes_to_glyphs(text.encode("utf-8"))

    def glyphs_to_text(self, glyphs: str) -> str:
        """
        Decode glyph string to UTF-8 text.
        """
        data = self.glyphs_to_bytes(glyphs)
        return data.decode("utf-8", errors="strict")


# ---------------------------------------------------------------------------
# GlyphNotes DB
# ---------------------------------------------------------------------------

@dataclass
class GlyphNote:
    id: str
    name: str
    lang: str
    tags: List[str]
    created_at: float
    updated_at: float
    text: str
    glyphs: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GlyphNote":
        return cls(
            id=data["id"],
            name=data["name"],
            lang=data.get("lang", "und"),
            tags=list(data.get("tags", [])),
            created_at=float(data.get("created_at", time.time())),
            updated_at=float(data.get("updated_at", time.time())),
            text=data.get("text", ""),
            glyphs=data.get("glyphs", ""),
        )


@dataclass
class GlyphNotesDB:
    meta: Dict[str, Any]
    entries: List[GlyphNote]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "meta": self.meta,
            "entries": [e.to_dict() for e in self.entries],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GlyphNotesDB":
        return cls(
            meta=dict(data.get("meta", {})),
            entries=[GlyphNote.from_dict(e) for e in data.get("entries", [])],
        )


def load_db() -> GlyphNotesDB:
    if DB_PATH.exists():
        try:
            with DB_PATH.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return GlyphNotesDB.from_dict(data)
        except Exception as e:
            print(f"⚠ Failed to load glyphnotes db: {e}", file=sys.stderr)

    db = GlyphNotesDB(
        meta={
            "created_at": time.time(),
            "updated_at": time.time(),
            "version": "1.0.0",
        },
        entries=[],
    )
    save_db(db)
    print(f"✓ Initialized new glyphnotes db → {DB_PATH}")
    return db


def save_db(db: GlyphNotesDB) -> None:
    db.meta["updated_at"] = time.time()
    tmp_path = DB_PATH.with_suffix(".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(db.to_dict(), f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, DB_PATH)


def add_note(
    encoder: GlyphEncoder,
    name: str,
    text: str,
    lang: str = "und",
    tags: Optional[List[str]] = None,
) -> GlyphNote:
    db = load_db()
    tags = tags or []

    glyphs = encoder.text_to_glyphs(text)
    now = time.time()

    note = GlyphNote(
        id=str(uuid.uuid4()),
        name=name,
        lang=lang,
        tags=tags,
        created_at=now,
        updated_at=now,
        text=text,
        glyphs=glyphs,
    )

    db.entries.append(note)
    save_db(db)
    return note


def find_note_by_name(db: GlyphNotesDB, name: str) -> Optional[GlyphNote]:
    for n in db.entries:
        if n.name == name:
            return n
    return None


def list_notes(db: GlyphNotesDB) -> List[GlyphNote]:
    return sorted(db.entries, key=lambda n: n.created_at)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cmd_encode(args: argparse.Namespace, enc: GlyphEncoder) -> None:
    text = args.text
    glyphs = enc.text_to_glyphs(text)
    print(glyphs)


def cmd_decode(args: argparse.Namespace, enc: GlyphEncoder) -> None:
    glyphs = args.glyphs
    try:
        text = enc.glyphs_to_text(glyphs)
    except Exception as e:
        print(f"✖ Decode error: {e}", file=sys.stderr)
        sys.exit(1)
    print(text)


def cmd_add(args: argparse.Namespace, enc: GlyphEncoder) -> None:
    tags = [t.strip() for t in args.tags.split(",")] if args.tags else []
    text = args.text
    if args.file:
        try:
            with open(args.file, "r", encoding="utf-8") as f:
                text = f.read()
        except Exception as e:
            print(f"✖ Failed to read file: {e}", file=sys.stderr)
            sys.exit(1)

    note = add_note(enc, args.name, text, lang=args.lang, tags=tags)
    print("✓ GlyphNote added")
    print(f"- id   : {note.id}")
    print(f"- name : {note.name}")
    print(f"- lang : {note.lang}")
    print(f"- tags : {', '.join(note.tags) if note.tags else '(none)'}")
    print(f"- glyphs_length : {len(note.glyphs)}")


def cmd_list(args: argparse.Namespace, enc: GlyphEncoder) -> None:
    db = load_db()
    notes = list_notes(db)
    if not notes:
        print("(no glyphnotes yet)")
        return
    for n in notes:
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(n.created_at))
        print(f"- {n.name} [{n.lang}] ({ts}) tags={','.join(n.tags)} id={n.id}")


def cmd_show(args: argparse.Namespace, enc: GlyphEncoder) -> None:
    db = load_db()
    note = find_note_by_name(db, args.name)
    if not note:
        print(f"✖ No note named '{args.name}'", file=sys.stderr)
        sys.exit(1)

    print(f"Name  : {note.name}")
    print(f"Lang  : {note.lang}")
    print(f"Tags  : {', '.join(note.tags) if note.tags else '(none)'}")
    print(f"ID    : {note.id}")
    print(f"Created : {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(note.created_at))}")
    print(f"Updated : {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(note.updated_at))}")
    print("")
    print("Plaintext:")
    print("----------")
    print(note.text)
    print("")
    print("Glyphs:")
    print("-------")
    print(note.glyphs)


def cmd_export(args: argparse.Namespace, enc: GlyphEncoder) -> None:
    db = load_db()
    out_path = Path(args.out).resolve()
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(db.to_dict(), f, indent=2, ensure_ascii=False)
    print(f"✓ Exported glyphnotes db → {out_path}")


def cmd_import(args: argparse.Namespace, enc: GlyphEncoder) -> None:
    in_path = Path(args.path).resolve()
    if not in_path.exists():
        print(f"✖ Import file not found: {in_path}", file=sys.stderr)
        sys.exit(1)
    try:
        with in_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        db = GlyphNotesDB.from_dict(data)
        save_db(db)
        print(f"✓ Imported glyphnotes db ← {in_path}")
    except Exception as e:
        print(f"✖ Failed to import db: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_alphabet_show(args: argparse.Namespace, enc: GlyphEncoder) -> None:
    print(f"Alphabet length: {len(enc.alphabet)}")
    print("".join(enc.alphabet))


def cmd_alphabet_set(args: argparse.Namespace, enc: GlyphEncoder) -> None:
    """
    Replace alphabet from a text file where each line is one glyph.
    """
    path = Path(args.path).resolve()
    if not path.exists():
        print(f"✖ Alphabet file not found: {path}", file=sys.stderr)
        sys.exit(1)
    glyphs: List[str] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            g = line.strip("\n\r")
            if not g:
                continue
            glyphs.append(g)
    if len(glyphs) < 16:
        print("✖ New alphabet must contain at least 16 glyphs.", file=sys.stderr)
        sys.exit(1)
    save_alphabet(glyphs)
    print(f"✓ Updated alphabet from {path}")
    print(f"- length: {len(glyphs)}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="GlyphNotes Component — encode/decode text and manage glyph notes."
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # encode
    p_enc = sub.add_parser("encode", help="encode UTF-8 text to glyphs")
    p_enc.add_argument("text", type=str)
    p_enc.set_defaults(func=cmd_encode)

    # decode
    p_dec = sub.add_parser("decode", help="decode glyphs to UTF-8 text")
    p_dec.add_argument("glyphs", type=str)
    p_dec.set_defaults(func=cmd_decode)

    # add
    p_add = sub.add_parser("add", help="add a glyphnote entry")
    p_add.add_argument("--name", required=True, type=str, help="note name")
    p_add.add_argument("--lang", default="und", type=str, help="language tag (e.g. en, ja, code)")
    p_add.add_argument("--tags", default="", type=str, help="comma-separated tags")
    src_group = p_add.add_mutually_exclusive_group(required=True)
    src_group.add_argument("--text", type=str, help="inline text")
    src_group.add_argument("--file", type=str, help="path to text file")
    p_add.set_defaults(func=cmd_add)

    # list
    p_list = sub.add_parser("list", help="list all glyphnotes")
    p_list.set_defaults(func=cmd_list)

    # show
    p_show = sub.add_parser("show", help="show one note (plaintext + glyphs)")
    p_show.add_argument("--name", required=True, type=str)
    p_show.set_defaults(func=cmd_show)

    # export
    p_export = sub.add_parser("export", help="export db to a JSON file")
    p_export.add_argument("--out", required=True, type=str)
    p_export.set_defaults(func=cmd_export)

    # import
    p_import = sub.add_parser("import", help="import db from a JSON file")
    p_import.add_argument("path", type=str)
    p_import.set_defaults(func=cmd_import)

    # alphabet show
    p_as = sub.add_parser("alphabet-show", help="show current alphabet")
    p_as.set_defaults(func=cmd_alphabet_show)

    # alphabet set
    p_aset = sub.add_parser("alphabet-set", help="replace alphabet from file (one glyph per line)")
    p_aset.add_argument("path", type=str)
    p_aset.set_defaults(func=cmd_alphabet_set)

    return p


def main(argv: Optional[List[str]] = None) -> None:
    alphabet = load_alphabet()
    encoder = GlyphEncoder(alphabet=alphabet)

    parser = build_parser()
    args = parser.parse_args(argv)

    func = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        sys.exit(1)

    func(args, encoder)


if __name__ == "__main__":
    main()
EOF

chmod +x glyphnotes_component.py
