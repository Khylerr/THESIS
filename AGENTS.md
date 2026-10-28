# Instructions for AI agents (Codex, Claude, Sol, …)

1. **Read `HANDOFF.md` first.** It is the single source of truth: project, repo map, how to run,
   key decisions, status, next steps.
2. **After any progress, update `HANDOFF.md`** (§5 status, §6 next steps, §12 changelog) in the
   same change. Keep it short and factual.
3. Parity rule: anything that affects recorded data must change in Python
   (`MediaPipe/`) AND Kotlin (`android/core`) together, then
   `MediaPipe\venv\Scripts\python.exe MediaPipe/make_golden.py` and the `:core:test` Gradle
   task must pass. MediaPipe settings live only in `shared/mediapipe_config.json`.
4. Work on a branch, don't push or merge to `main` without asking JP.
