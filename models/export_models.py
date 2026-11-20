"""PyTorch checkpoints (models/checkpoints/*.pth) -> shared/models/*.aislm for the Android app.

No torch needed (pth_reader.py reads the checkpoint safely); numpy only:
    python models/export_models.py

.aislm layout (little-endian), read by android/core SignModel.parse and by read_aislm() below:
    7 bytes   magic  b"AISLM1\\n"
    int32     N = header length in bytes
    N bytes   UTF-8 header, one "key=value" per line
    float32   every tensor listed in the header's "tensors=" line, in that order, C order

What is NOT in the checkpoints (input layout, masks, padding, pooling) is written into the
header from MODELS / COMMON below. Those values were inferred from the weights, see HANDOFF.md
section 14.2. If the training code turns out to differ, change them HERE, re-run this script and
make_model_golden.py, then run the Kotlin tests. The app has no copy of these settings.
"""
import hashlib
import os
import struct
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from pth_reader import load  # noqa: E402

CKPT_DIR = os.path.join(HERE, "checkpoints")
OUT_DIR = os.path.join(HERE, "..", "shared", "models")
MAGIC = b"AISLM1\n"

# The 79 columns of a normalized take (aisl_norm.py FEATURE_COLUMNS / Normalizer.kt, spec v3).
FEATURE_COLUMNS = (
    ["t", "g_valid"]
    + [f"g_{a}{i}" for i in range(21) for a in "xyz"]
    + ["g_px", "g_py", "glove_valid"]
    + [f"flex{i}" for i in range(1, 6)]
    + ["acc_x", "acc_y", "acc_z", "gyro_x", "gyro_y", "gyro_z"]
)
assert len(FEATURE_COLUMNS) == 79

# Same for every model (inferred, HANDOFF 14.2).
COMMON = {
    "format": "1",
    "feature_spec_version": "3",   # must equal Normalizer.SPEC_VERSION in the app
    "in_features": "79",
    "seq_len": "120",              # 30 Hz x 4 s
    "hz": "30",
    "conv_kernel": "3",
    "conv_padding": "1",           # inferred (weakest evidence)
    "pooling": "last_step",        # lstm_out[:, -1, :], inferred
    "bn_eps": "1e-05",             # PyTorch default
}

# zero_cols = columns set to 0 before the network, exactly as in training (first-last, inclusive).
# camera / glove: required | optional | off.
MODELS = [
    {
        "id": "multimodal_raw", "order": "1",
        "title": "Multimodal",
        "subtitle": "Camera + glove",
        "note": "Trained on the recorded takes as they are.",
        "modality": "multimodal", "camera": "required", "glove": "required", "zero_cols": "",
    },
    {
        "id": "multimodal_augmented_60reps", "order": "2",
        "title": "Multimodal (augmented)",
        "subtitle": "Camera + glove",
        "note": "Same inputs, trained on augmented data (60 reps).",
        "modality": "multimodal", "camera": "required", "glove": "required", "zero_cols": "",
    },
    {
        "id": "unimodal_vision_raw", "order": "3",
        "title": "Vision only",
        "subtitle": "Camera only, no glove",
        "note": "Glove columns are switched off.",
        "modality": "vision", "camera": "required", "glove": "off", "zero_cols": "63-78",
    },
    {
        "id": "unimodal_glove_raw", "order": "4",
        "title": "Glove only",
        "subtitle": "Glove only, no camera",
        "note": "Camera columns are switched off.",
        # camera=optional: columns 63-66 (g_y20, g_z20, g_px, g_py) come from the camera and were
        # NOT zeroed in training (mask boundary off by 4, HANDOFF 14.2). With the camera off they are 0.
        "modality": "glove", "camera": "optional", "glove": "required", "zero_cols": "0-62",
    },
]

TENSORS = [
    ("conv1d.weight", (32, 79, 3)), ("conv1d.bias", (32,)),
    ("bn1.weight", (32,)), ("bn1.bias", (32,)), ("bn1.running_mean", (32,)), ("bn1.running_var", (32,)),
    ("bilstm.weight_ih_l0", (128, 32)), ("bilstm.weight_hh_l0", (128, 32)),
    ("bilstm.bias_ih_l0", (128,)), ("bilstm.bias_hh_l0", (128,)),
    ("bilstm.weight_ih_l0_reverse", (128, 32)), ("bilstm.weight_hh_l0_reverse", (128, 32)),
    ("bilstm.bias_ih_l0_reverse", (128,)), ("bilstm.bias_hh_l0_reverse", (128,)),
    ("bn2.weight", (64,)), ("bn2.bias", (64,)), ("bn2.running_mean", (64,)), ("bn2.running_var", (64,)),
    ("fc.weight", (7, 64)), ("fc.bias", (7,)),
]
EXPECTED_KEYS = [n for n, _ in TENSORS] + ["bn1.num_batches_tracked", "bn2.num_batches_tracked"]


def sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def export(m):
    src = os.path.join(CKPT_DIR, m["id"] + ".pth")
    ck = load(src)
    sd = ck["model_state_dict"]
    if sorted(sd.keys()) != sorted(EXPECTED_KEYS):
        raise SystemExit(f"{m['id']}: unexpected layers {sorted(set(sd) ^ set(EXPECTED_KEYS))}")
    classes = [c for c, _ in sorted(ck["class_to_idx"].items(), key=lambda kv: kv[1])]
    if sorted(ck["class_to_idx"].values()) != list(range(len(classes))):
        raise SystemExit(f"{m['id']}: class indices are not 0..n-1")
    if any("|" in c or "\n" in c or "=" in c for c in classes):
        raise SystemExit(f"{m['id']}: class name with a reserved character")

    header = dict(COMMON)
    header.update(m)
    header["classes"] = "|".join(classes)
    header["conv_channels"] = "32"
    header["lstm_hidden"] = "32"
    header["source_file"] = os.path.basename(src)
    header["source_sha256"] = sha256(src)
    hist = ck["history"]
    header["epochs"] = str(len(hist["val_acc"]))
    header["val_acc_last"] = repr(float(hist["val_acc"][-1]))
    header["tensors"] = ",".join(f"{n}:{'x'.join(str(d) for d in shape)}" for n, shape in TENSORS)

    blobs = []
    for name, shape in TENSORS:
        a = np.asarray(sd[name])
        if a.shape != shape or a.dtype != np.float32:
            raise SystemExit(f"{m['id']}: {name} is {a.shape} {a.dtype}, expected {shape} float32")
        if not np.isfinite(a).all():
            raise SystemExit(f"{m['id']}: {name} has NaN/inf")
        blobs.append(np.ascontiguousarray(a, dtype="<f4").tobytes())

    text = "".join(f"{k}={v}\n" for k, v in header.items()).encode("utf-8")
    out = os.path.join(OUT_DIR, m["id"] + ".aislm")
    with open(out, "wb") as f:
        f.write(MAGIC)
        f.write(struct.pack("<i", len(text)))
        f.write(text)
        for b in blobs:
            f.write(b)
    print(f"{os.path.basename(out)}: {os.path.getsize(out)} bytes, classes {classes}, "
          f"zero_cols '{m['zero_cols']}', sha256 {sha256(out)[:12]}")
    return out


def read_aislm(path):
    """-> (header dict, {tensor name: float32 array}). Mirror of SignModel.parse (Kotlin)."""
    with open(path, "rb") as f:
        data = f.read()
    assert data[:len(MAGIC)] == MAGIC, "not an AISLM1 file"
    (n,) = struct.unpack_from("<i", data, len(MAGIC))
    pos = len(MAGIC) + 4
    header = dict(line.split("=", 1) for line in data[pos:pos + n].decode("utf-8").splitlines() if line)
    pos += n
    tensors = {}
    for item in header["tensors"].split(","):
        name, dims = item.split(":")
        shape = tuple(int(d) for d in dims.split("x"))
        count = int(np.prod(shape))
        tensors[name] = np.frombuffer(data, dtype="<f4", count=count, offset=pos).reshape(shape)
        pos += 4 * count
    assert pos == len(data), "trailing bytes"
    return header, tensors


def zero_cols(spec):
    """'63-78' / '0-62,70-71' / '' -> sorted list of column indices."""
    cols = []
    for part in filter(None, spec.split(",")):
        a, b = part.split("-")
        cols += range(int(a), int(b) + 1)
    return sorted(cols)


if __name__ == "__main__":
    os.makedirs(OUT_DIR, exist_ok=True)
    for model in MODELS:
        path = export(model)
        hdr, ts = read_aislm(path)   # read back
        sd_ = load(os.path.join(CKPT_DIR, model["id"] + ".pth"))["model_state_dict"]
        for name_, _ in TENSORS:
            assert np.array_equal(ts[name_], np.asarray(sd_[name_])), name_
    with open(os.path.join(OUT_DIR, "feature_columns.txt"), "w", newline="\n") as f:
        f.write("\n".join(FEATURE_COLUMNS) + "\n")
    print("ok: every tensor read back bit-equal")
