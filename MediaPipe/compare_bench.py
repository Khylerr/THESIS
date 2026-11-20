#!/usr/bin/env python3
"""Runs the PC's MediaPipe on the frame the app's "GPU test" saved, and compares landmarks.

The app saves (Android/data/com.aisla.app/files/bench/): frame.png = the exact upright,
mirrored image its MediaPipe saw, cpu.csv / gpu.csv = the phone's landmarks for it (IMAGE
mode). This runs the same model + settings (shared config) on the same pixels on the PC.

    adb pull /sdcard/Android/data/com.aisla.app/files/bench bench
    venv\\Scripts\\python.exe compare_bench.py bench
"""
import csv
import os
import sys

import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_tasks
from mediapipe.tasks.python import vision as mp_vision

import aisl_norm


def read_hands(path):
    with open(path, newline="") as f:
        return [(row["label"], [float(row[f"{a}{i}"]) for i in range(21) for a in "xyz"])
                for row in csv.DictReader(f)]


def pc_hands(png, cfg):
    model, _ = aisl_norm.load_model(cfg)
    opts = mp_vision.HandLandmarkerOptions(
        base_options=mp_tasks.BaseOptions(model_asset_buffer=model,
                                          delegate=mp_tasks.BaseOptions.Delegate.CPU),
        running_mode=mp_vision.RunningMode.IMAGE,
        num_hands=cfg["num_hands"],
        min_hand_detection_confidence=cfg["min_hand_detection_confidence"],
        min_hand_presence_confidence=cfg["min_hand_presence_confidence"],
        min_tracking_confidence=cfg["min_tracking_confidence"])
    rgb = cv2.cvtColor(cv2.imread(png), cv2.COLOR_BGR2RGB)   # already upright + mirrored: no flip
    with mp_vision.HandLandmarker.create_from_options(opts) as lm:
        r = lm.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))
    hands = [(aisl_norm.handedness_label(hd[0].category_name, cfg),
              [v for p in lms for v in (p.x, p.y, p.z)])
             for lms, hd in zip(r.hand_landmarks, r.handedness)]
    return hands, rgb.shape[1], rgb.shape[0]


def diff(a, b, w, h):
    xy = max(max(abs(a[3 * k] - b[3 * k]) * w, abs(a[3 * k + 1] - b[3 * k + 1]) * h) for k in range(21))
    z = max(abs(a[3 * k + 2] - b[3 * k + 2]) for k in range(21))
    return xy, z


def main(folder):
    cfg = aisl_norm.load_mp_config()
    pc, w, h = pc_hands(os.path.join(folder, "frame.png"), cfg)
    print(f"frame {w}x{h}: PC found {len(pc)} hand(s)")
    if not pc:
        return
    for name in ("cpu", "gpu"):
        path = os.path.join(folder, name + ".csv")
        if not os.path.exists(path):
            print(f"  phone {name.upper()}: no file")
            continue
        phone = read_hands(path)
        if not phone:
            print(f"  phone {name.upper()}: no hand")
            continue
        xy, z = diff(pc[0][1], phone[0][1], w, h)
        print(f"  phone {name.upper()} vs PC: max {xy:.2f} px in x/y, max {z:.4f} in z, "
              f"labels phone={phone[0][0]} PC={pc[0][0]}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "bench")
