package com.aisla.core

/**
 * One take: countdown, then a fixed-length recording. Port of fslRecorder.record_take's
 * timing logic: t_rec0 = press time + countdown; every frame with 0 <= t - t_rec0 < record_sec
 * becomes a row; the first frame at or past record_sec ends the take (and is not stored).
 * Times are seconds on the host clock (the same clock as the glove samples).
 */
class TakeRecorder(
    val recordSec: Double = 4.0,
    val countdownSec: Double = 3.0,
    val logOther: Boolean = true,
) {
    sealed class Status {
        object Idle : Status()
        class Countdown(val secondsLeft: Double) : Status()
        class Recording(val secondsLeft: Double) : Status()
        class Finished(
            val rows: List<FrameRow>,
            val perf: List<Quality.Perf>,
            val tRec0: Double,
            val tEnd: Double,
        ) : Status()
    }

    var active = false
        private set
    var tRec0 = 0.0
        private set
    private val rows = ArrayList<FrameRow>()
    private val perf = ArrayList<Quality.Perf>()
    private var frameIdx = 0

    fun start(now: Double) {
        tRec0 = now + countdownSec
        rows.clear()
        perf.clear()
        frameIdx = 0
        active = true
    }

    fun abort() {
        active = false
        rows.clear()
        perf.clear()
    }

    /** Call once per processed camera frame (t = its capture time). */
    fun onFrame(t: Double, glove: Hand?, other: Hand?, procMs: Double, skipped: Int): Status {
        if (!active) return Status.Idle
        val tRec = t - tRec0
        if (tRec >= recordSec) {   // deadline checked before storing the frame
            active = false
            return Status.Finished(ArrayList(rows), ArrayList(perf), tRec0, t)
        }
        if (tRec < 0) return Status.Countdown(-tRec)
        rows += FrameRow.build(frameIdx, tRec, glove, other, logOther)
        perf += Quality.Perf(procMs, if (frameIdx > 0) skipped else 0)
        frameIdx++
        return Status.Recording(recordSec - tRec)
    }
}
