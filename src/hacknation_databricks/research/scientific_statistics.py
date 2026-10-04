"""Domain-independent deterministic seeds and binomial uncertainty."""

import hashlib
from math import sqrt


def seed_for(master: int, branch: str, batch: int, scenario: str = "") -> int:
    identity = f"{master}/{branch}/{batch}/{scenario}".encode()
    return int.from_bytes(hashlib.sha256(identity).digest()[:4], "big")


def wilson(successes: int, n: int, z: float = 1.96) -> list[float]:
    if n <= 0:
        raise ValueError("Need observations for a confidence interval")
    p = successes / n
    denominator = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denominator
    radius = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return [max(0.0, center - radius), min(1.0, center + radius)]
