# Sign models (CNN-BiLSTM) and how they get into the app

Full story and evidence: `HANDOFF.md` section 14. Short version:

| Path | What |
|---|---|
| `checkpoints/*.pth` | The four PyTorch checkpoints from Andrei (2026-11-16). Classes: B, E, F, L, R, U, i-love-you. |
| `pth_reader.py` | Reads a checkpoint **without torch** and without running pickle code (only the tensor types are allowed). |
| `export_models.py` | Checkpoints → `../shared/models/<id>.aislm`, the files the Android app bundles. **Holds every setting a checkpoint does not store** (input columns, masked columns, conv padding, pooling, which inputs a model needs, its name in the app). |
| `make_model_golden.py` | Runs the checkpoints in **real PyTorch** and writes `../shared/golden/sign_model/`. The Kotlin test `SignModelTest` must reproduce these numbers. Needs `torch` + `numpy`. |
| `forensics/` | The three scripts that worked out the input layout from the weights (no training code was available). |

## Model input (inferred from the weights, not from training code)

One sample = one normalized take = **120 steps × 79 columns**, exactly a `_norm.csv`
(`aisl_norm.py` / `Normalizer.kt`, spec v3), all columns in file order, no scaling:

`t, g_valid, g_x0 … g_z20, g_px, g_py, glove_valid, flex1 … flex5, acc_x, acc_y, acc_z, gyro_x, gyro_y, gyro_z`

Network: Conv1d(79→32, k=3, padding 1) → BatchNorm → ReLU → BiLSTM(32→32) → output at the
**last time step** → BatchNorm → Linear(64→7).
Unimodal models = same network with columns zeroed: vision zeroes columns 63–78,
glove zeroes columns 0–62.

## Adding or replacing a model

1. Put `<id>.pth` in `checkpoints/` (same layers: `conv1d, bn1, bilstm, bn2, fc`).
2. Add / edit its entry in `MODELS` in `export_models.py` (title, `camera` / `glove` =
   `required | optional | off`, `zero_cols`).
3. `python models/export_models.py` (numpy only).
4. `<python with torch> models/make_model_golden.py`
   (once: `python -m venv .venv-torch`, then
   `.venv-torch\Scripts\pip install torch numpy --index-url https://download.pytorch.org/whl/cpu --extra-index-url https://pypi.org/simple`).
5. In `android/`: Gradle `:core:test :app:testDebugUnitTest :app:assembleDebug`. The app
   lists every `.aislm` by itself; no app code changes.

If the training code shows a different padding / pooling / mask than the ones inferred here,
change it in `export_models.py` (`COMMON`, `MODELS`) and repeat steps 3–5. A different
*pooling* also needs a new branch in `SignModel.kt` and `make_model_golden.py` (both refuse
unknown values instead of guessing).
