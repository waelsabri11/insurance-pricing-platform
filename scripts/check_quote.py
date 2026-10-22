"""Reads a /quote response on stdin and asserts the invariants the smoke test cares about."""

import json
import sys

q = json.load(sys.stdin)
o = q["offer"]
assert o["simulated"] is True and 0.8 <= o["multiplier"] <= 1.3 and 0 < o["expected_conversion"] < 1
assert q["annual_pure_premium"] > 0 and len(q["breakdown"]) == 8
print(
    f"quote ok: pure {q['annual_pure_premium']:.2f} EUR, offer {o['annual_price']:.2f} EUR, "
    f"x{o['multiplier']}, simulated conversion {o['expected_conversion']:.3f}"
)
