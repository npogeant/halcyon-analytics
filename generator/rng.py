from __future__ import annotations

import hashlib

import numpy as np


def sub_seed(seed: int, name: str) -> int:
    """Derive a stable per-entity seed so each generator module draws an
    independent random stream, regardless of what other modules generated
    before it or in what order they ran."""
    digest = hashlib.sha256(f"{seed}:{name}".encode()).digest()
    return int.from_bytes(digest[:8], "little")


def rng_for(seed: int, name: str) -> np.random.Generator:
    return np.random.default_rng(sub_seed(seed, name))
