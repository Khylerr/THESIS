"""AISL-A shared MediaPipe config + cross-device feature normalization (spec v3).

Needs only the standard library (no pandas, no numpy), so the exact same steps can be
written line for line in Kotlin: android/core/src/main/kotlin/com/aisla/core/Normalizer.kt.
Both are checked against the same golden files (shared/golden/, made by make_golden.py).
If you change anything here, change Normalizer.kt too and re-run make_golden.py.

Why: a webcam frame (640x480 landscape, OpenCV) and a phone frame (CameraX, e.g. 480x640
portrait, other lens, other frame rate) give MediaPipe landmarks that are NOT directly
comparable: x is divided by the image width, y by the height, z is on the x scale, and
the hand's size depends on the distance to the camera. The normalized version removes
all of that:

Per hand (21 landmarks, raw MediaPipe x,y,z in [0,1] of the image that MediaPipe saw):
  1. pixels:     X = x*W,  Y = y*H,  Z = z*W        (square pixels; z uses the x scale)
  2. palm size:  s = mean 3D distance wrist(0) -> MCP 5, 9, 13, 17
  3. shape:      ((X,Y,Z)_i - (X,Y,Z)_0) / s   for i = 0..20     -> 63 values
  4. position:   (X_0 - W/2) / min(W,H),  (Y_0 - H/2) / min(W,H)  -> 2 values
  -> 65 values, plus a valid flag (0 = hand missing/degenerate -> all zeros)
Only the gloved (signing) hand: signs are one-handed (spec v2 dropped the other hand).
Glove (spec v3): flex1..5 normalized with the session's two-point calibration,
  flex_n = (v - open) / (closed - open)   -> ~0 = hand fully open, ~1 = tight fist (not clipped);
  the 6 IMU values as recorded; plus a valid flag. A take without a two-point calibration
  (older takes) gets glove_valid = 0 (all glove values zero): raw flex counts are glove- and
  person-specific and must never be mixed with normalized ones.
Time: each stream is resampled onto a fixed 30 Hz grid over the 4 s take (120 steps):
  linear interpolation between the two valid frames around a grid time if they are at
  most MAX_GAP_SEC apart, else the nearest valid frame within MAX_GAP_SEC / 2, else invalid.

Not normalized (cannot be, from landmarks alone): where the signer stands in the frame
(position values depend on framing), lighting/blur, and the MediaPipe model itself
(that is why both platforms load the same hand_landmarker.task, see load_model()).
"""
import csv
import hashlib
import json
import math
import os

try:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
except NameError:
    BASE_DIR = os.getcwd()

SPEC_VERSION = 3   # v2: other hand removed (79 columns); v3: two-point flex calibration
SHARED_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "shared"))
MP_CONFIG_PATH = os.path.join(SHARED_DIR, "mediapipe_config.json")

N_LM = 21
GLOVE_COLS = ["flex1", "flex2", "flex3", "flex4", "flex5",
              "acc_x", "acc_y", "acc_z", "gyro_x", "gyro_y", "gyro_z"]
PALM_MCPS = (5, 9, 13, 17)
MIN_PALM_PX = 1e-6           # palm size (pixels) below this = degenerate hand -> invalid

# Two-point flex calibration (open hand, then fist), same on desktop and phone
CAL_HOLD_SEC = 3.0           # hold each pose this long ...
CAL_AVG_SEC = 1.0            # ... and average its last second of glove samples
MIN_CAL_SAMPLES = 25         # >= 0.5 s at 50 Hz
MIN_FLEX_RANGE = 100.0       # |closed - open| below this (ADC counts) = finger not calibrated

RESAMPLE_HZ = 30.0
RESAMPLE_SEC = 4.0
MAX_GAP_SEC = 0.10           # same as the recorder's MAX_GAP_SEC quality gate


def hand_feature_names(prefix):
    return [f"{prefix}{a}{i}" for i in range(N_LM) for a in "xyz"] + [prefix + "px", prefix + "py"]


HAND_FEATS = len(hand_feature_names(""))       # 65
FEATURE_COLUMNS = (["t", "g_valid"] + hand_feature_names("g_")
                   + ["glove_valid"] + GLOVE_COLS)


# ----------------------------------------------------------------------------
# Shared MediaPipe config (shared/mediapipe_config.json, also bundled in the app)
# ----------------------------------------------------------------------------
def load_mp_config(path=MP_CONFIG_PATH):
    with open(path) as f:
        return json.load(f)


def load_model(cfg, model_dir=BASE_DIR):
    """Read hand_landmarker.task and check it is byte-for-byte the model the app uses."""
    path = os.path.join(model_dir, cfg["model_file"])
    with open(path, "rb") as f:
        data = f.read()
    digest = hashlib.sha256(data).hexdigest()
    if digest != cfg["model_sha256"]:
        raise RuntimeError(f"{path} has sha256 {digest}, but shared/mediapipe_config.json expects "
                           f"{cfg['model_sha256']}. Python and the Android app must use the same model file.")
    return data, digest


def handedness_label(category_name, cfg):
    """Tasks API label -> the signer's real hand on the mirrored image (legacy convention).

    On the same mirrored image, the Tasks HandLandmarker labels a hand the opposite way to
    the old mp.solutions.hands (checked: 20 of 24 matched hands). The recorder's S01 takes
    showed the legacy label is the signer's real hand, so the Tasks label is swapped.
    """
    if not cfg.get("invert_handedness_label", False):
        return category_name
    return {"Left": "Right", "Right": "Left"}.get(category_name, category_name)


# ----------------------------------------------------------------------------
# Per-frame normalization
# ----------------------------------------------------------------------------
def normalize_hand(xyz, width, height):
    """63 raw MediaPipe values (x0,y0,z0,...,z20) -> 65 features, or None if missing."""
    if len(xyz) != 3 * N_LM or not all(math.isfinite(v) for v in xyz):
        return None
    w = float(width)
    h = float(height)
    px = [xyz[3 * i] * w for i in range(N_LM)]
    py = [xyz[3 * i + 1] * h for i in range(N_LM)]
    pz = [xyz[3 * i + 2] * w for i in range(N_LM)]

    def dist0(j):
        dx = px[j] - px[0]
        dy = py[j] - py[0]
        dz = pz[j] - pz[0]
        return math.sqrt(dx * dx + dy * dy + dz * dz)

    s = (dist0(PALM_MCPS[0]) + dist0(PALM_MCPS[1]) + dist0(PALM_MCPS[2]) + dist0(PALM_MCPS[3])) / 4.0
    if not s > MIN_PALM_PX:
        return None
    feats = []
    for i in range(N_LM):
        feats.append((px[i] - px[0]) / s)
        feats.append((py[i] - py[0]) / s)
        feats.append((pz[i] - pz[0]) / s)
    m = min(w, h)
    feats.append((px[0] - w / 2.0) / m)
    feats.append((py[0] - h / 2.0) / m)
    return feats


def flex_calibration(open_samples, closed_samples):
    """Two-point calibration from glove samples (each: >= 5 values, flex1..5 first).

    open_samples: hand open, flat, still; closed_samples: tight fist. Returns
    {"open": [5 means], "closed": [5 means]}; raises ValueError saying what went wrong.
    """
    if len(open_samples) < MIN_CAL_SAMPLES or len(closed_samples) < MIN_CAL_SAMPLES:
        raise ValueError(f"too few glove samples ({len(open_samples)} open, "
                         f"{len(closed_samples)} fist; need {MIN_CAL_SAMPLES}): is the glove streaming?")

    def means(samples):
        out = []
        for i in range(5):
            total = 0.0
            for s in samples:
                total += s[i]
            out.append(total / len(samples))
        return out

    o, c = means(open_samples), means(closed_samples)
    bad = [f"F{i + 1}" for i in range(5) if not abs(c[i] - o[i]) >= MIN_FLEX_RANGE]
    if bad:
        raise ValueError(f"{', '.join(bad)} barely changed between open hand and fist "
                         f"(< {MIN_FLEX_RANGE:.0f} counts): check the sensor, then redo with a tight fist")
    return {"open": o, "closed": c}


def normalize_flex(vals, cal):
    """flex1..5 -> (v - open) / (closed - open): ~0 open, ~1 fist."""
    return [(vals[i] - cal["open"][i]) / (cal["closed"][i] - cal["open"][i]) for i in range(5)]


def glove_values(vals, flex_cal):
    """11 glove values with flex normalized, or None (no sample in this frame / no calibration)."""
    if flex_cal is None or len(vals) != len(GLOVE_COLS) or not all(math.isfinite(v) for v in vals):
        return None
    return normalize_flex(vals, flex_cal) + list(vals[5:])


# ----------------------------------------------------------------------------
# Time normalization
# ----------------------------------------------------------------------------
def resample(times, feats, n_feats, hz=RESAMPLE_HZ, duration=RESAMPLE_SEC, max_gap=MAX_GAP_SEC):
    """Irregular frames -> fixed grid t_k = k / hz, k = 0 .. round(duration * hz) - 1.

    times: frame times (s, non-decreasing). feats: per frame a list of n_feats values or None.
    Returns a list of (valid, values) per grid step; invalid steps are all zeros.
    """
    for t0, t1 in zip(times, times[1:]):
        if t1 < t0:
            raise ValueError("frame times must be non-decreasing")
    n_out = int(round(duration * hz))
    good = [i for i, f in enumerate(feats) if f is not None]
    half = max_gap / 2.0
    out = []
    for k in range(n_out):
        g = k / hz
        a = None   # last valid frame with t <= g
        b = None   # first valid frame with t > g
        for i in good:
            if times[i] <= g:
                a = i
            else:
                b = i
                break
        if a is not None and times[a] == g:
            out.append((1, list(feats[a])))
        elif a is not None and b is not None and times[b] - times[a] <= max_gap:
            w = (g - times[a]) / (times[b] - times[a])
            fa, fb = feats[a], feats[b]
            out.append((1, [fa[j] + w * (fb[j] - fa[j]) for j in range(n_feats)]))
        else:
            da = g - times[a] if a is not None else math.inf
            db = times[b] - g if b is not None else math.inf
            if da <= db and da <= half:
                out.append((1, list(feats[a])))
            elif db < da and db <= half:
                out.append((1, list(feats[b])))
            else:
                out.append((0, [0.0] * n_feats))
    return out


# ----------------------------------------------------------------------------
# Whole take
# ----------------------------------------------------------------------------
def read_take_csv(path):
    """Take CSV -> (header, rows of floats). Empty cells (pandas NaN) -> nan."""
    with open(path, newline="") as f:
        r = csv.reader(f)
        header = next(r)
        rows = [[float(v) if v != "" else math.nan for v in row] for row in r]
    return header, rows


def image_size(meta):
    """(width, height) of the image MediaPipe saw, from the take's JSON sidecar."""
    src = meta.get("mediapipe_input") or meta["camera_reported"]
    return float(src["width"]), float(src["height"])


def normalize_take(header, rows, width, height, flex_cal=None):
    """Take rows (recorder CSV layout) -> FEATURE_COLUMNS rows on the fixed time grid.

    flex_cal: the take's two-point calibration ({"open": [5], "closed": [5]}); None -> glove invalid.
    """
    col = {name: i for i, name in enumerate(header)}
    g_idx = [col[f"{a}{i}"] for i in range(N_LM) for a in "xyz"]
    gl_idx = [col[c] for c in GLOVE_COLS] if all(c in col for c in GLOVE_COLS) else None

    times, g_feats, gl_feats = [], [], []
    for row in rows:
        times.append(row[col["t_sec"]])
        g_feats.append(normalize_hand([row[i] for i in g_idx], width, height)
                       if row[col["detected"]] == 1 else None)
        gl_feats.append(glove_values([row[i] for i in gl_idx], flex_cal) if gl_idx is not None else None)

    g = resample(times, g_feats, HAND_FEATS)
    gl = resample(times, gl_feats, len(GLOVE_COLS))
    out = []
    for k in range(len(g)):
        out.append([k / RESAMPLE_HZ, float(g[k][0]), *g[k][1], float(gl[k][0]), *gl[k][1]])
    return out


def normalize_take_files(csv_path, json_path=None):
    if json_path is None:
        json_path = os.path.splitext(csv_path)[0] + ".json"
    with open(json_path) as f:
        meta = json.load(f)
    header, rows = read_take_csv(csv_path)
    w, h = image_size(meta)
    return normalize_take(header, rows, w, h, meta.get("flex_calibration"))


def write_feature_csv(path, rows):
    with open(path, "w", newline="") as f:
        wr = csv.writer(f, lineterminator="\n")
        wr.writerow(FEATURE_COLUMNS)
        wr.writerows(rows)
