# -*- coding: utf-8 -*-
import os, sys
BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

gt_path = os.path.join(BASE, "group_trusted.py")
cp_path = os.path.join(BASE, "crypto_primitives.py")
assert os.path.isfile(gt_path), f"group_trusted.py が見つかりません: {gt_path}"
assert os.path.isfile(cp_path), f"crypto_primitives.py が見つかりません: {cp_path}"

from group_trusted import Node, TrustedRepeaterSetup  # noqa: E402

OUT = "group_key_ac.bin"

def main():
    alice, bob, charlie = Node("Alice"), Node("Bob"), Node("Charlie")
    auth_key = os.urandom(32)

    setup = TrustedRepeaterSetup(alice, bob, charlie, auth_key=auth_key)
    k_ab, k_bc, k_ac_final = setup.run_once()

    with open(os.path.join(BASE, OUT), "wb") as f:
        f.write(k_ac_final)

    print("=== Stage78 Trusted Repeater Demo ===")
    print(f"K_AB (A-B)  : {k_ab.hex()[:16]}... len={len(k_ab)}")
    print(f"K_BC (B-C)  : {k_bc.hex()[:16]}... len={len(k_bc)}")
    print(f"K_AC (final): {k_ac_final.hex()[:16]}... len={len(k_ac_final)}")
    print(f"Saved A–C shared key -> {OUT}")

if __name__ == "__main__":
    main()
