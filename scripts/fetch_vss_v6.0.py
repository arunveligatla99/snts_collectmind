"""Fetch COVESA VSS v6.0 release assets, derive a flat lookup, write SHA-256 manifest.

Downloads (per ADR-0001, COVESA VSS v6.0 commit 20c609bf95c73b51d483fb8f81a099d1d5b73066):
    - vss.json (canonical signal tree)
    - vss.csv (flat-row reference)
    - quantities.yaml, units.yaml (unit definitions)

Writes:
    - config/vss/v6.0/signals.yaml (flat name -> metadata lookup used by the validator)
    - config/vss/v6.0/manifest.sha256 (SHA-256 of every downloaded asset)
    - config/vss/v6.0/source.json (provenance metadata)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path
from typing import Any

import yaml


VSS_TAG = "v6.0"
VSS_COMMIT_SHA = "20c609bf95c73b51d483fb8f81a099d1d5b73066"
VSS_RELEASE_BASE = (
    "https://github.com/COVESA/vehicle_signal_specification/releases/download/v6.0"
)
ASSETS = (
    "vss.json",
    "vss.csv",
    "quantities.yaml",
    "units.yaml",
)
LEAF_KINDS = {"sensor", "actuator", "attribute"}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _download(name: str) -> bytes:
    url = f"{VSS_RELEASE_BASE}/{name}"
    print(f"downloading {url}")
    with urllib.request.urlopen(url, timeout=60) as resp:
        return resp.read()


def _walk_signals(node: dict[str, Any], path: str, out: dict[str, dict[str, Any]]) -> None:
    """Walk the VSS expanded tree and record leaf signals into `out`."""
    kind = node.get("type")
    children = node.get("children")
    if kind in LEAF_KINDS:
        out[path] = {
            "type": kind,
            "datatype": node.get("datatype"),
            "unit": node.get("unit"),
            "description": node.get("description"),
        }
    if isinstance(children, dict):
        for child_name, child_node in children.items():
            child_path = f"{path}.{child_name}" if path else child_name
            _walk_signals(child_node, child_path, out)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="config/vss/v6.0", help="Output directory.")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest_lines: list[str] = [
        f"# COVESA VSS {VSS_TAG} commit {VSS_COMMIT_SHA}",
        f"# Source: {VSS_RELEASE_BASE}",
        "# Format: <sha256>  <asset>",
    ]
    asset_blobs: dict[str, bytes] = {}
    for asset in ASSETS:
        data = _download(asset)
        asset_blobs[asset] = data
        manifest_lines.append(f"{_sha256_bytes(data)}  {asset}")

    # vss.json is a top-level dict whose root is the synthesized "Vehicle" branch.
    tree = json.loads(asset_blobs["vss.json"])
    if "Vehicle" not in tree:
        print(f"unexpected vss.json shape: top-level keys = {list(tree.keys())}", file=sys.stderr)
        return 2
    signals: dict[str, dict[str, Any]] = {}
    _walk_signals(tree["Vehicle"], "Vehicle", signals)

    signals_doc: dict[str, Any] = {
        "version": VSS_TAG,
        "commit": VSS_COMMIT_SHA,
        "leaf_count": len(signals),
        "signals": signals,
    }
    (out_dir / "signals.yaml").write_text(
        yaml.safe_dump(signals_doc, sort_keys=True, default_flow_style=False),
        encoding="utf-8",
    )

    (out_dir / "manifest.sha256").write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")

    (out_dir / "source.json").write_text(
        json.dumps(
            {
                "tag": VSS_TAG,
                "commit": VSS_COMMIT_SHA,
                "release_url": VSS_RELEASE_BASE,
                "leaf_count": len(signals),
                "assets": list(ASSETS),
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    for asset, data in asset_blobs.items():
        (out_dir / asset).write_bytes(data)

    print(
        f"wrote {len(signals)} VSS leaf signals to {out_dir / 'signals.yaml'} "
        f"({len(asset_blobs)} assets recorded in manifest.sha256)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
