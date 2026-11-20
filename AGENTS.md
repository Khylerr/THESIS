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
5. **Log generously, as you go** (JP, 2026-11-18: "log everything in agents u think u need,
   like just as u go, make sure u log a lot so when i use a lower model, it'll have more context
   for that chat"). Don't wait for the end of a task. Write into `HANDOFF.md` while working:
   what you found (with the file it came from), what you measured or verified and how, what you
   decided and why, what JP said (quote + date), what is still unknown, and what you tried that
   did not work. Mark proposals as proposals until JP approves them. Assume the next reader is
   a smaller model with none of this chat: spell out file paths, pin numbers, dimensions,
   versions and commands instead of "see above". Hardware (circuit, PCB, enclosure) lives in
   `HANDOFF.md` §8, §9 and §13.
