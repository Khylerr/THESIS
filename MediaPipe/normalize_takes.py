#!/usr/bin/env python3
"""Normalize every recorded take (desktop or phone) into the shared feature format.

    data/<signer>/<take>.csv + .json   ->   data_norm/<signer>/<take>_norm.csv

Same code path as the Android app (aisl_norm.py = Normalizer.kt, golden-tested), so a
webcam take and a phone take of the same sign end up directly comparable: fixed 30 Hz x 4 s
grid, hand shape centered on the wrist and scaled by palm size, position relative to the
image center. Copy the phone's Android/data/com.aisla.app/files/data/<signer> folder into
data/ to normalize phone takes here too (the phone also writes its own data_norm copy).

No pandas needed. Run in VS Code (Run Python File) or:  python normalize_takes.py
"""
import glob
import json
import os

import aisl_norm

DATA = os.path.join(aisl_norm.BASE_DIR, "data")
OUT = os.path.join(aisl_norm.BASE_DIR, "data_norm")


def main():
    n = 0
    for csv_path in sorted(glob.glob(os.path.join(DATA, "*", "*.csv"))):
        json_path = os.path.splitext(csv_path)[0] + ".json"
        if not os.path.exists(json_path):
            print(f"skip (no JSON sidecar): {csv_path}")
            continue
        signer = os.path.basename(os.path.dirname(csv_path))
        stem = os.path.splitext(os.path.basename(csv_path))[0]
        rows = aisl_norm.normalize_take_files(csv_path, json_path)
        os.makedirs(os.path.join(OUT, signer), exist_ok=True)
        aisl_norm.write_feature_csv(os.path.join(OUT, signer, stem + "_norm.csv"), rows)
        valid = sum(r[1] for r in rows) / len(rows)
        glove = sum(r[aisl_norm.FEATURE_COLUMNS.index("glove_valid")] for r in rows) / len(rows)
        with open(json_path) as f:
            calibrated = "flex_calibration" in json.load(f)
        print(f"{signer}/{stem}: {len(rows)} steps, glove hand present in {valid:.0%}, glove data in "
              f"{glove:.0%}" + ("" if calibrated else "  (no open/fist calibration -> glove columns invalid)"))
        n += 1
    print(f"{n} takes normalized -> {OUT}")


if __name__ == "__main__":
    main()
