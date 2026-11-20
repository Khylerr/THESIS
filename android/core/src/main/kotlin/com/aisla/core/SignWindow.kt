package com.aisla.core

/**
 * Live data -> the input of a SignModel: one 4 s window turned into the 120 x 79 matrix of a
 * normalized take. It runs the recorder's own code on the window, in the same order as a
 * recorded take (FrameRow.build -> TakeSync.sync -> Normalizer.normalizeTake), so the model
 * sees exactly what a saved `_norm.csv` of those 4 s would contain.
 */
object SignWindow {
    const val SYNC_DIRECTION = "nearest"
    const val SYNC_TOLERANCE_SEC = 0.04   // same as the recorder (MainActivity / fslRecorder.py)
    val DURATION_SEC = Normalizer.RESAMPLE_SEC
    val STEP_SEC = 1.0 / Normalizer.RESAMPLE_HZ
    private val HAND_VALID_COL = Normalizer.FEATURE_COLUMNS.indexOf("g_valid")
    private val GLOVE_VALID_COL = Normalizer.FEATURE_COLUMNS.indexOf("glove_valid")

    /** One processed camera frame: capture time on the host clock (s) + the gloved hand, if found. */
    class Frame(val t: Double, val hand: Hand?)

    class Window(
        val x: Array<DoubleArray>,    // [120][79], Normalizer.FEATURE_COLUMNS order
        val nFrames: Int,             // camera frames (or grid steps) inside the window
        val handValidFrac: Double,    // share of the 120 steps with a tracked hand
        val gloveValidFrac: Double,   // share of the 120 steps with a calibrated glove sample
    )

    /** Start time of the live window whose last grid step falls on the newest frame/sample. */
    fun liveStart(tNewest: Double): Double = tNewest - (DURATION_SEC - STEP_SEC)

    /** No camera: one hand-less "frame" per grid step, so every step picks its nearest glove sample. */
    fun gridFrames(tRec0: Double): List<Frame> =
        List(Math.rint(DURATION_SEC * Normalizer.RESAMPLE_HZ).toInt()) { Frame(tRec0 + it * STEP_SEC, null) }

    /**
     * The window [tRec0, tRec0 + 4 s): frames outside it are ignored (same rule as TakeRecorder).
     * glove = any stretch of the glove buffer covering the window; flexCal = null -> glove invalid.
     */
    fun build(
        frames: List<Frame>, glove: List<GloveSample>, tRec0: Double,
        width: Double, height: Double, flexCal: FlexCalibration?,
    ): Window {
        val rows = ArrayList<FrameRow>()
        for (f in frames.sortedBy { it.t }) {
            val tRec = f.t - tRec0
            if (tRec < 0 || tRec >= DURATION_SEC) continue
            rows += FrameRow.build(rows.size, tRec, f.hand, null, logOther = false)
        }
        return fromRows(rows, glove, tRec0, width, height, flexCal)
    }

    fun fromRows(
        rows: List<FrameRow>, glove: List<GloveSample>, tRec0: Double,
        width: Double, height: Double, flexCal: FlexCalibration?,
    ): Window {
        val t1 = tRec0 + DURATION_SEC + SYNC_TOLERANCE_SEC
        val slice = glove.filter { it.t >= tRec0 - SYNC_TOLERANCE_SEC && it.t <= t1 }
        val synced = TakeSync.sync(rows, slice, tRec0, SYNC_DIRECTION, SYNC_TOLERANCE_SEC)
        val logOther = rows.any { it.o != null }
        val norm = Normalizer.normalizeTake(synced, logOther, width, height, flexCal)
        val x = norm.toTypedArray()
        return Window(
            x, rows.size,
            x.count { it[HAND_VALID_COL] == 1.0 }.toDouble() / x.size,
            x.count { it[GLOVE_VALID_COL] == 1.0 }.toDouble() / x.size,
        )
    }
}
