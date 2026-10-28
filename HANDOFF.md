# AISL-A — Project Handoff (read this first)

> **For any AI or person picking this up (Claude, Codex, Sol, teammates):** this file is the
> single source of truth for what exists, how to run it, what was decided and why, and what's
> next. **Update it whenever you make progress** (status, decisions, changelog at the bottom).
> Keep it short and factual; dates as YYYY-MM-DD.

Last updated: 2026-10-28

---

## 1. Project in one paragraph

Undergrad thesis (group AISL-3-2526-C5, adviser Dr. Melvin K. Cabatuan, team lead JP = Juan
Porferio S. Napiza): **AISL-A**, a wearable-vision fusion system for real-time **Filipino Sign
Language (FSL)** recognition. Inputs: a camera running **MediaPipe Hands** (21 landmarks × x,y,z)
plus a **sensor glove** on the signing (right) hand: ESP32 + 5 flex sensors + MPU6050 IMU,
streaming over **BLE at 50 Hz**. Model (to be trained): 1D-CNN-BiLSTM (after Lu et al., 2023) →
gloss → fine-tuned T5 gloss-to-text. **Scope limitation: one-handed signs only.** End product is
like "Google Translate for signers": the user holds the phone in one hand (front camera) and
signs with the gloved hand. JP prefers casual, direct replies and confident decisions.

## 2. Repository map (`THESIS/`, git, branch `android-app`)

| Path | What |
|---|---|
| `MediaPipe/fslRecorder.py` | Desktop take recorder (webcam + MediaPipe + BLE glove). 3 s countdown, 4 s takes, CSV + JSON per take. Run in the venv. |
| `MediaPipe/aisl_norm.py` | Shared config loader + **cross-device normalization** (spec v3). No pandas/numpy. |
| `MediaPipe/normalize_takes.py` | `data/<signer>/*.csv` → `data_norm/<signer>/*_norm.csv` (training input). |
| `MediaPipe/make_golden.py` | Generates `shared/golden/` from the real Python/pandas code (reference for Kotlin tests). |
| `MediaPipe/compare_bench.py` | Runs PC MediaPipe on a frame saved by the app's GPU test and compares landmarks. |
| `MediaPipe/ble_check.py` | BLE glove diagnostics (desktop). |
| `MediaPipe/hand_landmarker.task` | **The** MediaPipe model (sha256 `fbc2a300…7cde1`). Used by desktop AND app. |
| `MediaPipe/data/S01/` | Pilot takes (old model — see §7). |
| `shared/mediapipe_config.json` | MediaPipe settings for BOTH platforms (version, model hash, thresholds, `num_hands`). |
| `shared/golden/` | Reference outputs; Kotlin `GoldenTest` must reproduce them bit for bit. |
| `android/` | Kotlin app: `:core` (pure Kotlin, parity-tested) + `:app` (CameraX, MediaPipe Tasks, BLE, UI). See `android/README.md`. |
| `hand_sign_glove_ble/hand_sign_glove_ble.ino` | **Current glove firmware** (BLE, 50 Hz, binary packets with device timestamp). |
| `hand_sign_glove_code/` | Old Bluetooth Classic firmware (text lines). Not used by the app. |
| `Glove kicad/` | Schematic (`glove/glove.kicad_sch`) + STEP models of ESP32-DevKitC-32D and MPU6050 module. PCB not laid out. |

Outside the repo (`D:\College\Thesis\`): manuscripts, progress reports, ethics forms, diagrams
(incl. `Diagrams and Mockups/AISL-A App — Wireframe Mockup.png`).

## 3. How to run things

**Desktop recorder** (Windows, VS Code): edit the `Config` block in `fslRecorder.py`
(signer, signs, reps), run with `MediaPipe\venv\Scripts\python.exe` (mediapipe 0.10.14, pandas,
bleak). Glove must not be connected to a phone at the same time (BLE = one central).

**Normalize takes** (any Python, no pandas): `python MediaPipe/normalize_takes.py`.

**Golden files** (after changing `aisl_norm.py` or recorder sync/quality code):
`cd MediaPipe; venv\Scripts\python.exe make_golden.py`, then run the Kotlin tests.

**Android app** — open `android/` in Android Studio (Gradle JVM = 21; the bundled 25 is too new
for Gradle 8.11.1). From a terminal (what the AI uses):
```bash
cd THESIS/android
export JAVA_HOME="$(cygpath -w ~/.jdks/jbr-21.0.11)"
G=$(ls -d ~/.gradle/wrapper/dists/gradle-8.11.1-bin/*/gradle-8.11.1 | head -1)
"$G/bin/gradle" --console=plain :core:test :app:assembleDebug
"$LOCALAPPDATA/Android/Sdk/platform-tools/adb.exe" install -r app/build/outputs/apk/debug/app-debug.apk
```
(No `gradlew` scripts in the repo; Android Studio uses `gradle/wrapper/gradle-wrapper.properties`.)
In Git Bash, prefix adb commands that take `/sdcard/...` paths with `MSYS_NO_PATHCONV=1`.

App files on the device: `Android/data/com.aisla.app/files/data/<signer>/` (raw take CSV + JSON),
`files/data_norm/<signer>/` (normalized), `files/bench/` (GPU test).
Xiaomi devices: Developer options → enable **Install via USB** or installs fail.

## 4. Key decisions (and why) — don't silently undo these

1. **Same MediaPipe everywhere.** Android only has the MediaPipe *Tasks* API, which cannot load
   the old lite model (missing metadata). So desktop was switched from `mp.solutions.hands`
   (lite) to Tasks `HandLandmarker` with the same `hand_landmarker.task`, version 0.10.14, VIDEO
   mode, CPU, thresholds 0.4. Both sides read `shared/mediapipe_config.json` and refuse to start
   if the model sha256 differs. **Verified:** same frame → phone CPU vs PC landmarks within 0.01 px.
2. **CPU, not GPU.** GPU delegate on the Pad 6 was faster but up to 23 px off vs CPU/PC and
   flipped a label. Data must stay comparable → CPU only.
3. **`num_hands: 1`** (2026-10-28): all signs are one-handed; with 2, MediaPipe runs the slow
   palm detector every frame looking for a 2nd hand. PC: 24 → 11.6 ms/frame. CSV keeps the
   **Other hand not recorded at all** (`log_other = False` / `LOG_OTHER = false`): raw take CSV
   = 79 columns: `frame, t_sec, detected, hand_conf, x0…z20, flex1…flex5, acc_x/y/z, gyro_x/y/z,
   glove_dt_ms`.
4. **Input image identical in geometry:** frames are upright + **mirrored** before MediaPipe on
   both platforms (webcam: `cv2.flip`; phone: rotate by CameraX rotation, then flip — both lenses).
5. **Handedness labels:** Tasks labels were opposite to the legacy API on bare-hand images
   (20/24), so `invert_handedness_label: true`. **Uncertain with gloves** (one gloved frame
   disagreed). Harmless: hand picking uses position (`hand_mode = "assume"`), labels only feed
   the `mediapipe_label_mismatch_frac` stat. Check that stat on real takes; flip the flag if ≈1.
6. **No pandas on the phone:** pandas `merge_asof` (nearest, 40 ms tolerance), rounding, CSV text
   and quality stats are ported to Kotlin (`android/core`) and golden-tested bit for bit.
7. **Cross-device normalization (spec v3)** — `aisl_norm.py` = `Normalizer.kt`:
   landmarks → pixels (x·W, y·H, z·W) → wrist-centered → ÷ palm size (mean 3D wrist→MCP 5/9/13/17)
   = 63 shape values + 2 position values (wrist vs image center ÷ min(W,H)) + valid flags + 11
   glove values (flex normalized with the two-point calibration, decision 11; IMU raw); resampled to a fixed **30 Hz × 4 s = 120-step** grid. **79 columns** (`t, g_valid, 65 hand values, glove_valid, 11 glove values`); v2 dropped
   the other hand (v1 had 145); v3 added the flex calibration.
   Webcam vs portrait-phone framing of the same take: shape features equal within 4e-16.
   **Train only on `_norm.csv`, never raw landmarks across devices.**
11. **Two-point flex calibration (2026-10-28):** before the first take (and after any glove
    reconnect / BOOT re-zero) the signer holds the hand **open** 3 s (this also sends `CAL`, zeroing
    flex + IMU) then a **tight fist** 3 s; the last 1 s of each is averaged. Every finger must change
    by ≥ 100 counts. Saved in each take JSON as `flex_calibration` {open, closed, time, method};
    raw CSV keeps raw counts. Normalized flex = (v − open)/(closed − open): ~0 open, ~1 fist, not
    clipped. Takes without it get `glove_valid = 0` (never mix raw and normalized flex). Desktop: key
    C; app: Cal button; Start is blocked until valid.
8. **Record full 4 s takes, not key frames.** Key frames (if wanted) are extracted later as an
   experiment; the BiLSTM needs motion.
9. **Timestamps:** phone uses the sensor exposure timestamp (exact) on `elapsedRealtimeNanos`;
   desktop stamps when OpenCV returns the frame (late by the unmeasured webcam latency).
   Glove samples are mapped to the host clock via `ClockMapper` (min arrival−device offset).
10. **App screen shows the analyzed frame itself** (no separate CameraX Preview), so landmarks
    always line up on every device.

## 5. Current status (2026-10-28)

- Desktop recorder on Tasks API: works (smoke-tested headless). Not yet used for a real session.
- Android app: builds, installs, runs on Galaxy A56 (Android 17) and **Xiaomi Pad 6 (Android 14)**.
  BLE glove connects (50 Hz), IMU OK, live glove values shown, SYNC gap ~1 ms, landmarks aligned.
- Kotlin parity tests: 9/9 pass (`:core:test`).
- **Speed:** Pad 6 ~44 ms/frame MediaPipe (~20 fps) — but measured while throttled (battery 4 %,
  big cores capped at 1.29/2.42 GHz). 1-hand speedup not yet confirmed on a charged, cool tablet.
- No real take recorded on the phone yet (data folder empty).
- Current enclosure is **V2** in `hardware/enclosure/v2/`, based on user hardware photos
  and **9 × 6 × 3 cm** supplied dimensions. One perfboard carries ESP32/dividers and an
  overhanging MPU6050; no separate IMU shelf. **122 × 86 × 42 mm body**, with strap loops
  on the **short ends** (146 × 86 × 42 mm overall), removable corner-support cradle,
  corner USB/button access and long-side wire exit. Large AISL-A lid engraving removed.
  IMU access: 26 × 14 mm opening on the opposite (-X) short end, aligned to the modeled MPU.
  Blend, three checked STLs, renders, ZIP and assembly notes provided. V1 preserved.
  Fit remains provisional: user dimensions interpreted conservatively as main board/stack;
  total overhang span, feature offsets and mounting-hole positions still need measurement.
- **First phone takes (2026-10-28, Pad 6, front cam, 1 hand):** `MediaPipe/data_phone/S01/`
  (`S01_hello_rep01`, `S01_thank-you_rep01`; tablet's own normalized copies in
  `data_phone/norm/`; other-hand columns stripped after recording). 27–28 fps (passes the 27 fps gate), 100 % hand detected,
  glove 50 Hz, 100 % frames synced, max frame–glove gap ≤ 10 ms, 0 packets lost, BLE RTT
  ~25 ms. Only warning: vision ~32 ms/frame (> 20 ms SO1). PC `aisl_norm` on these raw CSVs
  reproduces the tablet's `_norm.csv` exactly (values and text).
  These were **test takes without wearing the glove** (not ergonomic yet), so glove/IMU values
  are not meaningful; don't use them for training. (b) `mediapipe_label_mismatch_frac` 0.91 in one take,
  0.00 in the other → handedness labels unreliable with the glove (keep `hand_mode = assume`).
- **Nothing Phone A059 (Android 16), 2026-10-28, glove worn, first calibrated takes:**
  `MediaPipe/data_phone_nothing/S01/` (hello, home ×2, thank-you ×2; phone's own normalized
  copies in `norm_from_phone/`). Glove 50 Hz, 100 % synced, ≤ 10 ms gaps, 0 lost; **IMU live**
  (acc up to ~6 m/s², gyro ~3 rad/s). Two-point calibration works and PC normalization equals
  the phone's exactly. Issues: ~21 fps (vision ~39 ms) → "low fps" warnings; **F3 (middle)
  calibrated range only 358 counts** but reached ~1500 while signing → normalized F3 up to 3.4
  (fist during calibration not tight on F3, or sensor shifts) — recalibrate with a tight fist;
  F1/F2/F4 hit a constant max in the fist (likely ADC saturation) → ~1.0, fine.
- Git: branch **`android-app` on GitHub** (`Khylerr/THESIS`, commit `cb487f85`, based on GitHub
  `main` incl. Paulo's `ble` commit) — open a PR to merge. **`MediaPipe/venv` is tracked in git**
  (6.5k files); local venv upgrades (opencv 5, jaxlib) have files > 100 MB that GitHub rejects,
  so on JP's PC the venv is hidden from git (`skip-worktree` + `.git/info/exclude`). Never commit
  the venv; long-term, remove it from the repo (team decision: `git pull` would delete it locally).
  Local `main` has 2 old unpushed commits (venv + S01 takes, already contained in `android-app`);
  backup of the pre-squash branch: local `android-app-backup-with-venv`. Uncommitted: `hardware/` (Sol).
  APK for sharing: `D:\College\Thesis\AISL-A_app_2026-10-28.apk` (debug build, not in git).

## 6. Next steps (in order)

1. Once the glove is wearable, record a take wearing it and check flex + IMU change during the
   sign (MPU placement: back-of-hand vs wrist box, §9).
2. Record the same sign on the desktop recorder and compare with `data_phone/S01` (normalized
   curves) → figure for the report.
3. Re-record S01 with the updated desktop recorder and/or phone (old takes used the lite model).
4. Check `mediapipe_label_mismatch_frac` on real takes (decision 5).
   **Protocol draft (2026-10-28):** camera-to-participant distance **1.2 m** (lens to chest;
   allowed 1.0–1.5 m), camera at chest/shoulder height, centered, floor marked. Reason: seated
   signing space (~0.8 m tall × 0.9–1.0 m wide) fits a 640×480 frame for typical webcam/phone
   FOVs at ≥ ~1.0–1.3 m; hand stays ≥ ~70 px (MediaPipe reliable < 2 m; 100 % at 2 m, 77.5 % at
   3 m in Putri et al. 2025; Reimer et al. 2023: 1.75 cm error < 0.75 m vs 4.7 cm at 2.75 m);
   SL datasets use 1.5–2.5 m at higher resolution. Still to do: confirm webcam model/FOV with a
   framing check; decide on a handheld (0.4–0.6 m) test set since the app is used handheld.
5. Webcam latency tap test (tap glove on table in view; IMU spike vs video frame).
6. Glove enclosure (§9): measure full span including MPU overhang, corner mounting holes,
   USB/button offsets and populated stack. Trial-print `hardware/enclosure/v2/exports/`,
   use the latest lid without the AISL-A name, check board retention, wiring/apron clearance
   and short-end strap fit. Check the new opposite-end IMU opening against the actual module;
   finalize fit.
7. Train CNN-BiLSTM on `_norm.csv`; export TFLite; add live recognition + wireframe UI
   (Connect Glove / Live Translation / Settings, TTS) to the app.
8. Later: upgrade MediaPipe (16 KB page support) — bump config, `app/build.gradle.kts`,
   and `pip install mediapipe==X` together, regenerate golden files.

## 7. Known issues / caveats

- `MediaPipe/data/S01/*` were recorded with the legacy lite model (and older ones without glove
  columns; `S01_hello_rep01.csv` stores NaN as the text `nan`, which readers must accept).
- Full model is slower than lite (PC ~1.5×). SO1 target ≤ 20 ms/frame not met on the Pad 6 yet.
- MediaPipe 0.10.14 native libs aren't 16 KB-page aligned → warning dialog on Android 15+ test
  builds; harmless on 4 KB-page devices (A56, Pad 6 both 4 KB).
- Position features depend on framing / handheld shake; shape features don't.
- Raw flex values are relative to the open-hand CAL pose; the normalized ones use open + fist
  (decision 11). Use the same open pose every session (hand flat, palm down, still) and a full,
  tight fist. Existing takes (S01, data_phone) have no two-point calibration → glove invalid in
  their normalized files.
- Desktop calibration routine tested headless with a simulated glove only; the app routine not yet
  on the tablet (tablet was disconnected).
- Keep the phone-holding hand out of frame (with `num_hands: 1` MediaPipe may lock onto it).

## 8. Glove hardware + BLE protocol

ESP32-DevKitC-32D; flex pins {39, 34, 35, 32, 33} with 10 kΩ dividers + 0.1 µF caps; MPU6050
I2C SDA 21 / SCL 22 @ 400 kHz (±8 g, ±500 °/s, 44 Hz DLPF). BOOT button (GPIO0) = recalibrate.
BLE name `AISL_Glove`, service `e1273d67-cf0f-4bb7-9477-4f5d92124a6f`:
DATA `ecbd02f0-…` notify, 29-byte little-endian packet
`u16 seq, u32 t_ms, i16 flex[5], i16 acc[3] (m/s²×100), i16 gyro[3] (rad/s×1000), u8 flags`;
STATUS `493ccb74-…` notify (text: `MPU:OK`, `CAL:DONE …`, `PONG:<id>`);
CMD `b8b472e5-…` write (`CAL`, `PING:<id>`). MTU must be raised (≥ 32) — packet > 20 bytes.

## 9. Enclosure for the glove electronics (owner: Sol)

**Goal:** a 3D-printable, **openable** box that holds the circuit and **straps to the wrist**.

- Original outer target was ≈ 90 × 60 × 30 mm. Actual assembly dimensions supplied by JP:
  **9 × 6 × 3 cm**; V2 conservatively treats that as main perfboard/occupied stack and reserves
  extra MPU overhang. Current outer body **122 × 86 × 42 mm**; including short-end strap
  loops, **146 × 86 × 42 mm**.
- **Openable:** lid with snap-fit or M2/M3 screws (screws survive repeated opening better).
- **Strap:** two slots/loops on the **short ends** (+X/-X, user requested 2026-10-28),
  with 26 × 6 mm clear slots centred at (±67, 0), for a ~20–25 mm wrist strap;
  slightly curved or padded underside for comfort.
- **Contents:** ESP32-DevKitC-32D (≈ 55 × 28 mm board; STEP model in
  `Glove kicad/ESP32-DE-KIT/ESP32-DEVKITC-32D.step`), the flex-sensor divider resistors/caps
  (perfboard), wiring. MPU6050 module STEP: `Glove kicad/MPU-6050/OC09600.step`.
- **Openings needed:** micro-USB port of the ESP32 (flashing/charging), access to BOOT
  (recalibrate) and EN (reset) buttons (or button extenders), cable exit toward the fingers for
  the 5 flex sensors (strain relief), small window/light pipe for the ESP32 LED (optional),
  ventilation not critical.
- **Decisions (user confirmed 2026-10-28):** USB power for now; MPU6050 on the **back of the
  wrist**. Photos show the MPU already attached to and overhanging the main perfboard;
  V2 retains that assembly and orientation, replacing V1's separate shelf.
  No battery compartment. Box goes on the right signing wrist. Keep IMU orientation and
  wearing position fixed; changing location affects the recorded IMU data.
- Current files: `hardware/enclosure/v2/AISL-A_Enclosure_V2.blend`, three STLs in `v2/exports/`,
  closed/exploded/internal-layout previews, rebuild source, `v2/README.md` and print ZIP.
  V1 files/scenes preserved. V2 supports the whole 90 × 60 board at its corners with a large
  open pin field underneath. Corner-hole slots are provisional; check actual accessible holes.
- USB **26 × 16 mm** now on the +X short wall at Y=17; BOOT/EN **16 × 10 mm** at the same
  photographed corner. Glove wiring leaves the -Y long side through a **76 × 11 mm** opening;
  an integral lid apron opens the side for installation. Electronics are schematic envelopes.
  Nominal topology, Manifold-solver collision and independent STL checks pass; physical fit
  and strap strength remain unverified.
- Mount boards with standoffs/clips so nothing rattles (vibration shows up in the IMU).
- Lid name engraving: large AISL-A text removed at JP's request (2026-10-28).
- IMU access opening added on -X end opposite USB: **26 × 14 mm**, centre Y=17, Z=25.4,
  above the strap loop. `v2/imu_access_preview.png` shows this side. Module alignment is nominal.

## 10. Progress report notes (Report No. 5, Part C — sync method)

Written earlier; still accurate in substance: (1) timestamp on arrival / single host clock,
(2) common 4 s window, (3) nearest-timestamp matching (`merge_asof` nearest, **40 ms tolerance**,
no interpolation) → one fused row per camera frame (63 landmarks + 11 glove values + gap),
(4) live sync monitoring (fps, glove Hz, % synced, frame-glove gap, vision ms/frame).
Update Part C if needed: both platforms now use the same model and the phone uses exact sensor
timestamps; the dashboard figure showed IMU all zeros (MPU missing then; IMU works now).
Pending from that report: a table of real synced sample rows (frame, t, glove t, gap, a few
landmarks, F1–F5, acc, gyro). `MediaPipe/data/S01/S01_home_rep04.csv` has glove columns
(IMU zeros: MPU was missing). Never fabricate glove values; label any mock-up as illustrative.

## 11. Rules for agents working here

- Read this file + `android/README.md` before changing code.
- **Parity rule:** anything that affects data (MediaPipe settings, sync, rounding, CSV format,
  normalization) must change in Python AND Kotlin together → re-run `make_golden.py` → run
  `:core:test` (must stay all green).
- Change MediaPipe settings only in `shared/mediapipe_config.json`.
- Don't commit generated folders: `MediaPipe/data_norm/`, `MediaPipe/bench/`, build outputs.
- Commit on a branch, not `main`; don't push without asking JP.
- **Update §5, §6 and the changelog below after any progress.**

## 12. Changelog

- 2026-10-14 — Desktop recorder with BLE glove sync + live dashboard; pilot takes S01.
- 2026-10-28 — Android app (Kotlin) + shared MediaPipe config + normalization spec v1 + golden
  parity tests (9/9). Desktop switched to Tasks API. Tested on Galaxy A56 and Xiaomi Pad 6:
  BLE glove + IMU working, landmarks aligned, phone CPU = PC within 0.01 px, GPU rejected.
  `num_hands` → 1 (one-handed scope). Enclosure task assigned to Sol (§9). This handoff created.
- 2026-10-28 — Designed enclosure V1 using live Blender MCP; USB power and back-of-wrist IMU
  confirmed by JP. Added screw lid, strap loops, removable ESP32/divider carrier and rigid
  MPU6050 shelf. Saved blend, four mm-scale STLs, renders and fit notes in `hardware/enclosure/`;
  closed mesh/collision and independent STL checks completed. Physical trial print pending.
- 2026-10-28 — Enlarged ESP32 USB and BOOT/EN access openings for the soldered board-edge
  placement. Refreshed Blender model, STLs, previews and ZIP; mesh/collision and exported STL
  checks passed. Physical port/button alignment remains unverified.
- 2026-10-28 — Rebuilt as enclosure V2 from JP's six hardware photos and 9 × 6 × 3 cm dimensions.
  Preserved intact perfboard/socketed ESP32/overhanging MPU layout; replaced separate mounts
  with an open cradle, moved USB/buttons to the corner and wires to the long side. Body now
  122 × 86 × 42 mm. Saved separate V2 blend, three verified STLs, three renders and print ZIP;
  V1 retained. Physical mounting/feature offsets need measurement before final fit.
- 2026-10-28 — First phone takes recorded on the Pad 6 (hello, thank-you): 27–28 fps, 100 %
  detected, 100 % glove-synced, ≤ 10 ms gaps; PC normalizer reproduces the tablet's normalized
  CSVs exactly. Test takes without wearing the glove (glove values not meaningful); handedness
  labels unreliable. Takes pulled to `MediaPipe/data_phone/`.
- 2026-10-28 — Other hand removed everywhere (one-handed scope): raw takes 143 → 79 columns, normalization spec v2 → 79 columns. Python + Kotlin changed together; golden regenerated; 10/10 parity tests (new: column layout test). Desktop `data_norm/` and `data_phone/` rebuilt.
- 2026-10-28 — Moved V2 strap loops from long sides to the two short ends, below USB.
  Body stays 122 × 86 × 42 mm; overall becomes 146 × 86 × 42 mm. Updated source, blend,
  STLs, previews and print ZIP; mesh, nominal clearance and exported STL checks pass.
- 2026-10-28 — Removed the large AISL-A engraving from the V2 lid. Updated source,
  assembled/exploded/print meshes, blend, previews and ZIP. Mesh, nominal clearance and
  exported STL checks pass.
- 2026-10-28 — Added a 26 × 14 mm IMU opening on the V2 short end opposite USB, aligned
  with the photo-based MPU envelope. Updated source, base meshes, blend, STLs, previews and
  print ZIP; mesh, nominal clearance and independent STL checks pass.
- 2026-10-28 — Two-point flex calibration (open hand + fist) on desktop (key C) and app (Cal);
  required before takes, saved per take; normalization spec v3 (flex 0 open .. 1 fist).
  Python + Kotlin together, golden regenerated, 11/11 parity tests (new: calibration cases).
- 2026-10-28 — First glove-worn, calibrated phone takes (Nothing A059): sync and IMU good;
  F3 calibration too small; ~21 fps on that phone. Pulled to `MediaPipe/data_phone_nothing/`.
- 2026-10-28 — Pushed `android-app` to GitHub as one clean commit on top of GitHub `main`
  (the old local commits carried a venv with > 100 MB files that GitHub rejected).
