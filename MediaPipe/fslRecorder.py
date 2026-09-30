#!/usr/bin/env python3
"""FSL take recorder: camera + MediaPipe Hands (glove/BLE stream not included yet).

Each take is a fixed-length recording (default 4 s) saved as one wide CSV
(one row per camera frame) plus a JSON sidecar with metadata and quality stats.

Usage (VS Code): edit the Config block below (signer, signs, reps, glove hand),
then press Run > "Run Python File". No command-line arguments are needed.

Keys (click the video window first so it has focus):
    SPACE = start take | ENTER/Y = keep | R/N = redo | ESC = quit
"""
import csv
import glob
import json
import os
import random
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime

import cv2
import mediapipe as mp

try:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
except NameError:  # e.g. running cell-by-cell in the VS Code interactive window
    BASE_DIR = os.getcwd()


# ============================================================================
# CONFIG: edit this block before each session (replaces command-line arguments)
# ============================================================================
@dataclass
class Config:
    # --- change these per session ---
    signer: str = "S01"                     # signer ID
    signs: list = field(default_factory=lambda: ["hello", "thank-you", "home"])
    reps: int = 15                          # repetitions per sign
    glove_hand: str = "Right"               # "Left" or "Right": MediaPipe label (after flip)

    # --- usually leave as is ---
    session: str = field(default_factory=lambda: datetime.now().strftime("%Y%m%d"))
    out: str = os.path.join(BASE_DIR, "data")   # saved next to this script
    camera: int = 0                         # webcam index; try 1 if 0 is the wrong camera
    record_sec: float = 4.0
    countdown: float = 3.0
    log_other: bool = True                  # also log the non-glove hand's 63 values

    def __post_init__(self):
        if self.glove_hand not in ("Left", "Right"):
            raise ValueError('glove_hand must be "Left" or "Right"')
        if not self.signs:
            raise ValueError("signs must not be empty")


mp_drawing = mp.solutions.drawing_utils
mp_styles = mp.solutions.drawing_styles
mp_hands = mp.solutions.hands

WIN = "FSL take recorder"
N_LM = 21
NAN63 = [float("nan")] * (N_LM * 3)

# Quality-gate thresholds: judgment calls, tune them from your pilot recordings.
MIN_FPS = 27.0
MIN_DETECTED = 0.90
MAX_GAP_SEC = 0.10
MAX_READ_FAILS = 30

MP_SETTINGS = dict(
    max_num_hands=2,
    model_complexity=0,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5,
)


# ----------------------------------------------------------------------------
# Row building
# ----------------------------------------------------------------------------
def make_header(log_other):
    coords = [f"{a}{i}" for i in range(N_LM) for a in "xyz"]
    header = ["frame", "t_sec", "detected", "hand_conf"] + coords
    if log_other:
        header += ["other_detected"] + [f"o_{c}" for c in coords]
    return header


def flatten(lms):
    """21 landmarks -> 63 values in x0,y0,z0,x1,y1,z1,... order."""
    return [v for p in lms.landmark for v in (p.x, p.y, p.z)]


def pick_hands(results, glove_hand):
    """Return (glove, other); each is (label, score, landmarks) or None.

    The gloved hand is chosen by MediaPipe's handedness label (highest score if
    several), never by detection order. Frames are flipped BEFORE processing, so
    the label matches the signer's real hand.
    """
    found = []
    if results.multi_hand_landmarks and results.multi_handedness:
        for lms, hd in zip(results.multi_hand_landmarks, results.multi_handedness):
            c = hd.classification[0]
            found.append((c.label, c.score, lms))
    glove_candidates = [h for h in found if h[0] == glove_hand]
    glove = max(glove_candidates, key=lambda h: h[1]) if glove_candidates else None
    others = [h for h in found if h is not glove]
    other = max(others, key=lambda h: h[1]) if others else None
    return glove, other


def build_row(frame_idx, t_rec, glove, other, log_other):
    """One row per frame, always. Missing hand -> detected=0 and NaN values."""
    if glove:
        row = [frame_idx, round(t_rec, 4), 1, round(glove[1], 4)] + flatten(glove[2])
    else:
        row = [frame_idx, round(t_rec, 4), 0, float("nan")] + NAN63
    if log_other:
        row += ([1] + flatten(other[2])) if other else ([0] + NAN63)
    return row


# ----------------------------------------------------------------------------
# Camera / display helpers
# ----------------------------------------------------------------------------
def grab(cap):
    """Read a frame and timestamp it immediately, before any processing."""
    ok, frame = cap.read()
    t = time.perf_counter()
    if not ok:
        return None, t
    return cv2.flip(frame, 1), t  # flip first: process what the signer sees


def detect(hands, frame_bgr):
    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    rgb.flags.writeable = False
    return hands.process(rgb)


def draw_hands(image, results):
    if results.multi_hand_landmarks:
        for lms in results.multi_hand_landmarks:
            mp_drawing.draw_landmarks(
                image,
                lms,
                mp_hands.HAND_CONNECTIONS,
                mp_styles.get_default_hand_landmarks_style(),
                mp_styles.get_default_hand_connections_style(),
            )


def put(image, text, org, color=(255, 255, 255), scale=0.8, thick=2):
    cv2.putText(image, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), thick + 2, cv2.LINE_AA)
    cv2.putText(image, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thick, cv2.LINE_AA)


# ----------------------------------------------------------------------------
# Session phases
# ----------------------------------------------------------------------------
def wait_for_start(cap, hands, banner):
    """Live preview with landmarks so the signer can position their hand."""
    fails = 0
    while True:
        frame, _ = grab(cap)
        if frame is None:
            fails += 1
            if fails >= MAX_READ_FAILS:
                raise RuntimeError("Camera stopped returning frames.")
            continue
        fails = 0
        results = detect(hands, frame)
        draw_hands(frame, results)
        put(frame, banner, (20, 35), scale=0.7)
        put(frame, "SPACE = start take    ESC = quit", (20, 70), (0, 255, 255), 0.6, 1)
        cv2.imshow(WIN, frame)
        key = cv2.waitKey(1) & 0xFF
        if key == 32:
            return True
        if key == 27:
            return False


def record_take(cap, hands, args):
    """Countdown (tracker keeps running) then a fixed-duration recording.

    Returns (rows, last_frame, t_rec0, t_end); rows is None if the take was
    aborted with ESC. Raises RuntimeError if the camera stops.
    """
    rows, last_frame = [], None
    fails, frame_idx = 0, 0
    t0 = time.perf_counter()
    t_rec0 = t0 + args.countdown  # recording clock starts here
    # TODO(BLE): start the glove listener thread before this loop and, after it,
    # slice its buffer to [t_rec0, t_rec0 + record_sec] using the same
    # time.perf_counter() clock.
    while True:
        frame, t = grab(cap)
        if frame is None:
            fails += 1
            if fails >= MAX_READ_FAILS:
                raise RuntimeError("Camera stopped returning frames.")
            continue
        fails = 0

        t_rec = t - t_rec0
        if t_rec >= args.record_sec:  # deadline checked before storing the frame
            return rows, last_frame, t_rec0, t

        results = detect(hands, frame)
        draw_hands(frame, results)

        if t_rec < 0:
            put(frame, f"Get ready: {int(-t_rec) + 1}", (20, 60), (0, 0, 255), 1.5, 3)
        else:
            glove, other = pick_hands(results, args.glove_hand)
            rows.append(build_row(frame_idx, t_rec, glove, other, args.log_other))
            frame_idx += 1
            ok = glove is not None
            put(frame, f"REC {args.record_sec - t_rec:.1f}s", (20, 50), (0, 255, 0), 1.0, 2)
            put(frame, "glove hand: OK" if ok else "glove hand: LOST", (20, 85),
                (0, 255, 0) if ok else (0, 0, 255), 0.7, 2)

        last_frame = frame
        cv2.imshow(WIN, frame)
        if cv2.waitKey(1) & 0xFF == 27:
            return None, None, t_rec0, t


def quality(rows):
    n = len(rows)
    if n < 2:
        return dict(n_frames=n, fps=0.0, detected_frac=0.0, max_gap_sec=None,
                    warnings=["too few frames"])
    ts = [r[1] for r in rows]
    span = ts[-1] - ts[0]
    fps = (n - 1) / span if span > 0 else 0.0
    max_gap = max(b - a for a, b in zip(ts, ts[1:]))
    det = sum(r[2] for r in rows) / n
    warnings = []
    if fps < MIN_FPS:
        warnings.append(f"low fps ({fps:.1f})")
    if det < MIN_DETECTED:
        warnings.append(f"low detection ({det:.0%})")
    if max_gap > MAX_GAP_SEC:
        warnings.append(f"gap of {max_gap * 1000:.0f} ms between frames")
    return dict(n_frames=n, fps=round(fps, 2), detected_frac=round(det, 4),
                max_gap_sec=round(max_gap, 4), warnings=warnings)


def review(last_frame, q, banner):
    """Show the last frame with the quality summary; return keep/redo/quit."""
    frame = last_frame.copy()
    bad = bool(q["warnings"])
    color = (0, 0, 255) if bad else (0, 255, 0)
    put(frame, banner, (20, 35), scale=0.7)
    put(frame, f"{q['n_frames']} frames, {q['fps']:.1f} fps, {q['detected_frac']:.0%} detected",
        (20, 70), color, 0.7, 2)
    for i, w in enumerate(q["warnings"]):
        put(frame, "WARNING: " + w, (20, 105 + 30 * i), (0, 0, 255), 0.6, 2)
    put(frame, "ENTER/Y = keep    R/N = redo    ESC = quit", (20, frame.shape[0] - 20),
        (0, 255, 255), 0.6, 1)
    cv2.imshow(WIN, frame)
    while True:
        key = cv2.waitKey(0) & 0xFF
        if key in (13, ord("y"), ord("Y")):
            return "keep"
        if key in (ord("r"), ord("R"), ord("n"), ord("N")):
            return "redo"
        if key == 27:
            return "quit"


# ----------------------------------------------------------------------------
# Files and planning
# ----------------------------------------------------------------------------
def slug(text):
    return re.sub(r"[^A-Za-z0-9_-]+", "-", text).strip("-")


def stem_prefix(args, sign):
    return f"{args.signer}_{slug(sign)}_rep"


def existing_count(args, sign):
    pattern = os.path.join(args.out, args.signer, stem_prefix(args, sign) + "*.csv")
    return len(glob.glob(pattern))


def next_rep(args, sign):
    rep = existing_count(args, sign) + 1
    while os.path.exists(take_path(args, sign, rep, ".csv")):
        rep += 1
    return rep


def take_path(args, sign, rep, ext):
    return os.path.join(args.out, args.signer, f"{stem_prefix(args, sign)}{rep:02d}{ext}")


def build_plan(args):
    """Cycle through signs each round (shuffled) instead of all reps of one sign."""
    remaining = {s: max(0, args.reps - existing_count(args, s)) for s in args.signs}
    plan = []
    for r in range(max(remaining.values(), default=0)):
        batch = [s for s in args.signs if remaining[s] > r]
        random.shuffle(batch)
        plan += batch
    return plan


def save_take(args, cap, header, rows, q, sign, rep, t_rec0, t_end):
    os.makedirs(os.path.join(args.out, args.signer), exist_ok=True)
    csv_path = take_path(args, sign, rep, ".csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)
    meta = {
        "signer": args.signer,
        "sign": sign,
        "rep": rep,
        "session": args.session,
        "glove_hand": args.glove_hand,
        "saved_local": datetime.now().isoformat(timespec="seconds"),
        "record_sec": args.record_sec,
        "countdown_sec": args.countdown,
        "flipped_before_processing": True,
        "clock": "time.perf_counter",
        "record_start_perf_counter": t_rec0,
        "record_end_perf_counter": t_end,
        "camera_requested": {"width": 640, "height": 480, "fps": 30},
        "camera_reported": {
            "width": cap.get(cv2.CAP_PROP_FRAME_WIDTH),
            "height": cap.get(cv2.CAP_PROP_FRAME_HEIGHT),
            "fps": cap.get(cv2.CAP_PROP_FPS),
        },
        "mediapipe_version": getattr(mp, "__version__", "unknown"),
        "mediapipe_settings": MP_SETTINGS,
        "opencv_version": cv2.__version__,
        "columns": len(header),
        "quality": q,
    }
    with open(take_path(args, sign, rep, ".json"), "w") as f:
        json.dump(meta, f, indent=2)
    return csv_path


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
def main():
    args = Config()
    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        sys.exit("Cannot open camera.")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 30)
    print(f"Camera reports {cap.get(cv2.CAP_PROP_FRAME_WIDTH):.0f}x"
          f"{cap.get(cv2.CAP_PROP_FRAME_HEIGHT):.0f} @ {cap.get(cv2.CAP_PROP_FPS):.0f} fps "
          f"(requested 640x480 @ 30; the measured fps per take is what counts)")

    header = make_header(args.log_other)
    plan = build_plan(args)
    if not plan:
        print("Nothing left to record for these signs.")
        cap.release()
        return
    print(f"{len(plan)} takes planned for {args.signer}.")

    quit_all = False
    try:
        with mp_hands.Hands(static_image_mode=False, **MP_SETTINGS) as hands:
            for i, sign in enumerate(plan, 1):
                if quit_all:
                    break
                while True:
                    rep = next_rep(args, sign)
                    banner = f"[{i}/{len(plan)}] {sign}  (rep {rep}/{args.reps})"
                    if not wait_for_start(cap, hands, banner):
                        quit_all = True
                        break
                    rows, last_frame, t_rec0, t_end = record_take(cap, hands, args)
                    if rows is None:  # ESC mid-take: discard, back to the start screen
                        print("Take aborted.")
                        continue
                    q = quality(rows)
                    print(f"{banner}: {q['n_frames']} frames, {q['fps']:.1f} fps, "
                          f"{q['detected_frac']:.0%} detected"
                          + (f"  WARN: {'; '.join(q['warnings'])}" if q["warnings"] else ""))
                    decision = review(last_frame, q, banner)
                    if decision == "keep":
                        path = save_take(args, cap, header, rows, q, sign, rep, t_rec0, t_end)
                        print(f"  saved {path}")
                        break
                    if decision == "quit":
                        quit_all = True
                        break
                    print("  discarded, redoing.")
    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()