"""Reference outputs for the Kotlin forward pass (android/core SignModel), from REAL PyTorch.

    <python with torch + numpy> models/make_model_golden.py

Loads every models/checkpoints/<id>.pth with torch.load(weights_only=True) into a torch module
(strict=True, so the layer list and shapes must match the checkpoint exactly), runs a set of
inputs through it in eval mode and writes shared/golden/sign_model/:
    inputs.f32            float32 little-endian, cases x 120 x 79
    inputs_shape.txt      "cases 120 79"
    cases.txt             what each case is
    <id>_expected.csv     case, logits, probabilities, top class
SignModelTest (Gradle :core:test) must reproduce them.

The parts a checkpoint does not store (masked columns, conv padding, pooling) are read from the
exported shared/models/<id>.aislm header, i.e. from export_models.py: one place to change them.
"""
import csv
import os
import sys

import numpy as np
import torch
import torch.nn as nn

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from export_models import MODELS, TENSORS, FEATURE_COLUMNS, read_aislm, zero_cols  # noqa: E402

ROOT = os.path.join(HERE, "..")
OUT = os.path.join(ROOT, "shared", "golden", "sign_model")
T, C = 120, 79


class CnnBiLstm(nn.Module):
    """Layer names = the checkpoint's state-dict keys."""

    def __init__(self, n_classes, padding, zero):
        super().__init__()
        self.conv1d = nn.Conv1d(C, 32, kernel_size=3, padding=padding)
        self.bn1 = nn.BatchNorm1d(32)
        self.relu = nn.ReLU()
        self.dropout1 = nn.Dropout(0.3)   # identity in eval mode, rate irrelevant
        self.bilstm = nn.LSTM(32, 32, num_layers=1, batch_first=True, bidirectional=True)
        self.bn2 = nn.BatchNorm1d(64)
        self.dropout2 = nn.Dropout(0.3)
        self.fc = nn.Linear(64, n_classes)
        self.zero = zero

    def forward(self, x):                      # (batch, time, 79)
        x = x.clone()
        if self.zero:
            x[:, :, self.zero] = 0.0           # the training mask of the unimodal models
        y = self.relu(self.bn1(self.conv1d(x.permute(0, 2, 1))))
        out, _ = self.bilstm(self.dropout1(y).permute(0, 2, 1))
        return self.fc(self.dropout2(self.bn2(out[:, -1, :])))


def norm_csv(path):
    with open(path, newline="") as f:
        rows = list(csv.reader(f))
    assert rows[0] == FEATURE_COLUMNS, path
    a = np.array([[float(v) for v in r] for r in rows[1:]], dtype=np.float64)
    assert a.shape == (T, C), (path, a.shape)
    return a


def cases():
    rng = np.random.default_rng(20261120)
    out = []
    out.append(("random_normal", rng.normal(0.0, 1.0, (T, C))))
    out.append(("zeros", np.zeros((T, C))))
    out.append(("desktop_take_hello_no_glove_cal",
                norm_csv(os.path.join(ROOT, "shared", "golden", "norm_expected", "S01_hello_rep01_norm.csv"))))
    phone = os.path.join(ROOT, "MediaPipe", "data_phone_nothing", "norm_from_phone")
    out.append(("phone_take_home_glove_calibrated", norm_csv(os.path.join(phone, "S01_home_rep01_norm.csv"))))
    out.append(("phone_take_thank_you_glove_calibrated", norm_csv(os.path.join(phone, "S01_thank-you_rep02_norm.csv"))))
    # near the training data's channel means (recovered from the weights, models/forensics)
    mu = np.load(os.path.join(HERE, "forensics", "mu_est.npy"))
    x = np.tile(mu, (T, 1)) + rng.normal(0.0, 0.05, (T, C))
    x[:, 0] = np.arange(T) / 30.0
    x[:, 1] = 1.0
    x[:, 67] = 1.0
    out.append(("training_like_means", x))
    out.append(("random_uniform_wide", rng.uniform(-3.0, 3.0, (T, C))))
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    cs = cases()
    x32 = np.stack([c[1] for c in cs]).astype("<f4")
    x32.tofile(os.path.join(OUT, "inputs.f32"))
    with open(os.path.join(OUT, "inputs_shape.txt"), "w", newline="\n") as f:
        f.write(f"{len(cs)} {T} {C}\n")
    with open(os.path.join(OUT, "cases.txt"), "w", newline="\n") as f:
        f.write("".join(f"{i} {name}\n" for i, (name, _) in enumerate(cs)))
    x = torch.from_numpy(x32.astype(np.float32))

    for m in MODELS:
        header, tensors = read_aislm(os.path.join(ROOT, "shared", "models", m["id"] + ".aislm"))
        ck = torch.load(os.path.join(HERE, "checkpoints", m["id"] + ".pth"), map_location="cpu", weights_only=True)
        sd = ck["model_state_dict"]
        classes = [c for c, _ in sorted(ck["class_to_idx"].items(), key=lambda kv: kv[1])]
        assert classes == header["classes"].split("|")
        for name, _ in TENSORS:   # exported file == checkpoint, as torch reads it
            assert np.array_equal(tensors[name], sd[name].numpy()), (m["id"], name)
        assert header["pooling"] == "last_step" and header["conv_kernel"] == "3"
        net = CnnBiLstm(len(classes), int(header["conv_padding"]), zero_cols(header["zero_cols"]))
        net.load_state_dict(sd, strict=True)
        net.eval()
        with torch.no_grad():
            logits = net(x)
            probs = torch.softmax(logits.double(), dim=1)
        path = os.path.join(OUT, m["id"] + "_expected.csv")
        with open(path, "w", newline="\n") as f:
            f.write(",".join(["case"] + [f"logit_{c}" for c in classes] + [f"prob_{c}" for c in classes] + ["top"]) + "\n")
            for i, (name, _) in enumerate(cs):
                lg = [repr(float(v)) for v in logits[i].double()]
                pr = [repr(float(v)) for v in probs[i]]
                f.write(",".join([name] + lg + pr + [classes[int(torch.argmax(logits[i]))]]) + "\n")
        tops = [(cs[i][0], classes[int(torch.argmax(logits[i]))], round(float(probs[i].max()), 3)) for i in range(len(cs))]
        print(m["id"], "torch", torch.__version__, tops)


if __name__ == "__main__":
    main()
