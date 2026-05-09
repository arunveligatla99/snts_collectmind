"""Build a GGUF Q4_K_M artifact from the Qwen2.5-7B-Instruct revision SHA.

Wired in by Phase 3 US1 (T023) and the CPU-profile Dockerfile (T016). Foundation
smoke test does not require this script.
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, help="Path to a HF snapshot of the model.")
    parser.add_argument("--out", required=True, help="Output GGUF file path.")
    parser.add_argument("--llama-cpp-bin", default="convert_hf_to_gguf.py")
    args = parser.parse_args()

    source = Path(args.source)
    out = Path(args.out)
    if not source.exists():
        print(f"source not found: {source}", file=sys.stderr)
        return 1

    out.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "python",
        args.llama_cpp_bin,
        str(source),
        "--outfile",
        str(out),
        "--outtype",
        "q4_k_m",
    ]
    print("running:", " ".join(cmd))
    subprocess.run(cmd, check=True)

    sha = _sha256_file(out)
    print(f"{sha}  {out.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
