#!/usr/bin/env python3
"""FSL take recorder: camera + MediaPipe Hands + glove (5 flex + MPU6050) over BLE.

Each take is a fixed-length recording (default 4 s) saved as one wide CSV
(one row per camera frame) plus a JSON sidecar with metadata and quality stats.

MediaPipe: the Tasks HandLandmarker with hand_landmarker.task, configured from
../shared/mediapipe_config.json: the SAME model file (checked by sha256), API, version
and settings as the Android app, so desktop and phone landmarks come from one model.
(Takes recorded before this change used the old mp.solutions.hands lite model.)
To compare desktop and phone takes, use aisl_norm.py / normalize_takes.py.

Synchronization
---------------
Two streams run on the same PC clock (time.perf_counter):
  * camera frames (~30 fps), read on their own thread and timestamped the moment the
    driver delivers them; the main loop always processes the newest frame
  * glove samples (~50 Hz), read in a background thread so it never waits on the
    camera (BLE: ESP32 timestamp mapped to the PC clock; serial: arrival time)

After each take, pandas.merge_asof joins the glove stream onto the camera frames:
every frame gets the glove sample closest in time (within SYNC tolerance).
Output per frame = full MediaPipe row + 11 sensor values
(flex1..flex5, acc_x/y/z, gyro_x/y/z) + glove_dt_ms (how far apart the two
timestamps were, for auditing the sync).

Usage (VS Code): edit the Config block below (signer, signs, reps, glove hand,
glove port), then press Run > "Run Python File". No command-line arguments needed.
Glove transport (Config.glove_transport):
  "ble"    -> hand_sign_glove_ble firmware, read with bleak. Each packet carries the
              ESP32's own millis() timestamp, mapped onto the PC clock, so BLE
              batching jitter does not affect sync. Round-trip latency is measured
              at startup (30 PING/PONGs) and saved with every take.
  "serial" -> old Bluetooth Classic firmware on a COM port (timestamped on arrival).

Requires:  pip install pandas bleak      (pyserial too if using "serial")

Gloved hand (Config.hand_mode): "assume" (default) ignores MediaPipe's Left/Right
guess, which gloves often confuse. One visible hand = the glove hand; with two hands,
the one continuing from the glove hand's last position (else the glove-hand side of
the mirrored image). How often MediaPipe's label disagreed is saved per take.

Speed: per-frame vision latency (capture -> landmarks) is shown live (SPEED light)
and saved per take (median / p95 / max, share of frames within 20 ms).

Live dashboard (right side of the window): status lights for CAMERA, HAND, GLOVE,
IMU, SYNC and SPEED, plus scrolling graphs of the camera's finger openness and the
glove's flex / accel / gyro, so you can see both streams react as you move.
Same colour = same finger in the camera and flex graphs.

Keys (click the video window first so it has focus):
    SPACE = start take | C = calibrate glove (open hand, then fist) | ENTER/Y = keep | R/N = redo | ESC = quit

Glove calibration (C) is required before the first take and again whenever the glove reconnects
or re-zeroes itself (BOOT button / reboot): hold the hand open and flat (3 s), then a tight
fist (3 s). The open/fist values are saved with every take; normalize_takes.py turns flex into
0 = open .. 1 = fist with them (see aisl_norm.flex_calibration).
"""
import glob
import json
import math
import os
import random
import re
import struct
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime

import cv2
import mediapipe as mp
import numpy as np
import pandas as pd
from mediapipe.framework.formats import landmark_pb2
from mediapipe.tasks import python as mp_tasks
from mediapipe.tasks.python import vision as mp_vision

import aisl_norm

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
    glove_hand: str = "Right"               # the gloved hand ("Left" or "Right")
    hand_mode: str = "assume"               # "assume": ignore MediaPipe's Left/Right guess, the
                                            #   tracked hand IS the glove hand (robust with gloves)
                                            # "label": trust MediaPipe's handedness label (old way)
    glove_transport: str = "ble"            # "ble" (hand_sign_glove_ble firmware) or "serial" (old Classic firmware)
    glove_ble_name: str = "AISL_Glove"      # BLE device name (transport "ble")
    glove_port: str = "COM6"                # Bluetooth "Outgoing" COM port (transport "serial" only)

    # --- usually leave as is ---
    session: str = field(default_factory=lambda: datetime.now().strftime("%Y%m%d"))
    out: str = os.path.join(BASE_DIR, "data")   # saved next to this script
    camera: int = 0                         # webcam index; try 1 if 0 is the wrong camera
    record_sec: float = 4.0
    countdown: float = 3.0
    log_other: bool = False                 # one-handed signs only: no other_detected/o_* columns
    glove_baud: int = 115200                # ignored by Bluetooth SPP, needed by pyserial
    sync_direction: str = "nearest"         # merge_asof direction: "nearest" | "backward"
    sync_tolerance_sec: float = 0.04        # max frame<->glove time gap to accept a match
    camera_backend: str = "dshow"           # Windows: "dshow" (+MJPG, fastest/most reliable) or "any"
    # MediaPipe settings (hands, confidences, model) live in ../shared/mediapipe_config.json,
    # shared with the Android app. Change them there, never only here.
    show_dashboard: bool = True             # live status + signal graphs beside the video
    dashboard_hz: float = 10.0              # side panel redraw rate (video itself is every frame)
    plot_span_sec: float = 3.0              # seconds of history shown in the live graphs

    def __post_init__(self):
        if self.glove_hand not in ("Left", "Right"):
            raise ValueError('glove_hand must be "Left" or "Right"')
        if not self.signs:
            raise ValueError("signs must not be empty")
        if self.hand_mode not in ("assume", "label"):
            raise ValueError('hand_mode must be "assume" or "label"')
        if self.glove_transport not in ("ble", "serial"):
            raise ValueError('glove_transport must be "ble" or "serial"')
        if self.sync_direction not in ("nearest", "backward", "forward"):
            raise ValueError('sync_direction must be "nearest", "backward" or "forward"')


mp_drawing = mp.solutions.drawing_utils
mp_styles = mp.solutions.drawing_styles
mp_hands = mp.solutions.hands

WIN = "FSL take recorder"
N_LM = 21
NAN63 = [float("nan")] * (N_LM * 3)

# The 11 sensor values, in the order the ESP32 prints them
GLOVE_COLS = ["flex1", "flex2", "flex3", "flex4", "flex5",
              "acc_x", "acc_y", "acc_z", "gyro_x", "gyro_y", "gyro_z"]

# Quality-gate thresholds: judgment calls, tune them from your pilot recordings.
MIN_FPS = 27.0
MIN_DETECTED = 0.90
MAX_GAP_SEC = 0.10
MAX_READ_FAILS = 30
MIN_GLOVE_HZ = 40.0          # firmware sends 50 Hz (FRAME_PERIOD_MS = 20)
MIN_GLOVE_MATCHED = 0.95     # fraction of frames that got a glove sample
MAX_GLOVE_GAP_SEC = 0.10     # longest silence in the glove stream during a take

VISION_BUDGET_MS = 1000 / 30   # one camera frame at 30 fps
MAX_VISION_MS = 20.0           # SO1 target: per-frame processing latency <= 20 ms


def mp_settings(cfg, model_sha256):
    """What gets saved in each take's JSON (same keys as the Android app writes)."""
    keys = ["api", "model_file", "running_mode", "delegate", "num_hands",
            "min_hand_detection_confidence", "min_hand_presence_confidence",
            "min_tracking_confidence", "input_mirrored", "invert_handedness_label"]
    return {**{k: cfg[k] for k in keys}, "model_sha256": model_sha256}


class TrackedHand:
    """One hand's 21 landmarks; .landmark[i].x/.y/.z like the old mp.solutions result."""
    __slots__ = ("landmark",)

    def __init__(self, landmarks):
        self.landmark = landmarks


class HandTracker:
    """MediaPipe Tasks HandLandmarker set up from shared/mediapipe_config.json.

    Same model bytes (sha256-checked), API, version and settings as the Android app:
    VIDEO mode (tracks hands between frames), CPU. process() returns the found hands as
    (label, score, TrackedHand); label = the signer's real hand (see
    aisl_norm.handedness_label), score = MediaPipe's handedness score.
    """

    def __init__(self, cfg):
        if cfg["running_mode"] != "VIDEO" or cfg["delegate"] != "CPU":
            raise ValueError("shared config: running_mode must be VIDEO and delegate CPU")
        self.cfg = cfg
        model, self.model_sha256 = aisl_norm.load_model(cfg, BASE_DIR)
        self.version_ok = mp.__version__ == cfg["mediapipe_version"]
        if not self.version_ok:
            print(f"WARNING: mediapipe {mp.__version__} is installed, but the shared config (and the "
                  f"Android app) use {cfg['mediapipe_version']}: "
                  f"pip install mediapipe=={cfg['mediapipe_version']}")
        opts = mp_vision.HandLandmarkerOptions(
            base_options=mp_tasks.BaseOptions(model_asset_buffer=model,
                                              delegate=mp_tasks.BaseOptions.Delegate.CPU),
            running_mode=mp_vision.RunningMode.VIDEO,
            num_hands=cfg["num_hands"],
            min_hand_detection_confidence=cfg["min_hand_detection_confidence"],
            min_hand_presence_confidence=cfg["min_hand_presence_confidence"],
            min_tracking_confidence=cfg["min_tracking_confidence"],
        )
        self._landmarker = mp_vision.HandLandmarker.create_from_options(opts)
        self._last_ms = -1
        self.size = None   # (width, height) of the last image given to MediaPipe

    def process(self, frame_bgr, t):
        """Mirrored BGR frame captured at perf_counter time t -> list of found hands."""
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        ts_ms = max(int(round(t * 1000)), self._last_ms + 1)   # VIDEO mode: strictly increasing
        self._last_ms = ts_ms
        self.size = (frame_bgr.shape[1], frame_bgr.shape[0])
        result = self._landmarker.detect_for_video(
            mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), ts_ms)
        found = []
        for lms, hd in zip(result.hand_landmarks or [], result.handedness or []):
            c = hd[0]
            found.append((aisl_norm.handedness_label(c.category_name, self.cfg), c.score,
                          TrackedHand(lms)))
        return found

    def close(self):
        self._landmarker.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


# ----------------------------------------------------------------------------
# Glove readers (background thread). Two transports, same interface:
#   BleGloveReader     - BLE firmware (hand_sign_glove_ble.ino), binary packets with
#                        the ESP32's own timestamp  <- default
#   SerialGloveReader  - old Bluetooth Classic firmware (text lines over a COM port)
# Buffer item: (t_sync, values[11], t_arrival, seq, flags), times on time.perf_counter().
# ----------------------------------------------------------------------------
_NUM = re.compile(r":\s*(-?\d+(?:\.\d+)?)")


def parse_glove_line(line):
    """'[FLEX] F1:3 F2:-5 ... | [ACCEL] X:0.01 ... | [GYRO] X:...' -> 11 floats, or None.

    Status lines (calibration messages, warnings) are ignored.
    """
    if not line.startswith("[FLEX]"):
        return None
    vals = _NUM.findall(line)
    if len(vals) != len(GLOVE_COLS):
        return None
    return [float(v) for v in vals]


class GloveReaderBase:
    """Rolling buffer + queries shared by both transports."""

    transport = "?"

    def __init__(self, name, keep_sec=30.0):
        self.name = name                # shown in the UI / logs
        self.buf = deque(maxlen=int(keep_sec * 100))
        self.lock = threading.Lock()
        self.connected = False
        self.connection_id = 0          # +1 on every (re)connect: invalidates the flex calibration
        self.last_error = ""
        self.last_status = ""           # last status text from the glove (e.g. MPU warning)
        self.calibration = ""           # last "CAL:DONE ..." line (calibration baselines)
        self.n_bad = 0                  # malformed packets / lines
        self.n_dropped = 0              # packets lost in transit (BLE seq gaps)
        self.mtu = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    # -- lifecycle --
    def start(self, wait_sec=20.0, verbose=True):
        """Start the thread and wait until the first sample arrives (prints progress)."""
        self._thread.start()
        t0 = time.perf_counter()
        last_msg = None
        while time.perf_counter() - t0 < wait_sec:
            if self.latest() is not None:
                return True
            msg = getattr(self, "state", "") + (f" | last error: {self.last_error}" if self.last_error else "")
            if verbose and msg != last_msg and msg.strip(" |"):
                print(f"  [{time.perf_counter() - t0:4.1f}s] glove: {msg}")
                last_msg = msg
            time.sleep(0.05)
        return False

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=3)

    def _run(self):
        raise NotImplementedError

    def _append(self, t_sync, vals, t_arr, seq=-1, flags=0):
        with self.lock:
            self.buf.append((t_sync, vals, t_arr, seq, flags))

    # -- commands (BLE only) --
    def send_command(self, cmd):
        return False

    def measure_rtt(self, n=30):
        return None

    # -- queries --
    def latest(self):
        with self.lock:
            return (self.buf[-1][0], self.buf[-1][1]) if self.buf else None

    def window(self, t_start, t_end):
        """Samples with t_start <= t_sync <= t_end as a DataFrame:
        t, 11 sensor columns, t_arrival, seq, flags."""
        with self.lock:
            rows = [(t, *v, ta, s, f) for t, v, ta, s, f in self.buf if t_start <= t <= t_end]
        return pd.DataFrame(rows, columns=["t"] + GLOVE_COLS + ["t_arrival", "seq", "flags"])

    def recent(self, span):
        """Samples from the last `span` seconds: (times, values) as numpy arrays."""
        t_min = time.perf_counter() - span
        items = []
        with self.lock:
            for item in reversed(self.buf):     # newest first; stop at the window edge
                if item[0] < t_min:
                    break
                items.append((item[0], item[1]))
        if not items:
            return np.empty(0), np.empty((0, len(GLOVE_COLS)))
        items.reverse()
        ts, vs = zip(*items)
        return np.asarray(ts), np.asarray(vs, dtype=float)

    def rate_hz(self, span=1.0):
        t_min = time.perf_counter() - span
        n = 0
        with self.lock:
            for item in reversed(self.buf):
                if item[2] < t_min:
                    break
                n += 1
        return n / span

    def status_text(self):
        last = self.latest()
        if not self.connected:
            return False, f"glove: DISCONNECTED ({self.name})"
        if last is None or time.perf_counter() - last[0] > 0.5:
            return False, "glove: connected, NO DATA"
        return True, f"glove: OK {self.rate_hz():.0f} Hz"


class SerialGloveReader(GloveReaderBase):
    """Old Bluetooth Classic firmware: text lines on a COM port, timestamped on arrival."""

    transport = "bluetooth-classic-spp"

    def __init__(self, port, baud=115200, keep_sec=30.0):
        super().__init__(port, keep_sec)
        self.port, self.baud = port, baud

    def _run(self):
        import serial  # only needed for this transport
        while not self._stop.is_set():
            try:
                with serial.Serial(self.port, self.baud, timeout=0.05) as ser:
                    ser.reset_input_buffer()
                    self.connected, self.last_error = True, ""
                    self.connection_id += 1
                    pending = b""
                    while not self._stop.is_set():
                        chunk = ser.read(ser.in_waiting or 1)
                        if not chunk:
                            continue
                        t = time.perf_counter()
                        pending += chunk
                        *lines, pending = pending.split(b"\n")
                        for raw in lines:
                            self._handle(raw.decode(errors="ignore").strip(), t)
            except (serial.SerialException, OSError) as e:
                self.connected, self.last_error = False, str(e)
                time.sleep(2.0)  # Bluetooth dropped or port busy: retry

    def _handle(self, line, t):
        if not line:
            return
        vals = parse_glove_line(line)
        if vals is not None:
            self._append(t, vals, t)
        elif line.startswith("[FLEX]"):
            self.n_bad += 1
        else:
            self.last_status = line
            if line.startswith(">>> CALIBRATION SUCCESSFUL"):
                self.calibration = line


# --- BLE protocol (must match hand_sign_glove_ble.ino) ---
BLE_SERVICE_UUID = "e1273d67-cf0f-4bb7-9477-4f5d92124a6f"
BLE_DATA_UUID = "ecbd02f0-3d5f-4ad5-952a-9e75b163eeab"
BLE_STATUS_UUID = "493ccb74-46cd-4966-8a16-ba3cca3fd116"
BLE_CMD_UUID = "b8b472e5-964d-4b06-ae50-19a91cccb0a2"
# seq u16, t_ms u32, flex 5x i16, acc 3x i16 (x100), gyro 3x i16 (x1000), flags u8 = 29 bytes
BLE_PACKET = struct.Struct("<HI5h3h3hB")


def decode_ble_packet(data):
    """29-byte packet -> (seq, t_device_sec, [11 values], flags), or None if malformed."""
    if len(data) != BLE_PACKET.size:
        return None
    seq, t_ms, *rest = BLE_PACKET.unpack(bytes(data))
    flex, acc, gyro, flags = rest[0:5], rest[5:8], rest[8:11], rest[11]
    vals = [float(v) for v in flex] + [a / 100.0 for a in acc] + [g / 1000.0 for g in gyro]
    return seq, t_ms / 1000.0, vals, flags


class ClockMapper:
    """Maps the ESP32 clock (millis) onto the PC clock (perf_counter).

    offset = min(t_arrival - t_device) over a sliding window: the lower envelope,
    i.e. the packets that crossed the radio fastest. t_device + offset removes BLE
    batching jitter (several packets arriving at once) and follows the slow drift
    between the two crystals. Resets if the glove reboots (clock jumps).
    """

    def __init__(self, window_sec=10.0):
        self.window = window_sec
        self.hist = deque()   # monotonic deque: (t_arr, d) with increasing d -> O(1) minimum
        self.offset = None

    def update(self, t_dev, t_arr):
        d = t_arr - t_dev
        if self.offset is not None and abs(d - self.offset) > 1.0:
            self.hist.clear()  # glove rebooted / clock jumped
        while self.hist and self.hist[-1][1] >= d:
            self.hist.pop()
        self.hist.append((t_arr, d))
        while self.hist[0][0] < t_arr - self.window:
            self.hist.popleft()
        self.offset = self.hist[0][1]
        return self.offset


class BleGloveReader(GloveReaderBase):
    """BLE firmware: binary notifications with the ESP32's own timestamp (needs bleak).

    t_sync = t_device + clock offset (see ClockMapper): the sample's time on the PC
    clock, as if it had arrived with the minimum radio delay. t_arrival is also kept,
    so the per-packet transport delay can be reported.
    """

    transport = "ble"

    def __init__(self, device_name, keep_sec=30.0):
        super().__init__(device_name, keep_sec)
        self.clock = ClockMapper()
        self._last_seq = None
        self._loop = None
        self._client = None
        self._pong_events, self._pong_times = {}, {}
        self.state = "starting"

    # -- thread / asyncio --
    def _run(self):
        import asyncio
        try:
            import bleak  # noqa: F401
        except ImportError:
            self.last_error = (f"'bleak' is not installed for this Python ({sys.executable}). "
                               f"Run: \"{sys.executable}\" -m pip install bleak")
            return
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._main())
        finally:
            self._loop.close()

    def _is_glove(self, device, adv):
        names = {adv.local_name, device.name}
        uuids = [u.lower() for u in (adv.service_uuids or [])]
        return self.name in names or BLE_SERVICE_UUID in uuids

    async def _main(self):
        import asyncio
        from bleak import BleakClient, BleakScanner
        while not self._stop.is_set():
            try:
                self.state = "scanning"
                dev = await BleakScanner.find_device_by_filter(self._is_glove, timeout=8.0)
                if dev is None:
                    self.last_error = (f"'{self.name}' not found in BLE scan (glove off, already "
                                       f"connected to a phone, or BLE firmware not uploaded?)")
                    continue
                self.state = f"connecting to {dev.address}"
                gone = asyncio.Event()
                async with BleakClient(dev, disconnected_callback=lambda _c: gone.set()) as client:
                    self._client = client
                    self.mtu = getattr(client, "mtu_size", None)
                    await client.start_notify(BLE_STATUS_UUID, self._on_status)
                    await client.start_notify(BLE_DATA_UUID, self._on_data)
                    self.connected, self.last_error, self.state = True, "", "connected"
                    self.connection_id += 1
                    while not self._stop.is_set() and not gone.is_set():
                        await asyncio.sleep(0.1)
            except Exception as e:  # BLE stacks raise many different error types
                self.last_error = f"{type(e).__name__}: {e}"
            finally:
                self.connected, self._client, self._last_seq = False, None, None
            if not self._stop.is_set():
                await asyncio.sleep(1.0)

    def _on_data(self, _sender, data):
        t_arr = time.perf_counter()
        pkt = decode_ble_packet(data)
        if pkt is None:
            self.n_bad += 1
            if len(data) == 20:
                self.last_error = "packets cut to 20 bytes: BLE MTU too small"
            return
        seq, t_dev, vals, flags = pkt
        if self._last_seq is not None:
            gap = (seq - self._last_seq - 1) & 0xFFFF
            if gap < 1000:
                self.n_dropped += gap
        self._last_seq = seq
        offset = self.clock.update(t_dev, t_arr)
        self._append(t_dev + offset, vals, t_arr, seq, flags)

    def _on_status(self, _sender, data):
        t_arr = time.perf_counter()
        text = bytes(data).decode(errors="ignore").strip()
        if text.startswith("PONG:"):
            k = text[5:]
            self._pong_times[k] = t_arr
            ev = self._pong_events.get(k)
            if ev:
                ev.set()
            return
        self.last_status = text
        if text.startswith("CAL:DONE"):
            self.calibration = text

    # -- commands --
    def send_command(self, cmd):
        """Write a text command ("CAL", "PING:<n>") to the glove. Returns True if sent."""
        import asyncio
        client, loop = self._client, self._loop
        if not (self.connected and client and loop):
            return False
        fut = asyncio.run_coroutine_threadsafe(
            client.write_gatt_char(BLE_CMD_UUID, cmd.encode(), response=False), loop)
        try:
            fut.result(timeout=2.0)
            return True
        except Exception as e:
            self.last_error = f"command failed: {e}"
            return False

    def measure_rtt(self, n=30):
        """PC -> glove -> PC round trips (PING/PONG). One-way latency ~ RTT / 2."""
        rtts = []
        for k in range(n):
            key = f"{k}-{random.randint(0, 9999)}"
            ev = threading.Event()
            self._pong_events[key] = ev
            t0 = time.perf_counter()
            if self.send_command(f"PING:{key}") and ev.wait(1.0):
                rtts.append((self._pong_times[key] - t0) * 1000)
            self._pong_events.pop(key, None)
            time.sleep(0.05)
        if not rtts:
            return None
        r = np.asarray(rtts)
        return dict(n=len(r), sent=n, min_ms=round(float(r.min()), 1),
                    median_ms=round(float(np.median(r)), 1),
                    p95_ms=round(float(np.percentile(r, 95)), 1), max_ms=round(float(r.max()), 1),
                    one_way_est_ms=round(float(np.median(r)) / 2, 1))


def make_glove_reader(args):
    if args.glove_transport == "ble":
        return BleGloveReader(args.glove_ble_name)
    return SerialGloveReader(args.glove_port, args.glove_baud)


# ----------------------------------------------------------------------------
# Row building
# ----------------------------------------------------------------------------
def make_header(log_other):
    coords = [f"{a}{i}" for i in range(N_LM) for a in "xyz"]
    header = ["frame", "t_sec", "detected", "hand_conf"] + coords
    if log_other:
        header += ["other_detected"] + [f"o_{c}" for c in coords]
    return header


def output_columns(log_other):
    """Final CSV columns: MediaPipe row + 11 glove values + sync audit column."""
    return make_header(log_other) + GLOVE_COLS + ["glove_dt_ms"]


def flatten(lms):
    """21 landmarks -> 63 values in x0,y0,z0,x1,y1,z1,... order."""
    return [v for p in lms.landmark for v in (p.x, p.y, p.z)]


class HandPicker:
    """Decides which detected hand is the gloved one, frame by frame.

    hand_mode "label":  MediaPipe's Left/Right label decides (frames are flipped before
                        processing, so the label is the signer's real hand). Fails when
                        the glove makes MediaPipe mislabel the hand.
    hand_mode "assume": the label is ignored. One hand visible -> it is the glove hand.
                        Two hands -> the one closest to where the glove hand was in the
                        last 0.5 s; if there is no recent position, the one on the
                        glove-hand side of the mirrored image (Right hand = right side).
    Counts how often MediaPipe's label disagreed, for the report.
    """

    JUMP = 0.30   # normalized distance: a lone hand this far from the glove hand = the other hand

    def __init__(self, args):
        self.mode, self.glove_hand = args.hand_mode, args.glove_hand
        self.prev, self.prev_t = None, -1e9
        self.reset_stats()

    def reset_stats(self):
        self.n_glove = 0
        self.n_label_mismatch = 0

    @staticmethod
    def _wrist(h):
        w = h[2].landmark[0]
        return w.x, w.y

    def pick(self, found, t):
        """found = HandTracker.process() output: list of (label, score, landmarks)."""
        if self.mode == "label":
            cands = [h for h in found if h[0] == self.glove_hand]
            glove = max(cands, key=lambda h: h[1]) if cands else None
        else:
            glove = None
            recent = self.prev is not None and t - self.prev_t < 0.5
            if len(found) == 1:
                h = found[0]
                if recent and math.dist(self._wrist(h), self.prev) > self.JUMP:
                    glove = None              # glove hand left the frame; this is the other hand
                else:
                    glove = h
            elif len(found) > 1:
                if recent:
                    glove = min(found, key=lambda h: math.dist(self._wrist(h), self.prev))
                else:
                    side = max if self.glove_hand == "Right" else min
                    glove = side(found, key=lambda h: self._wrist(h)[0])
        others = [h for h in found if h is not glove]
        other = max(others, key=lambda h: h[1]) if others else None
        if glove is not None:
            self.prev, self.prev_t = self._wrist(glove), t
            self.n_glove += 1
            self.n_label_mismatch += glove[0] != self.glove_hand
        return glove, other

    def stats(self):
        n = self.n_glove
        return dict(mode=self.mode,
                    mediapipe_label_mismatch_frac=round(self.n_label_mismatch / n, 4) if n else None)


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
# Synchronization
# ----------------------------------------------------------------------------
def sync_streams(rows, header, glove_df, t_rec0, args):
    """Join glove samples onto camera frames with pandas.merge_asof.

    Both streams are put on the same time axis (seconds since recording start).
    Each frame gets the glove sample closest in time ("nearest"), or the latest
    one at or before the frame ("backward", i.e. only past data, like live use).
    Frames with no glove sample within sync_tolerance_sec get NaN sensor values.
    """
    frames = pd.DataFrame(rows, columns=header)
    frames["t_sec"] = frames["t_sec"].astype("float64")

    glove = glove_df.copy()
    glove["glove_t_sec"] = (glove["t"] - t_rec0).astype("float64")
    glove = glove.drop(columns="t").sort_values("glove_t_sec")

    merged = pd.merge_asof(
        frames.sort_values("t_sec"),
        glove,
        left_on="t_sec",
        right_on="glove_t_sec",
        direction=args.sync_direction,
        tolerance=args.sync_tolerance_sec,
    )
    merged["glove_dt_ms"] = ((merged["glove_t_sec"] - merged["t_sec"]) * 1000).round(1)
    return merged[output_columns(args.log_other)]


# ----------------------------------------------------------------------------
# Camera / display helpers
# ----------------------------------------------------------------------------
class CameraStream:
    """Reads the webcam on its own thread and always hands out the NEWEST frame.

    Each frame is timestamped (perf_counter) the moment the driver delivers it, then
    mirrored. The main loop never blocks on the camera and never processes a stale,
    buffered frame; if processing ever falls behind, old frames are skipped and
    counted instead of piling up (which would delay everything and skew timestamps).
    """

    def __init__(self, args, width=640, height=480, fps=30):
        api = cv2.CAP_DSHOW if (args.camera_backend == "dshow" and os.name == "nt") else cv2.CAP_ANY
        self.cap = cv2.VideoCapture(args.camera, api)
        if not self.cap.isOpened() and api != cv2.CAP_ANY:
            self.cap = cv2.VideoCapture(args.camera)        # fall back to the default backend
        if not self.cap.isOpened():
            raise RuntimeError("Cannot open camera.")
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))  # 30 fps at 640x480 over USB
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.cap.set(cv2.CAP_PROP_FPS, fps)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.cond = threading.Condition()
        self.frame, self.t, self.seq, self.fails = None, 0.0, 0, 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        while not self._stop.is_set():
            ok, frame = self.cap.read()
            t = time.perf_counter()
            with self.cond:
                if ok:
                    self.frame, self.t, self.fails = cv2.flip(frame, 1), t, 0
                    self.seq += 1
                else:
                    self.fails += 1
                self.cond.notify_all()
            if not ok:
                time.sleep(0.005)

    def read(self, last_seq, timeout=2.0):
        """Wait for a frame newer than last_seq -> (frame, t_capture, seq, skipped)."""
        deadline = time.perf_counter() + timeout
        with self.cond:
            while self.seq <= last_seq:
                if self.fails >= MAX_READ_FAILS:
                    raise RuntimeError("Camera stopped returning frames.")
                remaining = deadline - time.perf_counter()
                if remaining <= 0:
                    raise RuntimeError("Camera stopped returning frames.")
                self.cond.wait(remaining)
            skipped = max(0, self.seq - last_seq - 1) if last_seq > 0 else 0
            return self.frame, self.t, self.seq, skipped

    def get(self, prop):
        return self.cap.get(prop)

    def release(self):
        self._stop.set()
        self._thread.join(timeout=1.0)
        self.cap.release()


def draw_hands(image, found):
    for _label, _score, lms in found:
        proto = landmark_pb2.NormalizedLandmarkList()
        proto.landmark.extend([landmark_pb2.NormalizedLandmark(x=p.x, y=p.y, z=p.z)
                               for p in lms.landmark])
        mp_drawing.draw_landmarks(
            image,
            proto,
            mp_hands.HAND_CONNECTIONS,
            mp_styles.get_default_hand_landmarks_style(),
            mp_styles.get_default_hand_connections_style(),
        )


def put(image, text, org, color=(255, 255, 255), scale=0.8, thick=2):
    cv2.putText(image, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), thick + 2, cv2.LINE_AA)
    cv2.putText(image, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thick, cv2.LINE_AA)


# ----------------------------------------------------------------------------
# Live dashboard (status lights + scrolling graphs of both input streams)
# ----------------------------------------------------------------------------
GREEN, YELLOW, RED, GREY = (80, 220, 80), (0, 210, 255), (60, 60, 255), (150, 150, 150)
# One colour per finger, shared by the vision and glove graphs so they can be compared
FINGER_COLORS = [(80, 80, 255), (0, 190, 255), (80, 220, 80), (255, 180, 60), (230, 90, 230)]
FINGER_NAMES = ["thumb", "index", "middle", "ring", "pinky"]
AXIS_COLORS = [(80, 80, 255), (80, 220, 80), (255, 160, 60)]   # x, y, z
FINGERTIPS = [4, 8, 12, 16, 20]


def finger_extension(lms):
    """Vision 'finger openness': fingertip-to-wrist distance / palm length (wrist->middle MCP).

    ~1.5-2 for a straight finger, smaller when it curls. Rough visual counterpart of
    the flex sensors, only for the live display (the raw landmarks are what get saved).
    """
    p = [(l.x, l.y) for l in lms.landmark]
    wx, wy = p[0]
    palm = math.hypot(p[9][0] - wx, p[9][1] - wy) or 1e-6
    return [math.hypot(p[i][0] - wx, p[i][1] - wy) / palm for i in FINGERTIPS]


class LiveView:
    """Builds the side panel: connection/sync status and live graphs of both streams."""

    W = 420  # panel width in pixels

    def __init__(self, args, glove_reader):
        self.args, self.glove = args, glove_reader
        self.frame_ts = deque(maxlen=120)
        self.vision = deque(maxlen=400)           # (t, [5 extension values] or None)
        self.hand_ok = False
        self.sync_ms = deque(maxlen=60)          # recent frame-vs-glove time offsets
        self.proc_ms = deque(maxlen=60)          # recent per-frame vision processing times
        self.skipped = deque(maxlen=60)          # camera frames skipped because we were busy
        self.canvas = None                       # reused output image (video + panel)
        self.panel = None                        # cached panel, redrawn at dashboard_hz
        self.panel_t = 0.0
        self.panel_mode = None

    def update(self, t_frame, glove_hand, proc_ms=None, skipped=0):
        """Call once per processed camera frame."""
        self.frame_ts.append(t_frame)
        self.hand_ok = glove_hand is not None
        self.vision.append((t_frame, finger_extension(glove_hand[2]) if glove_hand else None))
        last = self.glove.latest()
        if last is not None:
            self.sync_ms.append((t_frame - last[0]) * 1000)
        if proc_ms is not None:
            self.proc_ms.append(proc_ms)
        self.skipped.append(skipped)

    def compose(self, frame, mode=""):
        if not self.args.show_dashboard:
            return frame
        h, w = frame.shape[:2]
        if self.canvas is None or self.canvas.shape[0] != h:
            self.canvas = np.empty((h, w + self.W, 3), np.uint8)
        now = time.perf_counter()
        if (self.panel is None or now - self.panel_t >= 1.0 / self.args.dashboard_hz
                or mode.split()[0:1] != (self.panel_mode or "").split()[0:1]):
            self.panel = self._draw_panel(h, mode)
            self.panel_t, self.panel_mode = now, mode
        self.canvas[:, :w] = frame
        self.canvas[:, w:] = self.panel
        return self.canvas

    def _draw_panel(self, h, mode):
        panel = np.full((h, self.W, 3), 28, np.uint8)
        y = self._status(panel, mode)
        now = time.perf_counter()
        span = self.args.plot_span_sec
        g_t, g_v = self.glove.recent(span)
        v_t = [t for t, v in self.vision if t >= now - span]
        v_v = [v if v is not None else [np.nan] * 5 for t, v in self.vision if t >= now - span]
        v_v = np.asarray(v_v, dtype=float).reshape(-1, 5)
        plot_h = (h - y - 10) // 4
        y = self._plot(panel, y, plot_h, "CAMERA: finger openness", np.asarray(v_t), v_v,
                       FINGER_COLORS, ["T", "I", "M", "R", "P"], now, min_range=0.6, fmt="{:.2f}")
        y = self._plot(panel, y, plot_h, "GLOVE: flex F1-F5", g_t, g_v[:, 0:5],
                       FINGER_COLORS, ["F1", "F2", "F3", "F4", "F5"], now, min_range=60, fmt="{:.0f}")
        y = self._plot(panel, y, plot_h, "GLOVE: accel (m/s2)", g_t, g_v[:, 5:8],
                       AXIS_COLORS, ["X", "Y", "Z"], now, min_range=2.0, fmt="{:.1f}")
        self._plot(panel, y, plot_h, "GLOVE: gyro (rad/s)", g_t, g_v[:, 8:11],
                   AXIS_COLORS, ["X", "Y", "Z"], now, min_range=0.5, fmt="{:.2f}")
        return panel

    # -- status block --
    def _light(self, panel, y, color, label, detail):
        cv2.circle(panel, (16, y - 5), 7, color, -1, cv2.LINE_AA)
        cv2.putText(panel, label, (30, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (235, 235, 235), 1, cv2.LINE_AA)
        cv2.putText(panel, detail, (120, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)

    def _status(self, panel, mode):
        now = time.perf_counter()
        # camera
        ts = [t for t in self.frame_ts if t >= now - 1.0]
        fps = (len(ts) - 1) / (ts[-1] - ts[0]) if len(ts) > 2 else 0.0
        cam_c = GREEN if fps >= MIN_FPS else (YELLOW if fps > 0 else RED)
        self._light(panel, 22, cam_c, "CAMERA", f"{fps:4.1f} fps")
        self._light(panel, 44, GREEN if self.hand_ok else RED, "HAND",
                    f"{self.args.glove_hand} hand " + ("tracked" if self.hand_ok else "NOT FOUND"))
        # glove
        last = self.glove.latest()
        age = (now - last[0]) * 1000 if last else None
        hz = self.glove.rate_hz()
        if not self.glove.connected:
            g_c, g_txt = RED, f"DISCONNECTED ({self.glove.name})"
        elif age is None or age > 500:
            g_c, g_txt = RED, "connected, NO DATA"
        else:
            g_c = GREEN if hz >= MIN_GLOVE_HZ else YELLOW
            g_txt = f"{hz:3.0f} Hz   last {age:3.0f} ms ago"
        self._light(panel, 66, g_c, "GLOVE", g_txt)
        # IMU (all-zero accel+gyro = MPU missing / no-MPU firmware)
        _, v = self.glove.recent(1.0)
        if len(v) == 0:
            imu_c, imu_txt = GREY, "-"
        elif np.all(v[:, 5:11] == 0):
            imu_c, imu_txt = YELLOW, "no data (all zeros: MPU missing?)"
        else:
            imu_c, imu_txt = GREEN, "OK"
        self._light(panel, 88, imu_c, "IMU", imu_txt)
        # sync: how old the newest glove sample is when each frame arrives
        if self.sync_ms and g_c != RED:
            worst = max(abs(x) for x in self.sync_ms)
            tol = self.args.sync_tolerance_sec * 1000
            s_c = GREEN if worst <= tol else (YELLOW if worst <= 100 else RED)
            s_txt = f"frame-glove gap {np.median(self.sync_ms):3.0f} ms (max {worst:.0f})"
        else:
            s_c, s_txt = RED, "no glove data"
        self._light(panel, 110, s_c, "SYNC", s_txt)
        # speed: per-frame vision processing time vs the 20 ms target and 33 ms frame budget
        if self.proc_ms:
            med, worst = float(np.median(self.proc_ms)), max(self.proc_ms)
            p_c = GREEN if med <= MAX_VISION_MS else (YELLOW if med <= VISION_BUDGET_MS else RED)
            skip = sum(self.skipped)
            p_txt = (f"{med:4.1f} ms/frame (max {worst:.0f})  headroom {VISION_BUDGET_MS - med:3.0f} ms"
                     + (f"  {skip} skipped" if skip else ""))
        else:
            p_c, p_txt = GREY, "-"
        self._light(panel, 132, p_c, "SPEED", p_txt)
        if mode:
            cv2.putText(panel, mode, (16, 156), cv2.FONT_HERSHEY_SIMPLEX, 0.5, YELLOW, 1, cv2.LINE_AA)
        return 164

    # -- one scrolling graph --
    def _plot(self, panel, y0, h, title, ts, vals, colors, labels, now, min_range, fmt):
        x0, x1 = 10, self.W - 10
        top, bot = y0 + 30, y0 + h - 4
        cv2.rectangle(panel, (x0, top), (x1, bot), (60, 60, 60), 1)
        cv2.putText(panel, title, (x0, y0 + 12), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (220, 220, 220), 1, cv2.LINE_AA)
        # live value per series, in its colour
        cx = x0
        for i, (lab, col) in enumerate(zip(labels, colors)):
            cur = vals[-1, i] if len(vals) and not np.isnan(vals[-1, i]) else None
            txt = f"{lab}:{fmt.format(cur)}" if cur is not None else f"{lab}:--"
            cv2.putText(panel, txt, (cx, y0 + 26), cv2.FONT_HERSHEY_SIMPLEX, 0.38, col, 1, cv2.LINE_AA)
            cx += (x1 - x0) // len(labels)
        if len(ts) < 2 or np.all(np.isnan(vals)):
            cv2.putText(panel, "no data", (x0 + 8, (top + bot) // 2), cv2.FONT_HERSHEY_SIMPLEX,
                        0.45, GREY, 1, cv2.LINE_AA)
            return y0 + h
        lo, hi = np.nanmin(vals), np.nanmax(vals)
        if hi - lo < min_range:  # keep sensor noise from being blown up to full height
            mid = (hi + lo) / 2
            lo, hi = mid - min_range / 2, mid + min_range / 2
        pad = (hi - lo) * 0.08
        lo, hi = lo - pad, hi + pad
        span = self.args.plot_span_sec
        xs = x0 + (np.asarray(ts) - (now - span)) / span * (x1 - x0)
        for i, col in enumerate(colors):
            ys = bot - (vals[:, i] - lo) / (hi - lo) * (bot - top)
            seg = []
            for x, yv in zip(xs, ys):
                if np.isnan(yv):          # hand lost: break the line
                    if len(seg) > 1:
                        cv2.polylines(panel, [np.int32(seg)], False, col, 1, cv2.LINE_AA)
                    seg = []
                else:
                    seg.append((x, yv))
            if len(seg) > 1:
                cv2.polylines(panel, [np.int32(seg)], False, col, 1, cv2.LINE_AA)
        return y0 + h


# ----------------------------------------------------------------------------
# Session phases
# ----------------------------------------------------------------------------
def process_frame(cam, hands, picker, view, last_seq):
    """Newest camera frame -> MediaPipe -> glove/other hand. Returns a dict.

    proc_ms = capture timestamp -> landmarks ready (the per-frame vision latency).
    """
    frame, t, seq, skipped = cam.read(last_seq)
    # (no copy needed: the camera thread stores every new frame in a new array)
    found = hands.process(frame, t)
    t_done = time.perf_counter()
    glove, other = picker.pick(found, t)
    draw_hands(frame, found)
    proc_ms = (t_done - t) * 1000
    view.update(t, glove, proc_ms, skipped)
    return dict(frame=frame, t=t, seq=seq, skipped=skipped, glove=glove, other=other,
                proc_ms=proc_ms)


def flex_cal_valid(cal, glove_reader):
    """The session's flex calibration still applies: same connection, glove not re-zeroed since."""
    return (cal is not None and cal["connection_id"] == glove_reader.connection_id
            and cal["glove_status"] == glove_reader.calibration)


def hold_pose(cam, hands, picker, view, glove_reader, prompt, seq):
    """Show the prompt for CAL_HOLD_SEC, then return the last CAL_AVG_SEC of glove samples."""
    t_end = time.perf_counter() + aisl_norm.CAL_HOLD_SEC
    while True:
        f = process_frame(cam, hands, picker, view, seq)
        seq, frame = f["seq"], f["frame"]
        left = t_end - time.perf_counter()
        if left <= 0:
            break
        put(frame, prompt, (20, 60), (0, 255, 255), 0.8, 2)
        put(frame, f"hold still: {left:.1f} s", (20, 100), (0, 255, 255), 0.7, 2)
        cv2.imshow(WIN, view.compose(frame, "CALIBRATING GLOVE"))
        cv2.waitKey(1)
    _, v = glove_reader.recent(aisl_norm.CAL_AVG_SEC)
    return v.tolist(), seq


def run_flex_calibration(cam, hands, picker, glove_reader, view, seq=0):
    """Two-point flex calibration: open hand (also re-zeroes the glove), then a tight fist.

    Returns the calibration dict (open/closed means + bookkeeping) or None if it failed.
    """
    if not glove_reader.send_command("CAL"):
        print("Glove CAL command not available (Bluetooth Classic firmware): press BOOT on the ESP32 "
              "now, with the hand open and flat.")
    open_s, seq = hold_pose(cam, hands, picker, view, glove_reader,
                            "OPEN hand: fingers straight, flat, still", seq)
    closed_s, seq = hold_pose(cam, hands, picker, view, glove_reader,
                              "Make a TIGHT FIST and hold it", seq)
    try:
        cal = aisl_norm.flex_calibration(open_s, closed_s)
    except ValueError as e:
        print(f"Glove calibration FAILED: {e}")
        return None
    rng_txt = " ".join(f"F{i + 1}:{cal['closed'][i] - cal['open'][i]:+.0f}" for i in range(5))
    print(f"Glove calibrated (fist - open, ADC counts): {rng_txt}")
    return dict(cal, time=datetime.now().isoformat(timespec="seconds"),
                method="two-point: open hand (glove CAL zero) then fist; mean of the last "
                       f"{aisl_norm.CAL_AVG_SEC:g} s of a {aisl_norm.CAL_HOLD_SEC:g} s hold each",
                connection_id=glove_reader.connection_id, glove_status=glove_reader.calibration)


def wait_for_start(cam, hands, picker, glove_reader, view, args, banner, session_info):
    """Live preview with landmarks + dashboard so the signer can get ready.

    The glove's two-point calibration (C) must be valid before a take can start.
    """
    seq = 0
    while True:
        f = process_frame(cam, hands, picker, view, seq)
        seq, frame = f["seq"], f["frame"]
        put(frame, banner, (20, 35), scale=0.7)
        put(frame, "SPACE = start take   C = calibrate glove (open + fist)   ESC = quit", (20, 70),
            (0, 255, 255), 0.55, 1)
        glove_ok = glove_reader.status_text()[0]
        cal_ok = flex_cal_valid(session_info.get("flex_calibration"), glove_reader)
        if not glove_ok:
            put(frame, "Waiting for glove data...", (20, 105), (0, 0, 255), 0.6, 2)
        elif not cal_ok:
            put(frame, "Press C to calibrate the glove (open hand, then fist)", (20, 105),
                (0, 0, 255), 0.6, 2)
        elif f["glove"] is None:
            put(frame, "Show the gloved hand to the camera", (20, 105), (0, 165, 255), 0.6, 2)
        cv2.imshow(WIN, view.compose(frame, "PREVIEW (not recording)"))
        key = cv2.waitKey(1) & 0xFF
        if key in (ord("c"), ord("C")) and glove_ok:
            session_info["flex_calibration"] = run_flex_calibration(cam, hands, picker, glove_reader, view)
            seq = 0
        if key == 32 and glove_ok and cal_ok:
            return True
        if key == 27:
            return False


def record_take(cam, hands, picker, glove_reader, view, args):
    """Countdown (tracker keeps running) then a fixed-duration recording.

    The glove thread runs the whole time; after the loop, its buffer is sliced
    to this take's window on the same perf_counter clock.

    Returns (rows, glove_df, perf, last_frame, t_rec0, t_end); rows is None if the
    take was aborted with ESC. perf = per-frame (proc_ms, skipped) while recording.
    """
    rows, perf, last_frame = [], [], None
    frame_idx, seq = 0, 0
    t_rec0 = time.perf_counter() + args.countdown  # recording clock starts here
    picker.reset_stats()
    while True:
        f = process_frame(cam, hands, picker, view, seq)
        seq, frame, t = f["seq"], f["frame"], f["t"]
        t_rec = t - t_rec0
        if t_rec >= args.record_sec:  # deadline checked before storing the frame
            # small margin on both sides so the first/last frame can find a neighbour
            margin = args.sync_tolerance_sec
            glove_df = glove_reader.window(t_rec0 - margin, t + margin)
            return rows, glove_df, perf, last_frame.copy(), t_rec0, t

        if t_rec < 0:
            picker.reset_stats()   # only count handedness stats during the recording
            put(frame, f"Get ready: {int(-t_rec) + 1}", (20, 60), (0, 0, 255), 1.5, 3)
            mode = "COUNTDOWN"
        else:
            rows.append(build_row(frame_idx, t_rec, f["glove"], f["other"], args.log_other))
            perf.append((f["proc_ms"], f["skipped"] if frame_idx else 0))
            frame_idx += 1
            cv2.circle(frame, (frame.shape[1] - 30, 30), 12, (0, 0, 255), -1, cv2.LINE_AA)
            put(frame, f"REC {args.record_sec - t_rec:.1f}s", (20, 50), (0, 255, 0), 1.0, 2)
            if f["glove"] is None:
                put(frame, "gloved hand NOT tracked", (20, 85), (0, 0, 255), 0.7, 2)
            mode = f"RECORDING  {args.record_sec - t_rec:.1f}s left"

        last_frame = view.compose(frame, mode)
        cv2.imshow(WIN, last_frame)
        if cv2.waitKey(1) & 0xFF == 27:
            return None, None, None, None, t_rec0, t


def quality(df, glove_df, t_rec0, args, perf=None, hand_stats=None):
    """Camera + glove + sync + speed quality stats for one take (df = merged output)."""
    n = len(df)
    if n < 2:
        return dict(n_frames=n, fps=0.0, detected_frac=0.0, max_gap_sec=None,
                    glove_samples=0, glove_hz=0.0, glove_matched_frac=0.0,
                    glove_max_gap_sec=None, glove_max_abs_dt_ms=None,
                    glove_packets_dropped=None, glove_delay_above_min=None,
                    vision_latency=None, hand_picking=hand_stats,
                    warnings=["too few frames"])
    ts = df["t_sec"].tolist()
    span = ts[-1] - ts[0]
    fps = (n - 1) / span if span > 0 else 0.0
    max_gap = float(max(b - a for a, b in zip(ts, ts[1:])))
    det = float(df["detected"].mean())

    # glove stream inside the recording window only
    g_t = (glove_df["t"] - t_rec0).tolist() if len(glove_df) else []
    g_in = [x for x in g_t if 0 <= x < args.record_sec]
    glove_hz = len(g_in) / args.record_sec
    glove_gap = float(max(b - a for a, b in zip(g_in, g_in[1:]))) if len(g_in) > 1 else None
    matched = float(df["flex1"].notna().mean())
    abs_dt = df["glove_dt_ms"].abs()
    max_dt = float(abs_dt.max()) if abs_dt.notna().any() else None

    # transport: packets lost (BLE seq gaps) and per-packet radio delay
    in_take = glove_df[(glove_df["t"] - t_rec0 >= 0) & (glove_df["t"] - t_rec0 < args.record_sec)] \
        if len(glove_df) else glove_df
    dropped, delay = None, None
    if len(in_take) > 1 and "seq" in in_take and (in_take["seq"] >= 0).all():
        gaps = (in_take["seq"].diff().dropna().astype(int) - 1) % 65536
        dropped = int(gaps[gaps < 1000].sum())
        # delay above the fastest packet (t_sync is the minimum-delay arrival time)
        d = (in_take["t_arrival"] - in_take["t"]) * 1000
        delay = dict(median_ms=round(float(d.median()), 1), p95_ms=round(float(d.quantile(0.95)), 1),
                     max_ms=round(float(d.max()), 1))

    warnings = []
    if fps < MIN_FPS:
        warnings.append(f"low fps ({fps:.1f})")
    if det < MIN_DETECTED:
        warnings.append(f"low detection ({det:.0%})")
    if max_gap > MAX_GAP_SEC:
        warnings.append(f"gap of {max_gap * 1000:.0f} ms between frames")
    if glove_hz < MIN_GLOVE_HZ:
        warnings.append(f"low glove rate ({glove_hz:.0f} Hz)")
    if matched < MIN_GLOVE_MATCHED:
        warnings.append(f"only {matched:.0%} of frames have glove data")
    if glove_gap is not None and glove_gap > MAX_GLOVE_GAP_SEC:
        warnings.append(f"glove silent for {glove_gap * 1000:.0f} ms")
    if dropped:
        warnings.append(f"{dropped} glove packets lost")

    # vision speed: capture -> landmarks ready, per recorded frame
    vision = None
    if perf:
        pm = np.asarray([p[0] for p in perf])
        vision = dict(n_frames=len(pm), median_ms=round(float(np.median(pm)), 1),
                      p95_ms=round(float(np.percentile(pm, 95)), 1), max_ms=round(float(pm.max()), 1),
                      within_20ms_frac=round(float((pm <= MAX_VISION_MS).mean()), 4),
                      camera_frames_skipped=int(sum(p[1] for p in perf)))
        if vision["median_ms"] > MAX_VISION_MS:
            warnings.append(f"vision {vision['median_ms']:.0f} ms/frame (> {MAX_VISION_MS:.0f})")
    return dict(n_frames=n, fps=round(fps, 2), detected_frac=round(det, 4),
                max_gap_sec=round(max_gap, 4),
                glove_samples=len(g_in), glove_hz=round(glove_hz, 1),
                glove_matched_frac=round(matched, 4),
                glove_max_gap_sec=round(glove_gap, 4) if glove_gap is not None else None,
                glove_max_abs_dt_ms=max_dt,
                glove_packets_dropped=dropped,
                glove_delay_above_min=delay,
                vision_latency=vision,
                hand_picking=hand_stats,
                warnings=warnings)


def review(last_frame, q, banner):
    """Show the last frame with the quality summary; return keep/redo/quit."""
    frame = last_frame.copy()
    bad = bool(q["warnings"])
    color = (0, 0, 255) if bad else (0, 255, 0)
    put(frame, banner, (20, 35), scale=0.7)
    put(frame, f"{q['n_frames']} frames, {q['fps']:.1f} fps, {q['detected_frac']:.0%} detected",
        (20, 70), color, 0.7, 2)
    vis = q.get("vision_latency") or {}
    put(frame, f"glove {q['glove_hz']:.0f} Hz, {q['glove_matched_frac']:.0%} synced"
        + (f" | vision {vis['median_ms']:.0f} ms/frame" if vis else ""),
        (20, 100), color, 0.7, 2)
    for i, w in enumerate(q["warnings"]):
        put(frame, "WARNING: " + w, (20, 135 + 30 * i), (0, 0, 255), 0.6, 2)
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


def save_take(args, cap, hands, glove_reader, session_info, df, q, sign, rep, t_rec0, t_end):
    cal = session_info["flex_calibration"]
    os.makedirs(os.path.join(args.out, args.signer), exist_ok=True)
    csv_path = take_path(args, sign, rep, ".csv")
    df.to_csv(csv_path, index=False)
    meta = {
        "platform": "desktop-python",
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
        "glove": {
            "transport": glove_reader.transport,
            "device": glove_reader.name,
            "ble_mtu": glove_reader.mtu,
            "columns": GLOVE_COLS,
            "timestamp": (
                "ESP32 millis() per sample, mapped to PC time.perf_counter via the minimum "
                "(arrival - device time) over a 10 s sliding window"
                if glove_reader.transport == "ble" else
                "PC time.perf_counter at line arrival over Bluetooth Classic"),
            "units": "flex: ADC counts minus calibration baseline; acc: m/s^2; gyro: rad/s",
            "sync_method": "pandas.merge_asof",
            "sync_direction": args.sync_direction,
            "sync_tolerance_sec": args.sync_tolerance_sec,
            "calibration": glove_reader.calibration,
            "round_trip_latency_session": session_info.get("rtt"),
            "packets_dropped_session": glove_reader.n_dropped,
            "malformed_packets_session": glove_reader.n_bad,
            "last_status_line": glove_reader.last_status,
        },
        # the image MediaPipe saw (normalization needs its size): mirrored, upright
        "mediapipe_input": {"width": hands.size[0], "height": hands.size[1],
                            "rotation_degrees": 0, "mirrored": True},
        "feature_spec_version": aisl_norm.SPEC_VERSION,
        # two-point flex calibration of this session (normalize_takes.py needs it)
        "flex_calibration": {k: cal[k] for k in ("open", "closed", "time", "method")},
        "mediapipe_version": getattr(mp, "__version__", "unknown"),
        "mediapipe_settings": mp_settings(hands.cfg, hands.model_sha256),
        "hand_mode": args.hand_mode,
        "camera_backend": args.camera_backend,
        "opencv_version": cv2.__version__,
        "pandas_version": pd.__version__,
        "columns": len(df.columns),
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
    mp_cfg = aisl_norm.load_mp_config()
    aisl_norm.load_model(mp_cfg, BASE_DIR)   # fail now (not after the glove connects) if the model differs

    glove_reader = make_glove_reader(args)
    print(f"Connecting to glove '{glove_reader.name}' over {glove_reader.transport} "
          f"(can take ~5-15 s)...")
    if not glove_reader.start(wait_sec=25.0 if args.glove_transport == "ble" else 15.0):
        glove_reader.stop()
        hint = ("glove powered on with hand_sign_glove_ble firmware; AISL_Glove NOT paired in "
                "Windows Bluetooth settings (remove it there); no phone app connected to it; "
                "then press EN on the ESP32 and retry. Run ble_check.py for details"
                if args.glove_transport == "ble" else
                "glove powered on, paired, correct Outgoing COM port, Arduino Serial Monitor closed")
        sys.exit(f"No glove data. Check: {hint}. Last error: {glove_reader.last_error or 'none'}")
    time.sleep(1.0)
    print(f"Glove OK: {glove_reader.rate_hz():.0f} Hz"
          + (f", BLE MTU {glove_reader.mtu}" if glove_reader.mtu else "")
          + (f"  (glove says: {glove_reader.last_status})" if glove_reader.last_status else ""))
    if glove_reader.rate_hz() < MIN_GLOVE_HZ:
        print(f"  WARNING: glove rate is below {MIN_GLOVE_HZ:.0f} Hz. "
              f"Is FRAME_PERIOD_MS = 20 in the firmware?")
    session_info = {}
    if args.glove_transport == "ble":
        print("Measuring glove round-trip latency (30 pings)...")
        session_info["rtt"] = glove_reader.measure_rtt(30)
        print(f"  RTT: {session_info['rtt']}")

    try:
        cap = CameraStream(args)
    except RuntimeError as e:
        glove_reader.stop()
        sys.exit(str(e))
    print(f"Camera reports {cap.get(cv2.CAP_PROP_FRAME_WIDTH):.0f}x"
          f"{cap.get(cv2.CAP_PROP_FRAME_HEIGHT):.0f} @ {cap.get(cv2.CAP_PROP_FPS):.0f} fps "
          f"(requested 640x480 @ 30; the measured fps per take is what counts)")

    header = make_header(args.log_other)
    view = LiveView(args, glove_reader)
    picker = HandPicker(args)
    plan = build_plan(args)
    if not plan:
        print("Nothing left to record for these signs.")
        cap.release()
        glove_reader.stop()
        return
    print(f"{len(plan)} takes planned for {args.signer}. "
          f"Output: {len(output_columns(args.log_other))} columns per frame.")

    quit_all = False
    try:
        with HandTracker(mp_cfg) as hands:
            for i, sign in enumerate(plan, 1):
                if quit_all:
                    break
                while True:
                    rep = next_rep(args, sign)
                    banner = f"[{i}/{len(plan)}] {sign}  (rep {rep}/{args.reps})"
                    if not wait_for_start(cap, hands, picker, glove_reader, view, args, banner, session_info):
                        quit_all = True
                        break
                    rows, glove_df, perf, last_frame, t_rec0, t_end = record_take(
                        cap, hands, picker, glove_reader, view, args)
                    if rows is None:  # ESC mid-take: discard, back to the start screen
                        print("Take aborted.")
                        continue
                    df = sync_streams(rows, header, glove_df, t_rec0, args)
                    q = quality(df, glove_df, t_rec0, args, perf, picker.stats())
                    print(f"{banner}: {q['n_frames']} frames, {q['fps']:.1f} fps, "
                          f"{q['detected_frac']:.0%} detected | glove {q['glove_hz']:.0f} Hz, "
                          f"{q['glove_matched_frac']:.0%} synced, "
                          f"max dt {q['glove_max_abs_dt_ms']} ms | vision "
                          f"{(q['vision_latency'] or {}).get('median_ms')} ms/frame"
                          + (f"  WARN: {'; '.join(q['warnings'])}" if q["warnings"] else ""))
                    decision = review(last_frame, q, banner)
                    if decision == "keep":
                        path = save_take(args, cap, hands, glove_reader, session_info, df, q, sign,
                                         rep, t_rec0, t_end)
                        print(f"  saved {path}")
                        break
                    if decision == "quit":
                        quit_all = True
                        break
                    print("  discarded, redoing.")
    finally:
        cap.release()
        cv2.destroyAllWindows()
        glove_reader.stop()


if __name__ == "__main__":
    main()
