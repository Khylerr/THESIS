# AISL-A — Project Handoff (read this first)

> **For any AI or person picking this up (Claude, Codex, Sol, teammates):** this file is the
> single source of truth for what exists, how to run it, what was decided and why, and what's
> next. **Update it whenever you make progress** (status, decisions, changelog at the bottom).
> Keep it short and factual; dates as YYYY-MM-DD.

Last updated: 2026-11-20

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
| `android/` | Kotlin app: `:core` (pure Kotlin, parity-tested) + `:app` (CameraX, MediaPipe Tasks, BLE, UI). Two screens: recorder (`MainActivity`) and **Inference** (`InferenceActivity`, 2026-11-20, §14). See `android/README.md`. |
| `models/` | Sign classifiers (2026-11-20, §14): the four PyTorch checkpoints from Andrei in `checkpoints/`, `export_models.py` (→ `shared/models/*.aislm`), `make_model_golden.py` (PyTorch reference for the Kotlin tests), `forensics/`, `README.md`. |
| `shared/models/*.aislm` | The models in the app's own format (weights + input spec), bundled into the APK. Generated; edit `models/export_models.py`, not these. |
| `shared/golden/sign_model/` | PyTorch reference outputs for `SignModelTest`. |
| `hardware/pcb/v1/` | **Glove carrier PCB v1** (2026-11-18): generator scripts `build_carrier_pcb.py` (board) and `build_schematic.py` (schematic), KiCad 9 project with **board + matching schematic**, schematic PDF/PNG in `schematic/`, Gerber zip, BOM, STEP, renders, DRC/ERC/parity reports, `README.md`. Designed only, not built. See §13.7 and §13.10. |
| `hardware/enclosure/` | Enclosure V1/V2 for the old perfboard (Blender, STLs, renders), see §9. `v3/` = enclosure for carrier PCB v1 (2026-11-18), not printed: **`v3/freecad/` is the master** (FreeCAD script, .FCStd, STEP, the 2 print STLs, drawing, print zip, §13.9); `v3/*.blend`, `v3/build_enclosure_v3.py` and the previews are the Blender version, pictures only (§13.8). |
| `hand_sign_glove_ble/hand_sign_glove_ble.ino` | **Current glove firmware** (BLE, 50 Hz, binary packets with device timestamp). |
| `hand_sign_glove_code/` | Old Bluetooth Classic firmware (text lines). Not used by the app. |
| `Glove kicad/` | Schematic (`glove/glove.kicad_sch`, **KiCad 10 format**) + symbols, footprints and STEP models of ESP32-DevKitC-32D and MPU6050 module. `glove.kicad_pcb` is an empty stub. **This is the old schematic (caps to 3V3, no connectors): superseded on 2026-11-18 by `hardware/pcb/v1/aisl_glove_carrier.kicad_sch`**, kept untouched as the team's original. Its netlist is in §13.1. |

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
- **2026-11-07 enclosure report figures:** `hardware/enclosure/v2/report_renders_2026-11-07/`
  has six report views (assembled, exploded, internal layout, USB end, IMU end and dimensioned
  top/front), white-background PNGs with 300 dpi metadata, a combined four-panel figure,
  captions/paragraph, camera source and a separate Blender project. Original V2 geometry
  verified unchanged. Figures describe a CAD design with schematic electronics; physical fit pending.
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
  `main` incl. Paulo's `ble` commit) — **PR #1** https://github.com/Khylerr/THESIS/pull/1 (open). **`MediaPipe/venv` is tracked in git**
  (6.5k files); local venv upgrades (opencv 5, jaxlib) have files > 100 MB that GitHub rejects,
  so on JP's PC the venv is hidden from git (`skip-worktree` + `.git/info/exclude`). Never commit
  the venv; long-term, remove it from the repo (team decision: `git pull` would delete it locally).
  Local `main` has 2 old unpushed commits (venv + S01 takes, already contained in `android-app`);
  backup of the pre-squash branch: local `android-app-backup-with-venv`. Uncommitted: `hardware/` (Sol).
  APK for sharing: `D:\College\Thesis\AISL-A_app_2026-10-28.apk` (debug build, not in git).
- **2026-11-18 glove PCB:** carrier PCB v1 exists as design files only (`hardware/pcb/v1/`,
  §13.7): 68 × 46.5 mm, DRC clean, Gerbers ready. It now has a matching schematic in the same
  KiCad project (§13.10): ERC 0, KiCad schematic-parity 0 issues. Waiting on JP's paper fit
  check before ordering from Aivon. **Enclosure V3** for this PCB is modelled (`hardware/enclosure/v3/`,
  §13.8–13.9): 74 × 58.9 × 29.4 mm, not printed. Master = FreeCAD model in
  `hardware/enclosure/v3/freecad/` (print from its `exports/`). Enclosure V2 only fits the perfboard.
- **2026-11-20 sign models + Inference screen (§14):** the app now has a second screen that
  runs Andrei's four CNN-BiLSTM checkpoints (7 signs: B, E, F, L, R, U, i-love-you) live or on
  a 4 s take, with a model picker; unimodal models switch the unused input off. Forward pass in
  plain Kotlin, equal to PyTorch within 2.7e-6. Kotlin tests: `:core:test` 17/17,
  `:app:testDebugUnitTest` 10/10 (screen tests on the JVM). Debug APK:
  `D:\College\Thesis\AISL-A_app_2026-11-20.apk`, installed on the Nothing Phone A059 on 2026-11-20
  (vision-only model seen running live; glove models not tried yet). **Accuracy
  not measured**; three settings of the models are inferred, not confirmed (§14.2, §14.4).
  Git: all of this is uncommitted on branch `android-app`.
- **2026-11-06 CV review:** Verified JP's role as AISL-A thesis team lead and summarized the
  recorder prototype and pilot synchronization results in his one-page Computer Engineering OJT CV.

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
   For the progress report, use the dated report-render folder's four-view figure/captions;
   keep its provisional CAD/physical-fit wording until a trial print is verified.
7. ~~Train CNN-BiLSTM on `_norm.csv`; export TFLite; add live recognition~~ First models exist
   and run in the app's Inference screen since 2026-11-20 (§14; plain Kotlin instead of TFLite).
   Still to do from this item: the wireframe UI (Connect Glove / Live Translation / Settings,
   TTS) and the gloss-to-text (T5) step.
   **Next for the models, in order:** (a) JP: install the new APK, open "Test a trained model",
   try each model in "4 s take" mode with the 7 signs and note what it answers; (b) get the
   training notebook from Andrei and compare with §14.2 (padding, pooling, masks, scaling); if
   anything differs, change `models/export_models.py` and re-run the three steps in
   `models/README.md`; (c) retrain the unimodal models with the corrected column split
   (vision = columns 1–66, glove = 67–78) and without the `t` column if the team agrees;
   (d) add a "no sign" class or a confidence rule before using live mode for translation.
8. Later: upgrade MediaPipe (16 KB page support) — bump config, `app/build.gradle.kts`,
   and `pip install mediapipe==X` together, regenerate golden files.
9. Before adding implementation details to the OJT CV, confirm JP's individual contributions.
   Keep team pilot sync metrics separate from recognition accuracy.
10. **Glove PCB + enclosure V3 (requested by JP 2026-11-18, §13).** Do this **before** the real
    data collection (steps 1–3), because the IMU position must not change once training takes
    exist. This supersedes step 6 (V2 trial print) unless the team decides to keep the perfboard.
    - Done 2026-11-18: carrier PCB v1 designed, DRC clean, Gerbers/STEP/renders exported
      (§13.7, `hardware/pcb/v1/`).
    - **Next, JP/team:** do the paper fit check and the MPU orientation check (§13.7
      "Unverified" list); say whether the IMU under the DevKit is OK; agree caps-to-GND with
      Paulo; pick the fab; buy the parts in `hardware/pcb/v1/fab/BOM.csv`.
    - Done 2026-11-18: enclosure V3 modelled round that PCB, checks clean, STLs exported
      (§13.8, `hardware/enclosure/v3/`). JP confirmed the IMU stays under the DevKit and
      picked Aivon (China) as the fab.
    - **Next, JP/team (in this order):** (1) paper fit check of the PCB; (2) order 5 boards
      from Aivon with `hardware/pcb/v1/fab/aisl_glove_carrier_gerbers.zip` and the settings
      in the PCB README; (3) buy the BOM parts; (4) trial-print the V3 base from
      `hardware/enclosure/v3/freecad/exports/01_base.stl`, test one screw and the USB plug,
      then print the lid. (Enclosure redone in FreeCAD on 2026-11-18, §13.9: done.)
    - Done 2026-11-18: schematic redrawn to match the PCB (§13.10,
      `hardware/pcb/v1/aisl_glove_carrier.kicad_sch`, PDF in `hardware/pcb/v1/schematic/`).
    - **Still open, AI:** add wire
      strain relief to V3; adjust V3 after the first trial print; regenerate V3 if the PCB
      changes after the fit check.

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

## 13. Glove circuit (verified netlist) + PCB / enclosure V3 plan

*(Section added 2026-11-18. Numbered 13 but placed here next to the other hardware sections.)*

**Why:** JP (2026-11-18): "we needa make a pcb and an enclosure." The current build is a
hand-soldered 90 × 60 mm perfboard; enclosure V2 (§9) was sized around that perfboard from
photos. A PCB changes the board size, so **the enclosure must be redesigned around the PCB
(call it V3)**; V2 stays as the perfboard fallback.

### 13.1 Netlist as drawn in `Glove kicad/glove/glove.kicad_sch` (read 2026-11-18)

Extracted by parsing the schematic's wires/junctions/pins (script, not by eye). 17 parts:
U1 ESP32-DevKitC-32D, U2 MPU6050 module (symbol `OC09600`, value `mpu-6050`), R1–R10, C1–C5.
No labels, no power symbols, no connectors, no no-connect flags.

| Net | Connected pins |
|---|---|
| 3V3 | U1 `3V3` (J2-1), U2 `VCC`, one end of all 5 flex sensors (R1, R3, R5, R7, R9), **pin 2 of all 5 caps** |
| GND (a) | U1 `GND1` (J2-14), bottom of all five 10 k resistors (R2, R4, R6, R8, R10) |
| GND (b) | U1 `GND2` (J3-7), U2 `GND`, U2 `AD0` (→ I2C address 0x68) |
| I2C | U1 `IO21` (J3-6) ↔ U2 `SDA`; U1 `IO22` (J3-3) ↔ U2 `SCL` |
| Flex channel on GPIO39 (`SENSOR_VN`, J2-4) | flex R9, 10 k R10, cap C5 |
| Flex channel on GPIO34 (J2-5) | flex R7, 10 k R8, cap C4 |
| Flex channel on GPIO35 (J2-6) | flex R1, 10 k R2, cap C1 |
| Flex channel on GPIO32 (J2-7) | flex R3, 10 k R4, cap C2 |
| Flex channel on GPIO33 (J2-8) | flex R5, 10 k R6, cap C3 |

Each channel is a voltage divider: **3V3 → flex sensor → ADC node → 10 k → GND**, so the ADC
voltage *drops* as the flex resistance rises (bending). Firmware order is
`FLEX_PINS[5] = {39, 34, 35, 32, 33}` = flex1…flex5, which matches the five GPIOs above (all on
ADC1, so they work while BLE is on; 34/35/39 are input-only pins, fine for ADC).
Unconnected on purpose: MPU `INT`, `XDA`, `XCL`; every other ESP32 pin.

### 13.2 Things to fix or decide before layout (found 2026-11-18)

1. **Caps go ADC node → 3V3, not ADC node → GND.** It still low-pass filters (3V3 is an AC
   ground), but it couples 3V3 rail noise straight into the ADC and is not the usual wiring.
   **Unknown whether the real perfboard is wired this way** or the drawing is just different:
   check the board. For the PCB, default plan = caps to GND (ask JP/Paulo before changing, since
   it slightly changes the filter's reference, not the DC values).
2. **Flex sensors are drawn as plain resistors**, no connectors. The PCB needs one 2-pin
   connector per finger (or one 6-pin: 3V3 + 5 signals, since all sensors share 3V3).
   Connector type not chosen (JST-XH 2.54 mm is the hand-solderable default).
3. **R, C and flex symbols have no footprints assigned** (only U1 and U2 do).
4. **GND is two separate wire groups** in the drawing (both end on ESP32 GND pins, so it works
   electrically; on the PCB they become one GND net / ground pour). No power flags, so ERC will
   complain until they are added.
5. **Firmware comment** on `SCL_PIN 22`: "Change to 27 if you remapped SCL during hardware
   repair". Confirm which pin the real board uses before routing I2C.
6. **Power:** still USB only (decision 2026-10-28). Not yet decided for the PCB: keep USB, or
   add LiPo + charger + switch. A wrist-worn box tethered by USB while the other hand holds the
   phone is awkward; ask JP.
7. **MPU6050 module on 3.3 V:** the GY-521-style board has its own regulator on VCC; it works
   on 3V3 in the current build (IMU live, §5), so keep as is.

### 13.3 Tooling facts

- The schematic is **KiCad 10** (`version 20260306`, `generator_version "10.0"`); this PC has
  only **KiCad 9.0.7** (`C:\Program Files\KiCad\9.0`). `kicad-cli` 9 answers
  "Failed to load schematic". So either install KiCad 10 here, or the PCB work happens in a new
  KiCad 9 project re-entered from the netlist in 13.1 (17 parts, quick). Whoever drew it
  (probably Paulo, on another PC) has KiCad 10.
- Footprint sizes from the repo's `.kicad_mod` files: ESP32-DevKitC-32D ≈ **28.7 × 54.9 mm**
  outline, 2 × 19 pins; MPU6050 module ≈ **16.2 × 20.8 mm**. STEP models for both are in
  `Glove kicad/` (usable for the 3D board model).
- Blender MCP + the scripted enclosure pipeline (`hardware/enclosure/v2/build_enclosure_v2.py`,
  helpers in `hardware/enclosure/build_enclosure.py`) is how V1/V2 were made; V3 should reuse it.

### 13.4 Proposed approach (proposal, **not yet approved by JP**)

- **Board type:** a 2-layer **carrier board** with through-hole parts, hand-solderable: female
  header sockets for the ESP32 DevKitC, a 1×8 socket (or direct solder) for the MPU6050 module,
  5 × 10 k resistors, 5 × 0.1 µF caps, flex connectors, 4 × M2.5/M3 mounting holes. Not a
  custom ESP32-WROOM design (needs USB-serial, regulator, antenna keep-out, reflow: too risky
  for the schedule and nothing to gain for a thesis prototype).
- **Expected size:** roughly 60–65 × 40–45 mm (vs 90 × 60 perfboard), stack height about
  20–25 mm with the DevKit on sockets (lower if soldered directly).
- **Order of work:** PCB first, enclosure second. KiCad exports a STEP of the populated board,
  and the enclosure is modelled around that exact geometry, which removes the photo-estimated
  offsets that made V2 "provisional".
- **IMU position is part of the dataset** (§9: changing location/orientation changes IMU data).
  All takes so far are pilot/test only, so **finish PCB + enclosure before recording the real
  training set**, then never move the IMU again.
- **Method:** fix schematic (13.2) → ERC → assign footprints → place + route (KiCad `pcbnew`
  Python scripting; simple enough to route by script, Freerouting as fallback) → DRC with
  `kicad-cli` → export Gerbers/drill, STEP, 3D render → JP reviews in KiCad and prints the board
  1:1 on paper to check the DevKit/MPU pin fit → order. The AI cannot physically verify fit.

### 13.5 Inputs still needed from JP / the team

For the PCB: (a) power choice (USB only vs battery); (b) flex sensor model/length and how the
leads are terminated now; (c) connector preference; (d) DevKit socketed or soldered; (e) is SCL
on 22 or 27; (f) are the caps really to 3V3 on the perfboard; (g) where it gets fabricated
(JLCPCB/PCBWay vs local, which sets design rules and lead time); (h) max size / where on the
wrist; (i) KiCad 10 install OK?
For the enclosure: printer model + bed size + material, strap width, which side the flex wires
exit, which side USB faces when worn, screw sizes available, and (if any) battery dimensions.

### 13.6 Decisions made by JP on 2026-11-18 (approved, don't silently undo)

| Question | JP's answer | Consequence |
|---|---|---|
| Board type | "Yes, carrier board" | 2-layer through-hole carrier; DevKit plugs in. No custom ESP32 design. |
| Power | "USB + spare 5V header" | Powered by the DevKit's USB as now. Extra 1×2 pin header `5V IN` wired to the DevKit `EXT_5V` pin (J2-19) + GND for a future battery pack / power bank. No charger, no battery bay. |
| Flex connectors | "5 x 2-pin JST-XH" | One vertical JST-XH B2B-XH-A (2.5 mm pitch) per finger. Flex sensors are not polarised, so plug direction does not matter electrically. |
| DevKit mounting | "Socketed" | Two 1×19 female 2.54 mm header sockets (8.5 mm tall). DevKit underside sits ≈ 11 mm above the carrier. |
| IMU SCL pin | "GPIO 22" | I2C stays SDA = GPIO21, SCL = GPIO22, same as schematic and firmware. No jumper. |

Defaults chosen by the AI (not asked, change if JP/Paulo disagree):
- Filter caps go **ADC node → GND** on the PCB (schematic draws them to 3V3, see 13.2 item 1).
- The 5V header is a plain pin header, **not** a JST-XH, so a battery pack can never be plugged
  into a flex socket (that would put 5 V on the 3V3 rail and a GPIO).
- Design rules kept loose so any fab (JLCPCB, PCBWay, local) can make it: tracks ≥ 0.4 mm,
  clearance ≥ 0.25 mm, drills ≥ 1.0 mm, 1.6 mm FR4, 2 layers.
- KiCad 10 is **not** installed; the PCB is generated in **KiCad 9.0.7** by a Python script
  (`pcbnew` API, run with `C:\Program Files\KiCad\9.0\bin\python.exe`). Files live in
  `hardware/pcb/v1/`. The KiCad 10 schematic in `Glove kicad/glove/` is left untouched and is
  now **out of date** versus the PCB (no connectors, caps to 3V3). **Redrawn in KiCad 9 on
  2026-11-18: see 13.10.** The old file stays as the team's original.

### 13.7 Carrier PCB v1: what was built on 2026-11-18

**State: designed and rule-checked on the computer only. Not ordered, not soldered, no
physical fit check yet.** Everything is in `hardware/pcb/v1/` (see its `README.md`).

**Tools used (JP asked; he is new to all of this):**
- **KiCad 9.0.7**: free PCB design program, already installed at `C:\Program Files\KiCad\9.0`.
  The board file is `hardware/pcb/v1/aisl_glove_carrier.kicad_pcb`; double-click the
  `.kicad_pro` to open the project, then "PCB Editor"; press Alt+3 for the 3D viewer.
- **`pcbnew` Python API**: KiCad's built-in scripting. `build_carrier_pcb.py` places every
  part, draws every track and the ground pours, and saves the board. Nothing was drawn by
  hand, so the script is the source of truth: change the script and re-run, don't hand-edit
  the board (the script overwrites it).
- **`kicad-cli`** (command line that ships with KiCad): ran the design rule check (DRC), and
  exported the Gerbers, drill files, STEP 3D model, the 1:1 PDF and the 3D renders.
- Word list: *Gerbers + drill files* = the manufacturing files a PCB factory needs (one file
  per copper/mask/silkscreen layer plus hole positions), zipped for upload. *DRC* = automatic
  check for shorts, too-small gaps and unconnected pins. *STEP* = 3D CAD model, used to
  design the enclosure round the board. *Footprint* = the pad pattern of one part.
  *Through-hole (THT)* = parts with legs that go through the board, easy to hand-solder.
- Enclosures V1/V2 were made in **Blender**; V3 was drafted in Blender and then redone in
  **FreeCAD 1.1.4** (free CAD program, installed 2026-11-18), which is now its master (§13.9).

**Result:**
- Board **68 × 46.5 mm**, 2 layers, 1.6 mm, all through-hole, no vias. 78 plated holes
  (58 × 1.0 mm, 20 × 0.8 mm), 6 non-plated 3.2 mm holes (4 mounting + 2 under the MPU module).
- Layout (origin = DevKit centre, +X = USB end, +Y = flex edge, sheet offset (100, 80)):
  DevKit socket rows at Y = ±12.7; **MPU6050 module underneath the DevKit** at (−5.79, 0) with
  its header row at Y = +6.33; five flex cells (R, C, JST) below the DevKit at X = −19, −9, 1,
  11, 21 with JST pins at Y = 27.1; `5V IN` header at (30.5, 15.0)/(30.5, 17.54); M3 holes at
  (−29.5, −11.5), (31.5, −11.5), (−29.5, 27.8), (31.5, 27.8) = 61 × 39.3 mm pattern.
- Netlist read back from the saved board matches §13.1 plus the approved changes (table in
  the README). Flex order = firmware order, **no firmware change needed**.
- DRC (`checks/drc.json`): **0 violations, 0 unconnected**.
- Nominal stack height: carrier 1.6 mm + about 16 mm above (top of the ESP32 shield) + about
  2 mm of solder joints below ≈ **20 mm**. Enclosure V3 inner height should be ≥ 22–23 mm.

**IMU under the DevKit: confirmed by JP on 2026-11-18** ("Keep it under", after being told
the trade-off below). Don't move it without asking him. Reason for the choice: it keeps the board
at 68 mm instead of about 80 mm. Cost: the IMU is hidden (unplug the DevKit to reach it), it
warms up slightly with the ESP32, and there is no "IMU window" like enclosure V2 had. If JP
prefers it beside the DevKit, change `MPU_CX/MPU_CY`, the outline and the I2C/3V3 routes in
the script; the board grows to roughly 80 × 46.5 mm.

**Unverified, must be checked by a person before ordering (also in the README):**
1. Print `checks/print_1to1_pin_fit_check.pdf` at 100 % and put the real parts on it.
2. The DevKit must be the **38-pin** DevKitC (19 per side, rows 25.4 mm apart).
3. **MPU6050 pin order and body direction** come from the SnapEDA footprint, which nobody has
   compared with the real module. With the header on its row the body must point at the top
   socket row. If it points at the flex connectors, the footprint is mirrored: fix in the script.
4. Caps to GND instead of 3V3 (13.2 item 1) not yet agreed with Paulo.
5. ~~No schematic exists for this KiCad 9 project.~~ Fixed 2026-11-18 (13.10): the project now
   has a schematic and KiCad's parity check passes. That proves board = schematic, **not** that
   the schematic is the circuit the team wants: items 1–4 still need a person.

**Problems hit while scripting (so the next agent does not repeat them):**
- `kicad-cli` 9.0.7 cannot open the KiCad 10 schematic ("Failed to load schematic").
- `pcbnew.FootprintLoad` needs a folder ending in `.pretty`. `pcbnew.FootprintSave` returns
  `None` plugin for an empty folder: use
  `pcbnew.PCB_IO_MGR.PluginFind(pcbnew.PCB_IO_MGR.KICAD_SEXP).FootprintSave(dir, fp)`.
- Zone cut-outs: `hole = outline.NewHole()` then `outline.Append(x, y, -1, hole)`. Without the
  last two arguments the points go into the outer outline, the file saves, and **KiCad
  segfaults when loading it** (kicad-cli DRC/render exit code 139).
- The scripted zone filler ignores the board's hole-clearance rule, hence the explicit
  cut-outs (2.3 mm radius) round all 3.2 mm holes.
- KiCad 9 `PAD.SetSize` takes a layer first: `pad.SetSize(pcbnew.F_Cu, size)`.
- Both SnapEDA STEP models are Y-up: model rotation (−90, 0, 0). DevKit model offset
  (0, −3.1, 12.64), MPU model offset (0, 0, 2.54).
- `kicad-cli pcb render --rotate` with a negative first number must be quoted twice in Git
  Bash: `--rotate "'-55,0,-30'"`.
- The DevKit footprint's own courtyard covers the whole module; replaced by two socket-row
  courtyards because the DevKit floats 11 mm above the carrier.

**Commands** (Git Bash, from `hardware/pcb/v1/`; `KC="/c/Program Files/KiCad/9.0/bin/kicad-cli.exe"`,
`PY="/c/Program Files/KiCad/9.0/bin/python.exe"`):
```bash
"$PY" build_schematic.py        # schematic + ERC + netlist + PDF/SVG (13.10). Run this FIRST.
"$PY" build_carrier_pcb.py      # board; reads checks/schematic_netlist.xml for the unused-pad nets
"$KC" pcb drc --schematic-parity --format json --severity-all --units mm -o checks/drc.json aisl_glove_carrier.kicad_pcb
"$PY" check_schematic_vs_pcb.py # independent pad-by-pad comparison, exit code 1 on any difference
"$KC" pcb export gerbers -o fab/gerbers/ --layers "F.Cu,B.Cu,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts" aisl_glove_carrier.kicad_pcb
"$KC" pcb export drill -o fab/gerbers/ --format excellon --excellon-units mm --excellon-zeros-format decimal --excellon-separate-th --generate-map --map-format pdf aisl_glove_carrier.kicad_pcb
"$KC" pcb export step --subst-models --force -o exports/aisl_glove_carrier_assembled.step aisl_glove_carrier.kicad_pcb
"$KC" pcb export pdf --mode-single --black-and-white --layers "F.Mask,F.SilkS,Edge.Cuts" -o checks/print_1to1_pin_fit_check.pdf aisl_glove_carrier.kicad_pcb
"$KC" pcb render --side top --perspective --rotate "'-55,0,-30'" --zoom 0.9 --width 2000 --height 1400 --quality high --background opaque -o renders/04_perspective.png aisl_glove_carrier.kicad_pcb
AISL_VARIANT=no_devkit "$PY" build_carrier_pcb.py   # extra board without the DevKit model, for renders 02/05 only; delete it after
```
After re-exporting Gerbers, rebuild `fab/aisl_glove_carrier_gerbers.zip` (all files in
`fab/gerbers/` except the PDFs and the `.gbrjob`).

### 13.8 Enclosure V3, the PCB fab, and the Blender-vs-CAD question (2026-11-18)

**Enclosure V3 is modelled** in `hardware/enclosure/v3/` (see its `README.md`). State: **fit
prototype on the computer only, nothing printed.** It was started right after JP confirmed
the IMU position, without waiting for the paper fit check and without JP's answers about
printer / strap / screws, using V2's conventions instead (strap loops on the short ends for a
20–25 mm strap, M3 screws, wires out of the −Y long side, USB at the +X short end). If the
PCB changes, V3 must be regenerated.

- Body **74 × 58.9 × 29.4 mm**, 98 mm long over the two strap loops (V2: 122 × 86 × 42, 146).
- Two printed parts: `exports/01_base.stl`, `exports/02_lid.stl`. No cradle: the PCB screws
  onto four corner pads in the base (M3 × 6 into 2.6 mm pilots). Lid: 4 × M3 × 10 into pilots
  in the 5.6 mm thick long walls (there is no room for corner towers because the PCB fills the
  cavity and has its own holes in the corners).
- Openings: USB notch 16 mm wide in the +X wall; 50 mm wide flex-wire notch in the −Y wall
  closed to a 50 × 6 mm slot by a lid apron; two 9 mm lid holes over BOOT and EN. **No IMU
  opening** (IMU is under the DevKit). No name engraving (JP removed it on V2), only small
  BOOT / EN / USB labels.
- Checks: both meshes closed; 0 mm³ overlap between lid, base and 41 envelope boxes of the
  electronics including a 12 × 8.5 mm USB plug (`validation.json`); independent STL check
  passes (`verify_stl.py`).
- Why 29.4 mm tall: socketed DevKit (8.5 mm sockets) + clearance for the USB plug body above it.
- Unverified: everything physical. BOOT/EN hole positions were read off the KiCad 3D model
  (and EN-vs-BOOT sides are from memory); USB plug reach (socket is ≈ 10.5 mm inside the
  wall); screw pilot fit; strap strength; no wire strain relief yet. List in the V3 README.
- **How it was made:** the Blender MCP could not connect (Blender was not open), so the
  script runs Blender **headless**:
  `"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" --background --factory-startup --python hardware/enclosure/v3/build_enclosure_v3.py`
  (about 40 s; builds, validates, exports STLs, renders five previews, saves the .blend).
  `bpy.context.window` exists in background mode, so the V1 helper functions work unchanged.
- The pictures use the real board exported from KiCad as GLB:
  `"$KC" pcb export glb --subst-models --include-tracks --include-zones --include-silkscreen --include-soldermask --user-origin 101x88.05mm --force -o exports/aisl_glove_carrier_assembled.glb aisl_glove_carrier.kicad_pcb`
  (run in `hardware/pcb/v1/`; 101 × 88.05 = board centre on the KiCad sheet). **KiCad 9.0.7
  writes this GLB in millimetres, not metres**, and puts the board underside at z = 0. The GLB
  is for rendering only; the clearance numbers are typed into the script.

**Is Blender good enough for 3D printing? (JP asked 2026-11-18: "is that good enough for the
3d printing? ... whats the more official free software for that")** Answer given: yes for
printing, because a slicer only needs a closed mesh in real millimetres, which is checked
here. Blender is a mesh/art tool, not CAD: no dimensioned drawings, no STEP export, hard for
teammates to edit by hand. The proper free tools are **FreeCAD** (free, open source, opens the
KiCad STEP directly), **Autodesk Fusion** (free personal/student licence), **Onshape** (free
education plan, in the browser), and for scripted CAD **OpenSCAD** / **CadQuery**. None of
these was found installed on JP's PC (only looked in `C:\Program Files` and
`%LOCALAPPDATA%\Programs`; no slicer found there either). Offered: port V3 to FreeCAD if JP
installs it. **Not decided yet.**

**PCB fab (JP, 2026-11-18: "we're actually planning on getting the pcb done from china ...
aivon.com ... this one"):** Aivon's quote page takes a Gerber zip/rar under 10 MB and says not
to put the PCB source file in the same zip. So the only file needed for the bare board is
`hardware/pcb/v1/fab/aisl_glove_carrier_gerbers.zip`. No BOM / pick-and-place needed (hand
soldering; those are for their assembly service). Form settings are in
`hardware/pcb/v1/README.md` ("Ordering from Aivon"): FR-4, 2 layers, 46.5 × 68 mm, single PCB,
qty 5, 1.6 mm, 1 oz, min spacing "6/6mil↑", min hole "0.3mm↑", HASL, Project File Confirm =
Yes. Their capability page allows boards down to 5 × 5 mm; our rules (0.4 mm tracks, 0.25 mm
gaps, 0.8 mm holes) are far inside any standard process. **Nothing was uploaded or ordered by
the AI**; JP orders with his own account, after the paper fit check.

### 13.9 Enclosure V3 redone in FreeCAD = the master model (2026-11-18)

JP chose "Redo in FreeCAD" after the Blender-vs-CAD answer in §13.8. **From now on the
FreeCAD model in `hardware/enclosure/v3/freecad/` is the master for enclosure V3.** The
Blender files one folder up are the same design and are kept for rendered pictures only;
their STL export was switched off and their `exports/` and print zip were deleted so there is
exactly one set of print files.

- **FreeCAD 1.1.4 was installed on JP's PC on 2026-11-18** with JP's OK ("Yes, install it"):
  `winget install --id FreeCAD.FreeCAD` (official installer from the FreeCAD GitHub releases,
  hash verified by winget). Installed per-user at `%LOCALAPPDATA%\Programs\FreeCAD 1.1\`.
  Command-line tool: `...\FreeCAD 1.1\bin\freecadcmd.exe`; GUI: `...\bin\freecad.exe`.
- Source: `freecad/build_enclosure_v3_freecad.py` (Part workbench scripting: boxes with
  filleted vertical edges, cylinders, cut/fuse). Same parameters and coordinates as the
  Blender script. Run from `freecad/`:
  `"$LOCALAPPDATA/Programs/FreeCAD 1.1/bin/freecadcmd.exe" build_enclosure_v3_freecad.py`
  (15–30 s). Outputs: `AISL-A_Enclosure_V3.FCStd`, `step/01_base.step`, `step/02_lid.step`,
  `step/AISL-A_V3_assembly.step` (with the PCB), `exports/01_base.stl`, `exports/02_lid.stl`
  (lid pre-flipped for printing), `drawings/AISL-A_V3_views.svg` (A4, three views with main
  dimensions, 1.5:1), `validation.json`. Print zip: `freecad/AISL-A_V3_Print_Files.zip`.
- **Better check than Blender's:** the script imports the real populated-board STEP from
  KiCad (`hardware/pcb/v1/exports/aisl_glove_carrier_assembled.step`, 254 solids), moves it
  by (−101, +88.05, +5.9) into enclosure coordinates, and computes the shared volume with the
  base and the lid: **0 mm³ for every solid**, also 0 for base vs lid and for a 12 × 8.5 mm
  USB-plug box. Tallest part to lid underside 3.62 mm; lowest pin to floor 1.69 mm.
- Cross-check: FreeCAD base 36 258 mm³ / lid 11 464 mm³ vs Blender 36 288 / 11 506 (0.1–0.4 %
  apart; FreeCAD has 0.6 mm chamfers on the base bottom and lid top where Blender had a
  0.3 mm bevel on every edge). STLs closed, checked by FreeCAD and by `freecad/verify_stl.py`.
- Limits to tell JP honestly: the `.FCStd` contains generated solids, **not** a sketch/pad
  history, so dimensions are changed in the script, not by clicking; no colours or hidden
  objects are saved because the script runs without the GUI; the drawing sheet is an SVG
  written by the script (outlines from `TechDraw.projectEx` + a few overall dimensions), not a
  FreeCAD TechDraw page.
- Things learned: `freecadcmd` may not define `__file__` (script falls back to `sys.argv`);
  `TechDraw.projectEx(shape, direction)` chooses its own paper axes for side views, so the
  script first transforms the shape so the wanted view looks down Z; `Part.makeWireString`
  + `Part.makeFace(wires, 'Part::FaceMakerBullseye')` gives engraved text headless (font
  `C:/Windows/Fonts/arial.ttf`); FreeCAD writes a `.FCBak` backup on every re-save (now in
  `hardware/enclosure/.gitignore`).

### 13.10 Schematic redrawn to match the PCB (2026-11-18)

JP, 2026-11-18, answering "Redraw the schematic to match the new PCB now?": **"Yes, redraw it"**.

**What exists now** (all in `hardware/pcb/v1/`, same KiCad 9 project as the board, so opening
`aisl_glove_carrier.kicad_pro` shows schematic and PCB together):

| File | What |
|---|---|
| `build_schematic.py` | **The source of the schematic.** Writes everything below. Edit this, not the `.kicad_sch`. |
| `aisl_glove_carrier.kicad_sch` | The schematic, one A4 sheet, KiCad 9 format. |
| `schematic/aisl_glove_carrier_schematic.pdf`, `.png`, `aisl_glove_carrier.svg` | Printable copies for the report. |
| `lib/aisl.kicad_sym`, `sym-lib-table` | Project symbol library: DevKit and MPU6050 module symbols (SnapEDA, converted to KiCad 9, renamed, footprint field pointing at `lib/aisl.pretty`). |
| `lib/snapeda_original_symbols/` | Untouched copies of the two SnapEDA `.kicad_sym` files from `Glove kicad/`. |
| `aisl_ids.py` | Shared by both build scripts: gives a symbol and its footprint the same UUID. |
| `check_schematic_vs_pcb.py` | Independent comparison of schematic netlist vs board, pad by pad. |
| `checks/erc.json`, `erc_report.txt` | KiCad electrical rules check of the schematic. |
| `checks/schematic_netlist.xml` | Netlist KiCad exported from the schematic. |
| `checks/schematic_vs_pcb.json` | Result of the independent comparison (also lists every net). |

**What the schematic contains:** 22 parts, the same as the board: U1 (DevKit), U2 (MPU6050
module), R1–R5 10 k, C1–C5 100 n, J1–J5 (flex JST-XH), J6 (5 V header), H1–H4 (M3 holes).
10 connected nets: `+3V3`, `GND`, `FLEX1`–`FLEX5`, `I2C_SCL`, `I2C_SDA`, `+5V_EXT`, exactly the
table in the PCB README. The 29 unused pins (26 on the DevKit, `INT`/`XCL`/`XDA` on the MPU)
carry no-connect marks. Caps go node → GND (13.6), flex sensors are connectors.

**Checks, all run by KiCad 9.0.7 itself, results on 2026-11-18:**
- ERC (`kicad-cli sch erc --severity-all`): 0 errors, 0 warnings.
- DRC with `--schematic-parity`: 0 violations, 0 unconnected, **0 parity issues**.
- `check_schematic_vs_pcb.py`: 22 = 22 parts, 78 = 78 pads, 0 problems (reference, value,
  footprint and net of every pad).

**What changed on the PCB side, and proof that the copper did not change:**
- `build_carrier_pcb.py` now (a) gives each footprint the UUID of its symbol plus sheet name
  and file, and (b) puts each unused pad on the single-pad net KiCad expects for a no-connect
  pin, e.g. `unconnected-(U1-EN-PadJ2-2)`, `unconnected-(U2-PadINT)`. Names are read from
  `checks/schematic_netlist.xml`, not guessed. This is what KiCad's "Update PCB from
  Schematic" does. Before this, parity reported 29 "Pad missing net given by schematic"
  (parts were already matched by reference, so there were no other parity issues).
- The board was regenerated and Gerbers/drill re-exported, zip rebuilt (9 files, 79 620 bytes).
  A text diff of the Gerbers is useless: KiCad writes items in a different order on every
  build (random internal IDs) and the net names inside changed. So old and new were compared
  **as geometry** (every flash, line, arc and filled region with its aperture, order ignored;
  `hardware/pcb/v1/compare_gerbers.py OLD NEW`, self-tested by comparing F.Cu with B.Cu, which
  it reports as different):
  identical on all 7 layers (F.Cu 135, B.Cu 87, masks 84 + 84, silk 1186 + 347, outline 8
  primitives). Both drill files are identical text. **The board a fab would make is the same
  board as before.** STEP, renders and the 1:1 fit-check PDF were not re-exported for that reason.

**How the schematic file is made (for the next agent):**
- KiCad 9 has **no scripting API for schematics** (`pcbnew` has one, eeschema does not), so
  `build_schematic.py` writes the `.kicad_sch` as text (S-expressions, `version 20250114`).
- Symbols are copied as raw text out of KiCad's own libraries
  (`C:\Program Files\KiCad\9.0\share\kicad\symbols\Device.kicad_sym` etc.) into the file's
  `lib_symbols` block, with the top-level name changed to `Lib:Name`. The two SnapEDA symbols
  are first converted with `kicad-cli sym upgrade --force` (they are 2021 format).
- Pin positions are parsed from those symbols. A pin at library (x, y) on a symbol at
  (sx, sy) with rotation 0 is at sheet (sx + x, sy − y): the library's Y axis points up, the
  sheet's points down. Rotation is counter-clockwise on screen. Every wire starts at a computed
  pin position and everything must sit on the 1.27 mm grid (the script asserts this).
- Connections between blocks use **global labels** (`FLEX1`…, `I2C_SCL`, `I2C_SDA`,
  `+5V_EXT`), so the net names equal the PCB's with no leading `/`. Local labels would give
  `/FLEX1` and break parity.
- `PWR_FLAG` on `+3V3`, `GND` and `+5V_EXT`: the SnapEDA DevKit symbol declares its 3V3/GND/5V
  pins as power *inputs*, so without a flag ERC says the nets have no supply.
- UUIDs are `uuid5(fixed namespace, name)` (`aisl_ids.py`), so re-running gives the same file
  and the symbol-to-footprint links survive regenerating either file. Do not change the namespace.
- H1–H4 are `Mechanical:MountingHole` symbols with `in_bom no`, so parity sees the four
  mounting-hole footprints as wanted.
- Fields on a rotated symbol (J1–J5 are rotated 180°) are written centred, because left/right
  justification flips with the symbol.
- Rendering the PDF to PNG: `pdftoppm` is not installed here; PyMuPDF (`import fitz`) in the
  system Python 3.11 works (`page.get_pixmap(dpi=200).save(...)`).
- Build order matters: `build_schematic.py` first (writes the netlist), then
  `build_carrier_pcb.py`. Re-running the board script changes the `.kicad_pcb` text (new
  internal IDs) but not the geometry; re-export the Gerbers and rebuild the zip after it so
  the fab files always come from the board file on disk.
- First run hit one bug: an `assert` comparing `66.04 - 2.54` with `63.5` failed on float
  noise. Compare with a tolerance.

**Still not covered:**
- Parity proves board = schematic. It does not prove the circuit is what the team wants:
  caps to GND is still not agreed with Paulo, and the MPU6050 pin order is still the
  unverified SnapEDA one (13.7 list).
- The note "use USB or J6, never both at once" on the sheet comes from Espressif's DevKitC
  guidance (one power source at a time), written from memory, not re-read on 2026-11-18.
- The note "the module has its own I2C pull-ups" is what the common GY-521 has; nobody has
  looked at the team's actual module.
- The old KiCad 10 schematic in `Glove kicad/glove/` was not edited. It still shows the old
  circuit. For the report, use the new PDF.
- Nobody has opened the new schematic in the KiCad window yet (only `kicad-cli` and the PDF).

## 14. Sign-recognition models + the app's Inference screen (2026-11-20)

*(Section added 2026-11-20, numbered 14, placed here before §10.)*

**Request (JP, 2026-11-20):** "can u implement these models in the app. create a separate window
on the app for inference, the user for now should be able to choose what model to test, if they
choose unimodal, turn off the part where it requires either the mediapipe or glove. make the ui
for this separate inference window ux friendly. make no mistakes."

### 14.1 The four checkpoints

JP downloaded them on 2026-11-20 from Google Drive; owner **abadandrei22@gmail.com** (teammate
Andrei), created 2026-11-16. Copies are now in `models/checkpoints/` (115 KB each):

| File | sha256 (first 12) | Meaning |
|---|---|---|
| `multimodal_raw.pth` | `cee8485b556b` | camera + glove, un-augmented data |
| `multimodal_augmented_60reps.pth` | `2a1b19ee6722` | camera + glove, augmented data |
| `unimodal_vision_raw.pth` | `221a3da0f1db` | camera only |
| `unimodal_glove_raw.pth` | `d0f000925094` | glove only |

Each file is a dict `{model_state_dict, history, class_to_idx}`. **Nothing else is stored**: no
preprocessing config, no scaler, no sequence length, no forward() code. **The training
notebook/script and the training dataset are NOT on JP's PC and NOT in the Drive files shared
with JP** (searched D:\, Downloads, Drive). Everything below marked "inferred" was worked out
from the weights; ask Andrei for the training code to confirm.

- Classes (same in all four), index order: `B, E, F, L, R, U, i-love-you` (7).
- Layers (names from the state dict): `conv1d` Conv1d(79 → 32, kernel 3) → `bn1` BatchNorm1d(32)
  → `relu` → `dropout1` → `bilstm` LSTM(32 → 32, bidirectional, 1 layer) → `bn2` BatchNorm1d(64)
  → `dropout2` → `fc` Linear(64 → 7). 27 591 weights.
- `history`: 200 epochs each; last val_acc 1.0 (raw models), 0.991 (augmented).
- The pickles only reference `collections.OrderedDict`, `torch._utils._rebuild_tensor_v2`,
  `torch.FloatStorage`, `torch.LongStorage` (checked by disassembling, nothing executed).
  `models/pth_reader.py` reads them **without torch** and refuses any other pickle global.

### 14.2 What the 79 inputs are (inferred, with numerical evidence)

**Input = the 79 columns of the app's own `_norm.csv` (spec v3), in file order, no scaling:**
`t, g_valid, g_x0..g_z20 (63), g_px, g_py, glove_valid, flex1..5, acc_x/y/z, gyro_x/y/z`.
So one sample = one normalized take = 120 steps × 79 (30 Hz × 4 s). Evidence
(scripts in `models/forensics/`, run `python models/forensics/<n>.py models/checkpoints`):

1. Conv1d weights that never received a gradient stay inside PyTorch's init range
   ±1/√(79·3) = ±0.065. Input channels **2, 3, 4** are untouched in the two raw models that use
   vision: those are `g_x0, g_y0, g_z0`, the wrist relative to itself = always exactly 0.
   (Raw-CSV layout would put `detected, hand_conf, x0` there: not constant zero.)
2. `unimodal_vision_raw`: channels **63–78 untouched**, 0–62 trained.
   `unimodal_glove_raw`: channels **0–62 untouched**, 63–78 trained.
   So the unimodal models were made by **zeroing columns by index**: vision = `[:63]`,
   glove = `[63:]` (the trainer assumed "63 landmark values first, then 16 glove values").
3. `bn1.running_mean − conv bias = Σ(weights) · (mean of each input channel)`. Solving that for
   the glove model (32 equations, 16 unknowns) fits with 2.6 % residual (wrong channel blocks:
   52–76 %) and gives the training data's channel means: `glove_valid` 0.94, `flex1..5`
   0.67 / 0.70 / 0.33 / 0.56 / 0.67 (0 = open, 1 = fist: the two-point calibration), gyro ≈ 0,
   `g_y20` −1.04, `g_z20` −0.24, `g_px` 0.20, `g_py` 0.14. Vision + multimodal solved together:
   `t` mean 1.93 (0…3.97 s ramp → 1.98), `g_valid` 0.89, and landmark means that form an upright
   hand. The means are far from 0, so **no StandardScaler / centering was applied**.
4. Pooling: the backward half of `bn2` has ~10× smaller variance than the forward half in all
   four models, and a single backward LSTM step on the last frame reproduces the backward
   `bn2.running_mean` with correlation 0.90 (multimodal). So the classifier reads
   **`lstm_out[:, -1, :]`** (last time step), not `h_n` and not a mean over time.
5. Conv padding: the same test gives correlation 0.90 with `padding=1` vs 0.79 with `padding=0`
   (0.67 vs 0.57 glove, 0.75 vs 0.66 vision). **`padding=1` is the best-supported value but this
   is the weakest of the five inferences.**

**Consequences / problems found in the training (tell Andrei):**
- The mask boundary is off by 4: columns 63–66 are `g_y20, g_z20, g_px, g_py` (camera values).
  The **"glove-only" model was trained WITH those 4 camera values** (their weights moved), and
  the vision-only model was trained WITHOUT them. Correct split of the 79 columns:
  vision = columns 1–66 (`g_valid` + 65 hand values), glove = columns 67–78.
- Column 0 (`t`, the time stamp 0…3.967 s) is used as a feature. Harmless but not a signal.
- No "no sign" class: the models always answer one of the 7 signs.

### 14.3 What was built (2026-11-20)

**Decision: no TFLite / ONNX / PyTorch Mobile.** The network has 27 591 weights, so its forward
pass is written in plain Kotlin in `:core` (`SignModel.kt`) and compared with real PyTorch in a
unit test. Reasons: no new native library (MediaPipe's are already not 16 KB aligned), no
PyTorch → ONNX → TFLite conversion of an LSTM to trust, testable on the PC without a phone,
~3 ms per prediction. This replaces "export TFLite" in the old next-step 7.

| Path | What |
|---|---|
| `models/checkpoints/*.pth` | The four originals. |
| `models/pth_reader.py` | Checkpoint reader, no torch, no arbitrary pickle code. |
| `models/export_models.py` | `.pth` → `shared/models/<id>.aislm`. **The only place** that holds what a checkpoint does not store: `COMMON` (79 inputs, 120 steps, 30 Hz, `conv_padding=1`, `pooling=last_step`, feature spec 3) and per model `title`, `camera`/`glove` = `required/optional/off`, `zero_cols`. Run: `python models/export_models.py` (numpy only). |
| `models/make_model_golden.py` | Real PyTorch reference → `shared/golden/sign_model/` (7 input cases × 4 models: logits, probabilities, top class). Loads each checkpoint with `strict=True`. Needs torch. |
| `models/forensics/` | The evidence scripts of 14.2. |
| `models/README.md` | How to add or replace a model. |
| `shared/models/*.aislm` | What the app bundles (Gradle `sharedAssets` task copies them into the APK assets). Format: `AISLM1\n`, int32 header length, `key=value` text header, float32 tensors. |
| `android/core/.../SignModel.kt` | Parser + forward pass (mask → Conv1d → BN → ReLU → BiLSTM → last step → BN → Linear → softmax). Refuses unknown pooling/format, wrong tensor sizes, NaN input. |
| `android/core/.../SignWindow.kt` | 4 s of live data → 120 × 79 features by running the recorder's own code (`FrameRow.build` → `TakeSync.sync` → `Normalizer.normalizeTake`). `gridFrames()` = the no-camera case. |
| `android/core/src/test/.../SignModelTest.kt` | 6 tests (below). |
| `android/app/.../InferenceActivity.kt` + `res/layout/activity_inference.xml`, `item_model.xml` | The Inference screen. |
| `android/app/.../ProbBarsView.kt`, `GloveView.kt` | Probability bars; flex/IMU panel shown when the camera is off. |
| `android/app/.../AppSession.kt` | Shared by both screens: the one `GloveBle` connection and the session's flex calibration. |
| `android/app/src/test/.../InferenceScreenTest.kt` | Screen tests on the JVM (Robolectric), write PNGs to `android/app/build/inference_screens/`. |

**Changes to existing code (small, on purpose):** `MainActivity`: new full-width button
"Test a trained model →" (`btnInference`, top of `activity_main.xml`; refuses while a take or
calibration is running); glove now comes from `AppSession.glove()`, flex calibration is stored in
`AppSession.flexCal` (so a calibration done on either screen counts on both);
`onStart()` re-takes the camera after the Inference screen; `onDestroy()` stops the glove only
when the activity is really finishing. `CameraPipeline`: new `stop()` (unbinds only its own
stream), `running`, and `start()` no longer binds if `stop()` was called meanwhile.
`AndroidManifest.xml`: `InferenceActivity` (portrait, not exported). Gradle: `.aislm` assets,
`models.dir` for `:core:test`, Robolectric test dependencies for `:app`.
Nothing in the recording / normalization path changed; `make_golden.py` was not re-run and
did not need to be.

**How the screen works**
- Open it with "Test a trained model →" on the recorder screen. Top card = the model; tap it to
  choose one of the four (it lists every `.aislm` in the APK, ordered by the header's `order`;
  the last choice and mode are remembered).
- **Only what the model uses is switched on and asked for** (header fields `camera`, `glove`):
  - Multimodal (both files): camera + MediaPipe, glove, flex calibration.
  - Vision only: camera + MediaPipe. Glove chip says "not used", calibration "not needed", the
    screen never waits for the glove or Bluetooth permission. (The BLE link itself is left
    alone if it is up: dropping it would throw away the recorder's calibration.)
  - Glove only: **camera and MediaPipe are off** (camera chip "off · not used"), the picture is
    replaced by a flex-bar / IMU panel. A switch "Also use the camera (how this model was
    trained)" turns the camera on to feed the 4 leaked columns (14.2); default off.
- Three status chips (camera / glove / calibration) + one message in the picture area say what is
  missing; the main button is always the next useful action: Allow camera / Allow Bluetooth /
  Calibrate glove / Start take / Cancel / Pause / Resume.
- Calibration here = the same two-point routine as the recorder (sends `CAL`, open hand 3 s,
  fist 3 s, last 1 s averaged, `FlexCalibration.fromSamples`).
- **Live**: every 0.3 s the last 4 s (window ends on the newest frame, or newest glove sample
  when the camera is off) → prediction. It first waits until 4 s have been collected since the
  inputs became ready. **4 s take**: 3 s countdown, then exactly 4 s, like recording a take;
  this is the mode that matches the training data most closely.
- Result card: top sign + percent, a bar per class, and a line "hand in X % of the 4 s · glove
  in Y % · ms". Below 60 % it says "Not sure". Under 50 % tracked hand / glove data it warns.
  No tracked hand at all (camera models) or no glove data → no answer is shown.
- Inputs that a model does not use are also zeroed by the model's own mask (`zero_cols`), so
  the result cannot depend on them (unit-tested).

**Verified on the PC (2026-11-20), nothing on a phone yet:**
- `torch.load(..., weights_only=True)` + `load_state_dict(strict=True)` works for all four
  with the reconstructed module (torch 2.15.0 CPU, in a throwaway venv, not in the repo).
- `.aislm` tensors = checkpoint tensors, bit for bit (checked by numpy and by torch).
- `:core:test`: 17/17 (11 old + 6 new). Kotlin vs PyTorch logits on 7 inputs × 4 models:
  largest difference **2.7e-6**; same top class everywhere. The 7 inputs: random, zeros, a
  desktop take, two phone takes with a calibrated glove, a "training-like" synthetic one, wide
  random.
- `SignWindow` on the golden take = the Kotlin normalizer applied to the take CSV the Python
  recorder code wrote: bit-equal (so live features = recorded-take features).
- `:app:assembleDebug` builds; the APK contains the four `.aislm` files.
- `:app:testDebugUnitTest`: 9/9 (`InferenceScreenTest`, Robolectric 4.14.1 with native graphics,
  Android 15 runtime, on the JVM). It opens the real activity and layout and checks: the four
  models are listed in order and the choice/mode is remembered; vision model → glove "not
  used", calibration "not needed", never asks for Bluetooth; glove model → camera "off · not
  used", camera view replaced by the glove panel, camera not running, never asks for the camera
  permission; multimodal → asks for both; the result card shows PyTorch's answer for a golden
  input, flags "Not sure" under 60 % and "do not trust" under 50 % tracked hand; fits a
  411 × 891 dp phone without scrolling and scrolls on a 360 × 640 dp one (the first version
  squeezed the picture area to 28 dp there: fixed with a ScrollView + 176 dp minimum).
  Screenshots of every state: `android/app/build/inference_screens/*.png` (regenerated by the
  test; looked at by the AI on 2026-11-20).
- Robolectric note for the next agent: its first run downloads a 200 MB Android runtime jar
  (`android-all-instrumented-15-robolectric-12650502-i7.jar`) and its own downloader **hung with
  no timeout** on JP's connection (23 min). Fix used: kill the Gradle test worker, download the
  jar with `curl -C -` from `https://repo1.maven.org/maven2/org/robolectric/android-all-instrumented/15-robolectric-12650502-i7/`
  into `~/.m2/repository/org/robolectric/android-all-instrumented/15-robolectric-12650502-i7/`,
  check it against the `.jar.sha512` next to it. It is cached there now on JP's PC.
- Android lint was started and cancelled (it was also downloading); not run.
- **First run on a phone, 2026-11-20 13:46, Nothing Phone A059 (serial 00149157O002357):**
  `AISL-A_app_2026-11-20.apk` installed with `adb install -r` (USB debugging had to be switched
  on first; Windows showed the phone only as an MTP device "A059" until then). App starts, no
  crash in logcat. Inference screen in dark mode, model "Vision only": camera picture live,
  chips "Glove: not used" / "Calibration: not needed", live prediction shown ("R 98 %", hand in
  74 % of the 4 s, 15 ms per window incl. feature building). Android shows the known
  "16 KB compatible" warning dialog for MediaPipe's libraries at start (§7): tap OK.
  **Still not done on the phone:** glove models (glove was not connected: chip "scanning"),
  calibration from this screen, 4 s take mode, and any accuracy check with the 7 signs.
- **Not verified:** the screen on a real phone (no phone was connected; the emulator on JP's
  PC cannot start: "Android Emulator hypervisor driver is not installed"), real camera/glove
  timing in the new screen, and **recognition accuracy** (no training data here; the only real
  takes on this PC are hello / home / thank-you, which are not among the 7 classes).

**Glove "does not connect to the phone" (JP, 2026-11-20 ~13:56): what it really was.**
JP tried the Play Store app *Serial Bluetooth Terminal* and got "read failed, socket might
closed or timeout". Read from `adb shell dumpsys bluetooth_manager` on the A059:
- 13:56:10 → 13:56:15: an **RFCOMM / SPP (UUID 00001101) connect to the glove failed**. That is
  Bluetooth *Classic* serial. The glove runs `hand_sign_glove_ble.ino` (name `AISL_Glove`), which
  is **BLE only** and has no serial port, so a Classic terminal can never connect; that error
  text is what Android gives for it. (The old Classic firmware is named
  `ESP32_Glove_Controller`.) Not a fault of the glove or the app.
- 13:58:34: **`com.aisla.app` scanned (found the glove in 118 ms) and connected over BLE**; the
  link stayed up (ACL LE: Y, encrypted). So the glove does connect to the phone.
- Why it looked unconnected: (1) the Inference screen was on "Vision only", whose glove chip said
  "not used" (now "connected · not used" when the link is up); (2) the app only scans while it
  is on screen: Android freezes it in the background (log: "sync unfroze ... com.aisla.app"), so
  nothing happens while another app is in front; (3) at 13:46 the chip said "scanning": the
  glove was not advertising then (off, still booting, or held by another device) - not
  determined.
- The glove is also **paired** in the phone's Bluetooth settings (bond with LE keys). Not needed
  for the app. If the ESP32 is re-flashed later and the app then loops on connect/disconnect,
  remove "AISL_Glove" under Settings > Bluetooth (Forget) and let the app connect by itself.
- The laptop's Bluetooth was off at the time, so the PC was not holding the glove.
- 14:06: rebuilt APK (glove chip "connected · not used") installed with `adb install -r`; the
  app reconnected to the glove 5 s later by itself. Recorder screen then showed
  **GLOVE 49 Hz, IMU OK, SYNC gap 2 ms (max 9)**: data is streaming.
- **Two things seen on that screen that need a look (not caused by the new code, it was the
  recorder screen):** (a) **CAMERA 9.5 fps, MediaPipe 100 ms/frame** (this phone did ~39 ms /
  21 fps on 2026-10-28) with no hand in view; cause unknown (phone hot / battery saver /
  palm-detector running every frame while no hand is found?). At under ~10 fps the frames are
  more than 100 ms apart, so `Normalizer` marks grid steps invalid (`MAX_GAP_SEC = 0.10`) and
  the models get holes: check the Camera chip's fps before judging a model. (b) flex read
  **F1 0, F2 0, F4 0, F3 -1974, F5 -1142** in one snapshot (glove state unknown, not
  calibrated): if F1/F2/F4 stay at exactly 0 while bending, those channels are pinned (wiring /
  ADC rail) and the two-point calibration will refuse them.

**Installed on a second phone, 2026-11-20 14:18:** Samsung Galaxy A56 (SM-A566B, Android 17,
adb serial `RRCY608SYYV`), same APK (`AISL-A_app_2026-11-20.apk`, built 14:02), `adb install -r`,
app launched. Nothing tested on it yet beyond starting. With two phones around: the glove
connects to whichever phone has the app on screen first; the other one stays on "scanning".

**Bug found by JP on the phone and fixed, 2026-11-20 14:22 ("Calibration stopped. The glove
stopped sending data" although the glove chip showed 49 Hz):** the Inference screen's
calibration aborted when no glove sample arrived for 0.5 s (`GLOVE_FRESH_SEC`). But the first
thing a calibration does is send `CAL`, and the firmware then **stops streaming while it zeroes
itself**: `calibrateSensors()` in `hand_sign_glove_ble.ino` takes 50 samples with `delay(10)`
(about 0.7 s, more if it re-inits the MPU first). So every calibration on this screen stopped
immediately. The recorder screen never had that check, which is why Cal worked there.
Fix: `InferenceActivity.calibrationLost()` + `CAL_STALL_SEC = 2.5` (abort only if the link is
down or nothing arrived for 2.5 s); a glove that is really dead is still caught at the end by
`FlexCalibration.fromSamples` ("too few glove samples"). New test
`calibrationSurvivesTheGlovesZeroingPause`. Why the PC tests missed it: they have no glove, so
nothing exercised the calibration with a real stream. **Lesson: any "is the glove alive" rule
must allow the ~0.7 s CAL pause.**
Verified on the Galaxy A56 at 14:23 after reinstalling: JP calibrated on the Inference screen,
chips "Camera: hand tracked", "Glove: connected · 50 Hz", "Calibration: done"; **Multimodal
model, live mode, open gloved hand → "B 90 %"** (F 9 %), "hand in 70 % of the 4 s · glove in
99 % · 31 ms". First complete camera + glove + calibration + model run on a phone. One sign,
one look: not an accuracy measurement. "Hand in 70 %" with the hand held in view suggests the
frame rate is low enough to leave gaps (see the 9.5 fps note above).

### 14.4 Open points / what to ask Andrei

1. **Send the training notebook/script.** Needed to confirm: conv `padding` (inferred 1),
   pooling (inferred last time step), that the input is the plain `_norm.csv` matrix with no
   scaler, the unimodal masks, and what the augmentation was.
2. The glove-only model's mask leaves 4 camera columns in (14.2). With the camera off (what JP
   asked for) those are 0, which the model never saw in training → its accuracy in the app may
   be lower than its validation accuracy. Compare with the "Also use the camera" switch on.
   Proper fix = retrain with vision = columns 1–66, glove = columns 67–78.
3. Was the data recorded with the phone app, the desktop recorder, or both? Which hand, which
   camera distance? (Position columns `g_px, g_py` and the `t` column are used by the models.)
4. Record a few takes of the 7 signs with the app and check the models on them (the Inference
   screen in "4 s take" mode, or offline: `_norm.csv` → `make_model_golden.py`-style script).

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
- 2026-11-06 — Cross-checked the thesis handoff and past chats and prepared JP's Computer Engineering OJT CV.
- 2026-11-07 — Rendered enclosure V2 for the progress report: assembled, exploded, internal,
  USB/IMU end and annotated orthographic views; white-background PNGs, combined report figure,
  captions, ZIP and separate camera-scene blend in `hardware/enclosure/v2/report_renders_2026-11-07/`.
  Verified framing and source geometry fingerprints; no enclosure geometry changes.
- 2026-11-18 — JP asked for a glove PCB and a matching enclosure. Read the KiCad schematic and
  extracted the real netlist (§13.1); it matches the firmware pins. Found: filter caps drawn to
  3V3 instead of GND, no flex connectors, no footprints on R/C/flex, PCB file is an empty stub,
  schematic is KiCad 10 but this PC has KiCad 9.0.7 (can't open it). Wrote the PCB/enclosure V3
  proposal and the list of inputs needed from JP (§13.4–13.5). **No design files changed yet.**
  JP also asked agents to log generously as they go (see `AGENTS.md` rule 5).
- 2026-11-18 — JP approved: carrier board, USB + spare 5V header, 5 × 2-pin JST-XH, socketed
  DevKit, SCL on GPIO22 (§13.6). Built **carrier PCB v1** by script in KiCad 9.0.7:
  68 × 46.5 mm, 2-layer, through-hole, MPU6050 module under the DevKit, caps to GND.
  DRC 0 violations / 0 unconnected; netlist read back and matches. Exported Gerber zip, drill
  files, BOM, assembled + bare STEP, 1:1 print PDF and six renders to `hardware/pcb/v1/`.
  Not ordered or built; paper fit check and MPU orientation check still to do (§13.7).
  Git: `hardware/` is still untracked, nothing committed.
- 2026-11-18 — JP: keep the IMU under the DevKit; fab will be Aivon (aivon.com, China).
  Modelled **enclosure V3** round the PCB with headless Blender 5.2 (MCP was not connected):
  74 × 58.9 × 29.4 mm body, 98 mm over the strap loops, base + lid, 0 mm³ collisions against
  41 electronics envelopes, STL check passes. Exported STLs, print zip, .blend, five previews
  and README to `hardware/enclosure/v3/`. Wrote the Aivon order settings into the PCB README.
  Answered JP's "is Blender good enough" question (§13.8). Nothing printed, uploaded or ordered.
- 2026-11-18 — JP: "Redo in FreeCAD". Installed FreeCAD 1.1.4 (winget, with JP's OK) and
  rebuilt enclosure V3 as CAD solids by script in `hardware/enclosure/v3/freecad/`: FCStd,
  STEP (parts + assembly with the PCB), STLs, A4 dimension sheet (SVG), print zip. Collision
  check against the real 254-solid PCB STEP: 0 mm³. **FreeCAD is now the master**; Blender
  V3 kept for pictures only, its STLs and zip deleted (§13.9). Still nothing printed.
- 2026-11-18 — JP: "Yes, redraw it". Schematic redrawn to match carrier PCB v1, in the same
  KiCad 9 project (`hardware/pcb/v1/aisl_glove_carrier.kicad_sch`, generated by
  `build_schematic.py`; PDF/PNG/SVG in `schematic/`). ERC 0/0. PCB script now links footprints
  to symbols and names the 29 unused pads; KiCad DRC with schematic parity: 0 violations,
  0 parity issues; own pad-by-pad check: 0 problems. Board regenerated, Gerbers and zip
  re-exported and proven geometrically identical to the earlier ones (§13.10). Old KiCad 10
  schematic left untouched. Still nothing ordered or printed.
- 2026-11-07 — (Claude, logged 2026-11-20) Filled Progress Report No. 7 (meeting 2026-10-28):
  `D:\Downloads\Progress Report (3) - filled.docx` (original `Progress Report (3).docx` untouched).
  Wrote "Data Extraction Mobile Deployment" (3 paragraphs: app pipeline, desktop/phone parity
  incl. 0.01 px, device results 27–28 fps Pad 6 / ~21 fps Nothing, 32–40 ms > 20 ms target,
  two-point calibration) + Figure 1 caption; "3D Modeling" (enclosure V2 122×86×42 mm, 146 mm
  with strap loops) + Figure 2 caption; JP's table row (tasks: two-point calibration, data
  collection protocol; deliverables: Android app on 3 devices, desktop/mobile parity). NOT
  touched: Petition Updates notes for SO4/SO6 (team must write what the adviser said); the
  report's two app screenshots are from an older build (glove "scanning"). Not rendered/
  checked in Word by Claude (no LibreOffice here); XML well-formed.
- 2026-11-20 — JP asked to put Andrei's four trained models (`multimodal_raw`,
  `multimodal_augmented_60reps`, `unimodal_vision_raw`, `unimodal_glove_raw`, PyTorch `.pth`)
  into the app with a separate, user-friendly inference window and a model picker, unimodal
  models switching off the unused input. Done (§14): checkpoints inspected without executing
  them; input layout / masks / pooling / padding worked out from the weights because no
  training code or data is available (evidence scripts in `models/forensics/`); weights exported
  to `shared/models/*.aislm`; forward pass written in Kotlin (`SignModel.kt`) and matched to real
  PyTorch 2.15 (max logit difference 2.7e-6 over 28 cases); `SignWindow.kt` builds the 120 × 79
  features with the recorder's own code; new `InferenceActivity` (Live + 4 s take, status chips,
  guided calibration, probability bars); glove connection and flex calibration now shared
  between the two screens (`AppSession`). Tests: `:core:test` 17/17, `:app:testDebugUnitTest`
  9/9, APK builds. Found and reported: the "glove-only" checkpoint was trained with 4 camera
  columns left in (mask boundary at 63 instead of 67), and the time column `t` is a model
  input. Not tested on a phone (none connected; emulator has no hypervisor driver here).
  Nothing committed or pushed.
- 2026-11-20 — (later the same day) Installed the app on the Nothing Phone A059 and the Galaxy
  A56 with adb. JP's "glove does not connect": it was Serial Bluetooth Terminal trying Bluetooth
  Classic serial against the BLE-only firmware; the app itself connects (49 Hz). Glove chip now
  says "connected · not used" for the vision model. Fixed a real bug JP hit: calibration on the
  Inference screen always stopped because the glove pauses ~0.7 s on `CAL` (§14.3). After the
  fix: full multimodal run on the A56, open hand → "B 90 %". Tests now `:core:test` 17/17,
  `:app:testDebugUnitTest` 10/10. JP: "commit all of it" → committed on `android-app` (not
  pushed).
- 2026-11-20 — Phone take CSV locations: phone `Android/data/com.aisla.app/files/data/<signer>/`
  (normalized: `files/data_norm/`); on PC `MediaPipe/data_phone_nothing/S01/` (glove worn),
  `MediaPipe/data_phone/S01/` (tablet, no glove), desktop `MediaPipe/data/S01/`.
