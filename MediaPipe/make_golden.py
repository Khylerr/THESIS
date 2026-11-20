#!/usr/bin/env python3
"""Builds shared/golden/: reference outputs from the real Python code, which the Kotlin
unit tests (android/core) must reproduce. This is how we know the phone app syncs,
rounds, normalizes and writes takes exactly like fslRecorder.py + aisl_norm.py.

Run with the MediaPipe venv (needs pandas + numpy; the phone has neither):
    venv\\Scripts\\python.exe make_golden.py
Then run the Kotlin tests:  cd ..\\android  ->  gradlew :core:test   (or Android Studio)

Re-run this whenever fslRecorder.py's sync/quality code or aisl_norm.py changes.
"""
import csv
import json
import math
import os
import random
import shutil
import struct
from types import SimpleNamespace

import numpy as np
import pandas as pd

import aisl_norm
import fslRecorder as rec

OUT = os.path.join(aisl_norm.SHARED_DIR, "golden")
DATA = os.path.join(aisl_norm.BASE_DIR, "data", "S01")
rng = random.Random(20261028)


def r(x):
    """Exact text for a float (Python repr round-trips)."""
    return repr(float(x))


def write_csv(name, header, rows):
    with open(os.path.join(OUT, name), "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        if header:
            w.writerow(header)
        w.writerows(rows)


def f32():
    """A landmark-like value: float32 from MediaPipe, widened to a Python float."""
    return float(np.float32(rng.uniform(-0.2, 1.1)))


# ----------------------------------------------------------------------------
def gen_rounding():
    xs = [0.0, -0.0, 1.0, 100.0, 0.5, 0.25, 0.35, 1.45, 2.5, 2.675, 0.1 + 0.2, 1e-4, 1e-5,
          0.00005, -0.00004, 1.5e-5, 1e16, 1e15, 123456789.123, -4.710815737496432e-09,
          0.8369881510734558, 8.25, -8.25, 0.0044, 30.00003000003, 2 ** 53, 2 ** -20, 1e22,
          5e-324, 1.7976931348623157e300, 0.95, 12.3456789, -1640.0, 0.04]
    for _ in range(400):
        e = rng.randint(-12, 12)
        xs.append(rng.uniform(-1, 1) * 10.0 ** e)
    for _ in range(200):
        xs.append(float(np.float32(rng.uniform(-2, 2))))
    for _ in range(100):   # glove_dt_ms-like values
        xs.append((rng.uniform(170000, 180000) - rng.uniform(170000, 180000)) * 1000 / 1e6)
    xs = [float(x) for x in xs]
    rows = []
    for x in xs:
        np1 = float(pd.Series([x]).round(1).iloc[0])
        rows.append([r(x), repr(x), r(round(x, 4)), r(round(x, 1)), r(np1)])
    write_csv("rounding.csv", ["x", "py_repr", "py_round4", "py_round1", "np_round1"], rows)


# ----------------------------------------------------------------------------
def asof_expected(left, right, direction, tol):
    ldf = pd.DataFrame({"k": np.asarray(left, dtype="float64")})
    rdf = pd.DataFrame({"k2": np.asarray(right, dtype="float64"), "ridx": np.arange(len(right))})
    m = pd.merge_asof(ldf, rdf, left_on="k", right_on="k2", direction=direction, tolerance=tol)
    return [-1 if pd.isna(v) else int(v) for v in m["ridx"]]


def gen_asof():
    cases = [
        ([0.5], [0.4, 0.6], 0.2),                 # equidistant tie -> backward wins
        ([1.0], [1.0], 0.04),                     # exact match
        ([1.0], [1.04], 0.04),                    # float edge: 1.04 - 1.0 > 0.04
        ([1.0], [0.96], 0.04),
        ([0.0, 0.1, 0.2], [], 0.04),              # no glove samples
        ([0.1, 0.2, 0.3], [0.2, 0.2, 0.2], 0.04),  # duplicate right keys
        ([-0.01, 0.0, 4.0, 4.02], [0.0, 0.02, 3.98, 4.0], 0.04),
    ]
    for _ in range(60):
        n_l, n_r = rng.randint(1, 40), rng.randint(0, 60)
        left = sorted(round(rng.uniform(-0.1, 4.1), rng.choice([2, 3, 4])) for _ in range(n_l))
        right = sorted(rng.uniform(-0.2, 4.2) for _ in range(n_r))
        if right and rng.random() < 0.3:   # some exact hits
            left = sorted(left + [rng.choice(right)])
        cases.append((left, right, rng.choice([0.01, 0.02, 0.04, 0.1])))
    rows = []
    for i, (left, right, tol) in enumerate(cases):
        for d in ("nearest", "backward", "forward"):
            exp = asof_expected(left, right, d, tol)
            rows.append([i, d, r(tol), " ".join(r(x) for x in left), " ".join(r(x) for x in right),
                         " ".join(str(e) for e in exp)])
    write_csv("asof.csv", ["case", "direction", "tolerance", "left", "right", "expected"], rows)


# ----------------------------------------------------------------------------
def fake_hand(score):
    lms = [SimpleNamespace(x=f32(), y=f32(), z=float(np.float32(rng.uniform(-0.15, 0.05))))
           for _ in range(rec.N_LM)]
    return ("Right", float(np.float32(score)), rec.TrackedHand(lms))


def gen_sync_and_quality():
    """A synthetic take through the recorder's build_row -> sync_streams -> quality."""
    args = SimpleNamespace(sync_direction="nearest", sync_tolerance_sec=0.04, log_other=True,
                           record_sec=4.0)
    t_rec0 = 173362.2229436
    header = rec.make_header(True)
    frame_in, rows, perf = [], [], []
    t = t_rec0 + 0.0044
    k = 0
    while t - t_rec0 < args.record_sec:
        g = fake_hand(rng.uniform(0.5, 1.0)) if rng.random() < 0.9 else None
        o = fake_hand(rng.uniform(0.5, 1.0)) if rng.random() < 0.3 else None
        t_rec = t - t_rec0
        rows.append(rec.build_row(k, t_rec, g, o, True))
        frame_in.append([k, r(t_rec),
                         1 if g else 0, r(g[1]) if g else "",
                         *([r(v) for p in g[2].landmark for v in (p.x, p.y, p.z)] if g else [""] * 63),
                         1 if o else 0, r(o[1]) if o else "",
                         *([r(v) for p in o[2].landmark for v in (p.x, p.y, p.z)] if o else [""] * 63)])
        perf.append((round(rng.uniform(8, 30), 3), rng.choice([0, 0, 0, 1]) if k else 0))
        k += 1
        t += rng.choice([1 / 30, 1 / 30, 1 / 30, 0.045, 0.12])   # incl. a few gaps
    t_end = t
    # glove: 50 Hz with jitter, one silent stretch, seq numbers with a drop and a wrap
    g_rows = []
    tg, seq = t_rec0 - 0.1, 65520
    while tg < t_end + 0.1:
        if not (1.50 < tg - t_rec0 < 1.62):
            vals = ([float(rng.randint(-2000, 300)) for _ in range(5)]
                    + [rng.randint(-1500, 1500) / 100.0 for _ in range(3)]
                    + [rng.randint(-5000, 5000) / 1000.0 for _ in range(3)])
            g_rows.append((tg + rng.uniform(-0.002, 0.002), vals, tg + rng.uniform(0.003, 0.02),
                           seq & 0xFFFF, 3))
        seq += 2 if rng.random() < 0.02 else 1
        tg += 0.02
    g_rows.sort(key=lambda x: x[2])   # buffer order = arrival order
    margin = args.sync_tolerance_sec
    win = [(a, v, ta, s, fl) for a, v, ta, s, fl in g_rows if t_rec0 - margin <= a <= t_end + margin]
    glove_df = pd.DataFrame([(a, *v, ta, s, fl) for a, v, ta, s, fl in win],
                            columns=["t"] + rec.GLOVE_COLS + ["t_arrival", "seq", "flags"])

    df = rec.sync_streams(rows, header, glove_df, t_rec0, args)
    q = rec.quality(df, glove_df, t_rec0, args, perf,
                    {"mode": "assume", "mediapipe_label_mismatch_frac": 0.0})

    write_csv("take_frames_input.csv",
              ["frame", "t_rec", "g_present", "g_score"] + [f"g{i}" for i in range(63)]
              + ["o_present", "o_score"] + [f"o{i}" for i in range(63)], frame_in)
    write_csv("take_glove_input.csv", ["t", *rec.GLOVE_COLS, "t_arrival", "seq", "flags"],
              [[r(a), *[r(x) for x in v], r(ta), s, fl] for a, v, ta, s, fl in g_rows])
    write_csv("take_perf_input.csv", ["proc_ms", "skipped"], [[r(p), s] for p, s in perf])
    with open(os.path.join(OUT, "take_meta.json"), "w") as f:
        json.dump({"t_rec0": r(t_rec0), "t_end": r(t_end), "record_sec": args.record_sec,
                   "sync_tolerance_sec": args.sync_tolerance_sec}, f, indent=1)
    df.to_csv(os.path.join(OUT, "take_expected.csv"), index=False)   # exactly as the recorder saves
    for log_other in (True, False):   # CSV column layout with and without the other hand
        write_csv(f"columns_log_other_{log_other}.csv", None, [rec.output_columns(log_other)])
    flat = []

    def walk(prefix, v):
        if isinstance(v, dict):
            for kk, vv in v.items():
                walk(f"{prefix}.{kk}" if prefix else kk, vv)
        elif isinstance(v, list):
            flat.append((prefix, "|".join(v)))
        elif v is None:
            flat.append((prefix, "null"))
        else:
            flat.append((prefix, r(v) if isinstance(v, float) else str(v)))
    walk("", q)
    write_csv("take_quality_expected.csv", ["key", "value"], flat)


# ----------------------------------------------------------------------------
def gen_clock():
    cm = rec.ClockMapper()
    rows = []
    t_dev, t_arr0 = 12.345, 5000.0
    for i in range(1500):
        t_dev += 0.02
        if i == 900:
            t_dev = 0.5          # glove reboot: device clock jumps back
        t_arr = t_arr0 + i * 0.02 + rng.choice([0.004, 0.006, 0.01, 0.03, 0.08])
        rows.append([r(t_dev), r(t_arr), r(cm.update(t_dev, t_arr))])
    write_csv("clock.csv", ["t_dev", "t_arr", "offset"], rows)


def gen_packets():
    rows = []
    specs = [(0, 0, [0] * 5, [0] * 3, [0] * 3, 0), (65535, 4294967295, [32767, -32768, 1, -1, 0],
              [32767, -32768, 981], [-32768, 32767, 5], 255)]
    for _ in range(50):
        specs.append((rng.randint(0, 65535), rng.randint(0, 2 ** 32 - 1),
                      [rng.randint(-32768, 32767) for _ in range(5)],
                      [rng.randint(-32768, 32767) for _ in range(3)],
                      [rng.randint(-32768, 32767) for _ in range(3)], rng.randint(0, 255)))
    for seq, t_ms, flex, acc, gyro, flags in specs:
        data = rec.BLE_PACKET.pack(seq, t_ms, *flex, *acc, *gyro, flags)
        s, t_dev, vals, fl = rec.decode_ble_packet(data)
        rows.append([data.hex(), s, r(t_dev), *[r(v) for v in vals], fl])
    write_csv("packets.csv", ["hex", "seq", "t_dev", *rec.GLOVE_COLS, "flags"], rows)


def gen_stats():
    rows = []
    for n in list(range(1, 12)) + [60, 120, 200]:
        xs = [round(rng.uniform(0, 40), rng.choice([1, 3, 6])) for _ in range(n)]
        a = np.asarray(xs)
        rows.append([" ".join(r(x) for x in xs), r(np.median(a)), r(np.percentile(a, 95)),
                     r(pd.Series(xs).quantile(0.95)), r(pd.Series(xs).median())])
    write_csv("stats.csv", ["values", "np_median", "np_p95", "pd_q95", "pd_median"], rows)


def gen_flex_calibration():
    """Two-point calibration cases: samples -> open/closed means, or the error message."""
    rows = []
    for case in range(40):
        n_o, n_c = rng.choice([10, 30, 50, 51]), rng.choice([20, 30, 50])
        o0 = [rng.uniform(-60, 60) for _ in range(5)]
        rng_ = [rng.choice([-1, 1]) * rng.uniform(40 if case % 4 == 0 else 150, 2000) for _ in range(5)]
        open_s = [[float(round(o0[i] + rng.gauss(0, 8))) for i in range(5)] + [0.0] * 6 for _ in range(n_o)]
        closed_s = [[float(round(o0[i] + rng_[i] + rng.gauss(0, 15))) for i in range(5)] + [0.0] * 6
                    for _ in range(n_c)]
        enc = lambda ss: "|".join(" ".join(r(v) for v in x[:5]) for x in ss)
        try:
            cal = aisl_norm.flex_calibration(open_s, closed_s)
            probe = [rng.uniform(-2500, 2500) for _ in range(5)]
            res = ["ok", " ".join(r(v) for v in cal["open"]), " ".join(r(v) for v in cal["closed"]),
                   " ".join(r(v) for v in probe), " ".join(r(v) for v in aisl_norm.normalize_flex(probe, cal))]
        except ValueError as e:
            res = ["error", str(e).replace(",", ";"), "", "", ""]   # no commas inside CSV cells
        rows.append([case, enc(open_s), enc(closed_s), *res])
    write_csv("flex_calibration.csv", ["case", "open_samples", "closed_samples", "result", "open", "closed",
                                       "probe", "probe_normalized"], rows)


def gen_picker():
    rows = []
    for mode in ("assume", "label"):
        for glove_hand in ("Right", "Left"):
            picker = rec.HandPicker(SimpleNamespace(hand_mode=mode, glove_hand=glove_hand))
            t, wx, wy = 0.0, 0.6, 0.5
            for k in range(300):
                t += rng.choice([1 / 30, 1 / 30, 0.2, 0.6])
                n = rng.choice([0, 1, 1, 2, 2, 2])
                found = []
                for j in range(n):
                    if j == 0 and rng.random() < 0.7:   # glove hand drifts
                        wx += rng.uniform(-0.05, 0.05)
                        wy += rng.uniform(-0.05, 0.05)
                        x, y = wx, wy
                    else:
                        x, y = f32(), f32()
                    lms = [SimpleNamespace(x=x, y=y, z=0.0)] + [SimpleNamespace(x=0.0, y=0.0, z=0.0)] * 20
                    found.append((rng.choice(["Left", "Right"]), float(np.float32(rng.random())),
                                  rec.TrackedHand(lms)))
                rng.shuffle(found)
                g, o = picker.pick(found, t)
                gi = next((i for i, h in enumerate(found) if h is g), -1)
                oi = next((i for i, h in enumerate(found) if h is o), -1)
                hands = ";".join(f"{lab}:{r(sc)}:{r(h.landmark[0].x)}:{r(h.landmark[0].y)}"
                                 for lab, sc, h in found)
                rows.append([mode, glove_hand, r(t), hands, gi, oi])
            st = picker.stats()
            rows.append([mode, glove_hand, "STATS", "", picker.n_glove, picker.n_label_mismatch])
            assert st["mode"] == mode
    write_csv("picker.csv", ["mode", "glove_hand", "t", "hands", "glove_idx", "other_idx"], rows)


# ----------------------------------------------------------------------------
def phone_like(header, rows, meta, keep_every=1, drop_window=None):
    """Re-express a webcam take as if a portrait 480x640 phone camera had filmed it.

    Same physical hand -> pixels scaled by 0.75 and shifted, then divided by the new image
    size. aisl_norm must give the same hand-shape features for both (only the position
    features differ, because the framing differs).
    """
    w0, h0 = aisl_norm.image_size(meta)
    w1, h1, sc, ox, oy = 480.0, 640.0, 0.75, 0.0, 140.0
    col = {n: i for i, n in enumerate(header)}
    out = []
    for k, row in enumerate(rows):
        if k % keep_every:
            continue
        if drop_window and drop_window[0] <= row[col["t_sec"]] <= drop_window[1]:
            continue
        row = list(row)
        for pre in ("", "o_"):
            if f"{pre}x0" not in col:
                continue
            for i in range(rec.N_LM):
                xi, yi, zi = col[f"{pre}x{i}"], col[f"{pre}y{i}"], col[f"{pre}z{i}"]
                row[xi] = (row[xi] * w0 * sc + ox) / w1
                row[yi] = (row[yi] * h0 * sc + oy) / h1
                row[zi] = (row[zi] * w0 * sc) / w1
        out.append(row)
    meta1 = dict(meta, platform="synthetic-phone",
                 mediapipe_input={"width": w1, "height": h1, "rotation_degrees": 270, "mirrored": True})
    return out, meta1


INT_COLS = {"frame", "detected", "other_detected"}


def write_take(stem, header, rows, meta):
    with open(os.path.join(OUT, "norm_inputs", stem + ".csv"), "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        for row in rows:
            w.writerow([("" if math.isnan(v) else (str(int(v)) if name in INT_COLS else r(v)))
                        for name, v in zip(header, row)])
    with open(os.path.join(OUT, "norm_inputs", stem + ".json"), "w") as f:
        json.dump(meta, f, indent=1)


SYNTH_FLEX_CAL = {"open": [12.5, -3.25, 40.0, 7.75, 0.5], "closed": [-1850.0, 640.0, -1210.5, 905.0, 777.25]}


def gen_norm():
    os.makedirs(os.path.join(OUT, "norm_inputs"), exist_ok=True)
    os.makedirs(os.path.join(OUT, "norm_expected"), exist_ok=True)
    stems = []
    for stem in ("S01_home_rep04", "S01_hello_rep01"):
        shutil.copy(os.path.join(DATA, stem + ".csv"), os.path.join(OUT, "norm_inputs", stem + ".csv"))
        with open(os.path.join(DATA, stem + ".json")) as f:
            m = json.load(f)
        if stem == "S01_home_rep04":   # synthetic two-point calibration -> exercises flex normalization
            m["flex_calibration"] = SYNTH_FLEX_CAL
        with open(os.path.join(OUT, "norm_inputs", stem + ".json"), "w") as f:
            json.dump(m, f, indent=1)
        stems.append(stem)

    # invariance check: webcam take vs the same take re-framed as a portrait phone image
    header, rows = aisl_norm.read_take_csv(os.path.join(DATA, "S01_home_rep04.csv"))
    with open(os.path.join(DATA, "S01_home_rep04.json")) as f:
        meta = json.load(f)
    meta["flex_calibration"] = SYNTH_FLEX_CAL
    w, h = aisl_norm.image_size(meta)
    p_rows, p_meta = phone_like(header, rows, meta)
    a = aisl_norm.normalize_take(header, rows, w, h)
    b = aisl_norm.normalize_take(header, p_rows, *aisl_norm.image_size(p_meta))
    shape_cols = [i for i, n in enumerate(aisl_norm.FEATURE_COLUMNS)
                  if n not in ("g_px", "g_py", "o_px", "o_py")]
    worst = max(abs(ra[i] - rb[i]) for ra, rb in zip(a, b) for i in shape_cols)
    print(f"invariance: webcam vs phone-framed take, max hand-shape feature difference = {worst:.3g}")
    assert worst < 1e-9, worst

    # phone-like take at ~15 fps with a 150 ms hole: exercises interpolation + gap rules
    p2_rows, p2_meta = phone_like(header, rows, meta, keep_every=2, drop_window=(2.0, 2.15))
    write_take("phone_like_15fps", header, p2_rows, p2_meta)
    stems.append("phone_like_15fps")

    for stem in stems:
        out = aisl_norm.normalize_take_files(os.path.join(OUT, "norm_inputs", stem + ".csv"))
        aisl_norm.write_feature_csv(os.path.join(OUT, "norm_expected", stem + "_norm.csv"), out)
        valid = sum(row[1] for row in out)
        print(f"  {stem}: {len(out)} steps, glove hand valid in {valid:.0f}")


def main():
    os.makedirs(OUT, exist_ok=True)
    gen_rounding()
    gen_asof()
    gen_sync_and_quality()
    gen_clock()
    gen_packets()
    gen_stats()
    gen_picker()
    gen_flex_calibration()
    gen_norm()
    print(f"golden files written to {OUT}")


if __name__ == "__main__":
    main()
