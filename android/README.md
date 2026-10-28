# AISL-A Android app (Kotlin)

Phone version of `MediaPipe/fslRecorder.py`: CameraX + MediaPipe Hands + the BLE glove,
4 s takes after a 3 s countdown, synced and quality-checked the same way, saved in the
**same 79-column CSV** (glove hand only; signs are one-handed) plus the normalized features. Live sign recognition comes later,
once the CNN-BiLSTM is trained (it will consume `Normalizer` output).

## Open and run

1. Install Android Studio (bundles JDK 21 + Android SDK). Open the `android/` folder.
   It downloads Gradle 8.11.1 / AGP 8.7.3 / Kotlin 2.1.0 on first sync.
2. Keep the folder layout: the build bundles `../MediaPipe/hand_landmarker.task` and
   `../shared/mediapipe_config.json` (no copies in the app, so they can't drift).
3. Run the parity tests: Gradle panel → `core › Tasks › verification › test`
   (or `gradlew :core:test`). All must pass before recording with the app.
4. Run `app` on the phone (USB debugging on). Grant camera + Bluetooth (Nearby devices).
   On Android 11 and older, Location must also be ON for BLE scanning.
5. The glove must run `hand_sign_glove_ble` firmware and must not be connected to the PC
   at the same time (BLE allows one central).

Takes are saved to `Android/data/com.aisla.app/files/data/<signer>/` (raw, same names as the
desktop) and `.../files/data_norm/<signer>/` (normalized). Copy them over USB.

## What is guaranteed to match the desktop recorder

| Piece | How it's kept identical | Checked by |
|---|---|---|
| MediaPipe model | Same `hand_landmarker.task` bytes, sha256 checked at start on both sides | `HandTracker` / `aisl_norm.load_model` refuse to start on mismatch |
| MediaPipe version + settings | `shared/mediapipe_config.json` read by both; app checks its AAR version | start-up check |
| API / mode | Tasks HandLandmarker, VIDEO mode (tracking), CPU, 2 hands, all thresholds 0.4 | config |
| Image MediaPipe sees | Upright + mirrored (CameraX frames rotated, then flipped like `cv2.flip(frame, 1)`), both lenses, no resampling | — |
| Left/Right label | Tasks labels are the reverse of the old API; both sides swap them back (`invert_handedness_label`) | `mediapipe_label_mismatch_frac` in every take JSON |
| Hand picking, rows, rounding | Ported line by line (`HandPicker`, `FrameRow.build`, Python `round`) | `GoldenTest` |
| Glove decode + clock mapping | `GlovePacket`, `ClockMapper` | `GoldenTest` |
| Sync (`pandas.merge_asof`, nearest, 40 ms) | `AsofJoin` = pandas' own algorithm, incl. tie → earlier sample | `GoldenTest` (vs pandas) |
| CSV text | `PyFormat.pyRepr` = Python `repr` (pandas writes the same) | `GoldenTest` (byte-equal lines) |
| Quality gates + warnings | `Quality` (numpy median/percentile, Python formatting) | `GoldenTest` |
| Normalized features | `Normalizer.kt` = `aisl_norm.py` | `GoldenTest` (bit-equal) |

`shared/golden/` is generated from the real Python code: `venv\Scripts\python.exe make_golden.py`
(in `MediaPipe/`). Re-run it and the Kotlin tests whenever either side changes.

## The normalization (spec v3, `MediaPipe/aisl_norm.py` = `core/.../Normalizer.kt`)

Webcam and phone landmarks are not comparable raw: x is divided by the image width and y
by the height (640x480 landscape vs 480x640 portrait), z is on the x scale, and hand size
depends on distance and lens. Per hand:

1. pixels: `X = x*W, Y = y*H, Z = z*W`
2. palm size `s` = mean 3D distance wrist → MCPs 5, 9, 13, 17
3. shape = `(P_i − P_0) / s` (63 values): independent of resolution, aspect ratio, distance
4. position = `(X_0 − W/2, Y_0 − H/2) / min(W, H)` (2 values)

Plus a valid flag per hand and for the glove: flex1..5 normalized with the session's **two-point
calibration** (open hand, then fist: `(v − open) / (closed − open)`, ~0 open, ~1 fist) and the 6
IMU values as recorded. Without a calibration the glove group is invalid.
Then each stream is resampled to a fixed **30 Hz × 4 s = 120-step** grid (linear between
valid frames ≤ 100 ms apart, else nearest within 50 ms, else invalid), so 10 fps, 24 fps
and 30 fps takes all give the same shape. Output: 79 columns (`t`, `g_valid`, 65 hand values, `glove_valid`, 11 glove values).
Spec v2 (2026-10-28) dropped the other hand (v1 had 145 columns); v3 added the flex calibration.

**Glove calibration in the app:** press **Cal**, hold the hand open and flat (3 s), then a tight
fist (3 s). The FLEXCAL light must be green before Start take works; it turns red again if the
glove reconnects or re-zeroes (BOOT button / reboot).

Proven in `make_golden.py`: the same webcam take re-expressed as a portrait phone frame gives
hand-shape features equal to within 4e-16.

Not removable by normalization: where the signer stands in the frame (affects the 2 position
values; keep framing similar: upper body, centered), lighting/blur, and lens distortion.

## Measured on device (Xiaomi Pad 6, 2026-10-28)

- Same 640x480 frame through the app's MediaPipe (CPU) and the PC's (`compare_bench.py`):
  landmarks within **0.01 px**, same label. The model really is identical across devices.
- GPU delegate: faster (~51 vs ~76 ms in the test) but landmarks up to **23 px** off and a
  flipped label vs CPU/PC. Not used; data collection stays on CPU.
- Live CPU timing: convert 3.5 ms + MediaPipe ~45 ms per frame → ~20 fps on this tablet
  (SO1 20 ms target not met here). Takes still resample to 30 Hz.
- The old lite model finds no hand in a gloved test frame that the Tasks model detects.
- Handedness on gloved hands is unreliable (legacy full model 0.58 confidence); check
  `mediapipe_label_mismatch_frac` on real takes before trusting `invert_handedness_label`.

The **GPU test** button repeats this: it saves `files/bench/` (frame.png, cpu.csv, gpu.csv);
`adb pull /sdcard/Android/data/com.aisla.app/files/bench bench` then
`venv\Scripts\python.exe compare_bench.py bench` in `MediaPipe/`.

## Known differences / open items

- **Old desktop takes used a different model.** Everything recorded before this change used
  `mp.solutions.hands` lite (`model_complexity=0`). The Android Tasks API cannot load the lite
  model (it lacks required metadata), so both sides now use the full `hand_landmarker.task`.
  Re-record S01 with the updated `fslRecorder.py` before training.
- **Speed:** on this PC the full model took ~54 ms/frame vs ~36 ms for lite (same image,
  same machine), so expect the desktop SPEED light to read higher than before. Check the SO1
  20 ms target on the recording laptop and on the phone (`vision_latency` in each JSON).
- **Frame timestamps:** the phone uses the sensor exposure timestamp (exact). The desktop
  stamps frames when OpenCV returns them, which is later by the webcam's own latency
  (unmeasured, typically tens of ms). The glove sample matched to a desktop frame is
  therefore slightly "newer" than the picture. Worth measuring once (e.g. tap the glove on
  the table in view and compare the IMU spike frame vs the video frame).
- MediaPipe 0.10.14 native libs are not 16 KB page aligned; fine on current phones (POCO X6
  Pro included). If you upgrade, bump `mediapipe_version` in the config, `mediapipeVersion`
  in `app/build.gradle.kts` and `pip install mediapipe==<same>` together.
- Glove hand assumed right-handed signers; left-handed signers are not mirrored.
