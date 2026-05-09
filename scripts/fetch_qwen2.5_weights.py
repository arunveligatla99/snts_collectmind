"""Download Qwen2.5-7B-Instruct weights at a pinned revision SHA (per ADR-0002).

Usage:
    python scripts/fetch_qwen2.5_weights.py --revision <sha> --cache <hf_home>

Phase 2 foundation does not actually download weights (~14 GB); this script is wired in
by Phase 3 US1 (T022) and is exercised by the GPU-profile Dockerfile (T017). The Phase
2 foundation smoke test does not bring up the SLM container.
"""

from __future__ import annotations

import argparse
from pathlib import Path


_REPO = "Qwen/Qwen2.5-7B-Instruct"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision", required=True, help="HuggingFace revision SHA (40 hex chars).")
    parser.add_argument("--cache", required=True, help="HuggingFace cache root.")
    args = parser.parse_args()

    if len(args.revision) != 40:
        raise SystemExit(f"revision must be a 40-char SHA, got {args.revision!r}")

    Path(args.cache).mkdir(parents=True, exist_ok=True)

    try:
        from huggingface_hub import snapshot_download  # imported lazily; not a hard dep
    except ImportError as exc:
        raise SystemExit(
            "huggingface_hub is required for actual weight downloads; install it before "
            "running this script in a build context."
        ) from exc

    snapshot_download(
        repo_id=_REPO,
        revision=args.revision,
        cache_dir=args.cache,
        allow_patterns=[
            "*.safetensors",
            "tokenizer*",
            "*.json",
            "config.json",
            "generation_config.json",
        ],
    )
    print(f"downloaded {_REPO}@{args.revision} to {args.cache}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
