cat > ~/SigilAGI-Local/rehydration_sigil.py <<'EOF'
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rehydration Sigil Component for SigilAGI-Local

This module creates and restores a compact "rehydration sigil" that
captures the core AGI state (ledger, models, memory) into a single,
checksummed artifact that can be reapplied later.

Usage (from ~/SigilAGI-Local):

  # 1) Capture current state into a sigil file
  python3 rehydration_sigil.py capture --out sigilagi_rehydrate.json

  # 2) Inspect a sigil file
  python3 rehydration_sigil.py inspect sigilagi_rehydrate.json

  # 3) Apply (rehydrate) a sigil back into the runtime files
  python3 rehydration_sigil.py apply sigilagi_rehydrate.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, asdict
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, Optional

# Root of SigilAGI-Local installation (this file should live there)
ROOT = Path(__file__).resolve().parent

# Known state files that define the "mind" + "world" of the system
STATE_FILES: Dict[str, str] = {
    "agi_ledger": "agi_ledger.json",
    "skill_registry": "skill_registry.json",
    "self_model": "self_model.json",
    "world_model": "world_model.json",
    "forecast_model": "forecast_model.json",
    "alignment_monitor": "alignment_monitor.json",
    "agent_memory": "agent_memory.json",
    "agent_chat_log": "agent_chat_log.json",
    "reasoning_runtime_log": "reasoning_runtime_log.json",
    "introspection_log": "introspection_log.json",
    "agent_consensus_log": "agent_consensus_log.json",
    "agent_output_log": "agent_output_log.json",
}


SIGIL_MAGIC = "⊏⚗$ Σ_rehydrate::SigilAGI_Cluster_v1 ⊐"
SIGIL_VERSION = "1.0.0"


@dataclass
class RehydrationSigil:
    """
    High-level representation of a rehydration sigil.

    - magic: glyphmatic header identifying this as a rehydration sigil
    - version: schema version
    - created_at: unix timestamp (float)
    - source_root: absolute path of the system when the sigil was created
    - state: mapping from logical state keys to their JSON payloads
    - checksum: SHA-256 checksum over the normalized state block
    """
    magic: str
    version: str
    created_at: float
    source_root: str
    state: Dict[str, Any]
    checksum: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RehydrationSigil":
        return cls(
            magic=data["magic"],
            version=data["version"],
            created_at=data["created_at"],
            source_root=data.get("source_root", ""),
            state=data["state"],
            checksum=data["checksum"],
        )


def _safe_read_json(path: Path) -> Optional[Any]:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠ Failed to read JSON from {path}: {e}", file=sys.stderr)
        return None


def _safe_write_json(path: Path, payload: Any) -> None:
    try:
        with path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"⚠ Failed to write JSON to {path}: {e}", file=sys.stderr)


def capture_state() -> Dict[str, Any]:
    """
    Capture all known state files that are present under ROOT.

    Returns a dict mapping logical keys to their JSON content.
    Files that do not exist are simply skipped.
    """
    state: Dict[str, Any] = {}
    for key, rel in STATE_FILES.items():
        path = ROOT / rel
        payload = _safe_read_json(path)
        if payload is not None:
            state[key] = payload
    return state


def compute_checksum(state: Dict[str, Any]) -> str:
    """
    Compute a deterministic SHA-256 checksum over the state block.
    """
    normalized = json.dumps(state, sort_keys=True, separators=(",", ":"))
    return sha256(normalized.encode("utf-8")).hexdigest()


def create_sigil() -> RehydrationSigil:
    """
    Capture current runtime state and wrap it in a RehydrationSigil.
    """
    state = capture_state()
    checksum = compute_checksum(state)
    sigil = RehydrationSigil(
        magic=SIGIL_MAGIC,
        version=SIGIL_VERSION,
        created_at=time.time(),
        source_root=str(ROOT),
        state=state,
        checksum=checksum,
    )
    return sigil


def save_sigil(sigil: RehydrationSigil, out_path: Path) -> None:
    """
    Serialize a RehydrationSigil to disk.
    """
    _safe_write_json(out_path, sigil.to_dict())


def load_sigil(path: Path) -> RehydrationSigil:
    """
    Load and validate a RehydrationSigil from disk.
    Raises ValueError if validation fails.
    """
    raw = _safe_read_json(path)
    if raw is None:
        raise ValueError(f"Unable to read sigil file: {path}")
    if raw.get("magic") != SIGIL_MAGIC:
        raise ValueError("Not a valid rehydration sigil (magic mismatch).")
    sigil = RehydrationSigil.from_dict(raw)
    expected = compute_checksum(sigil.state)
    if expected != sigil.checksum:
        raise ValueError(
            f"Checksum mismatch: expected {expected}, found {sigil.checksum}"
        )
    return sigil


def apply_state(sigil: RehydrationSigil, target_root: Optional[Path] = None) -> None:
    """
    Apply the sigil's state back into the local runtime files.

    target_root defaults to ROOT (current SigilAGI-Local directory).
    """
    root = target_root or ROOT
    applied = 0
    for key, payload in sigil.state.items():
        rel = STATE_FILES.get(key)
        if not rel:
            print(f"⚠ Unknown state key in sigil (skipping): {key}")
            continue
        path = root / rel
        _safe_write_json(path, payload)
        applied += 1
    print(f"✓ Rehydration applied for {applied} state segments under {root}")


def summarize_sigil(sigil: RehydrationSigil) -> str:
    """
    Build a human-readable summary of a sigil for quick inspection.
    """
    lines = []
    lines.append("=== Rehydration Sigil Summary ===")
    lines.append(f"Magic       : {sigil.magic}")
    lines.append(f"Version     : {sigil.version}")
    lines.append(f"Created at  : {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(sigil.created_at))}")
    lines.append(f"Source root : {sigil.source_root}")
    lines.append(f"Checksum    : {sigil.checksum}")
    lines.append("")
    lines.append("State blocks:")
    for key in sorted(sigil.state.keys()):
        payload = sigil.state[key]
        if isinstance(payload, dict):
            size = len(json.dumps(payload, ensure_ascii=False))
        else:
            size = len(str(payload))
        lines.append(f"  - {key}  (bytes≈{size})")
    lines.append("=================================")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        description="Rehydration Sigil Component for SigilAGI-Local"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # capture
    p_capture = sub.add_parser("capture", help="Capture current state into a sigil file")
    p_capture.add_argument(
        "--out",
        type=str,
        default="sigilagi_rehydrate.json",
        help="Output sigil file (default: sigilagi_rehydrate.json)",
    )

    # inspect
    p_inspect = sub.add_parser("inspect", help="Inspect a sigil file")
    p_inspect.add_argument("path", type=str, help="Path to sigil JSON file")

    # apply
    p_apply = sub.add_parser("apply", help="Apply (rehydrate) a sigil into runtime files")
    p_apply.add_argument("path", type=str, help="Path to sigil JSON file")
    p_apply.add_argument(
        "--root",
        type=str,
        default=None,
        help="Target SigilAGI root (default: this script's directory)",
    )

    args = parser.parse_args(argv)

    if args.cmd == "capture":
        sigil = create_sigil()
        out_path = (Path.cwd() / args.out).resolve()
        save_sigil(sigil, out_path)
        print("⊏⚗$ Rehydration sigil captured ⊐")
        print(f"- Output   : {out_path}")
        print(f"- Checksum : {sigil.checksum}")
        print(f"- Blocks   : {len(sigil.state)}")

    elif args.cmd == "inspect":
        path = Path(args.path).resolve()
        try:
            sigil = load_sigil(path)
        except Exception as e:
            print(f"✖ Failed to load sigil: {e}", file=sys.stderr)
            sys.exit(1)
        print(summarize_sigil(sigil))

    elif args.cmd == "apply":
        path = Path(args.path).resolve()
        try:
            sigil = load_sigil(path)
        except Exception as e:
            print(f"✖ Failed to load sigil: {e}", file=sys.stderr)
            sys.exit(1)
        target_root = Path(args.root).resolve() if args.root else ROOT
        apply_state(sigil, target_root=target_root)
        print("⊏⚗$ Rehydration complete ⊐")


if __name__ == "__main__":
    main()
EOF
