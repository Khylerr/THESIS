package com.aisla.core

import com.aisla.core.PyFormat.pyFixed
import com.aisla.core.PyFormat.pyPercent0
import com.aisla.core.PyFormat.pyRound

/** Quality gates and per-take stats: port of fslRecorder.quality(), same keys and warnings. */
object Quality {
    const val MIN_FPS = 27.0
    const val MIN_DETECTED = 0.90
    const val MAX_GAP_SEC = 0.10
    const val MIN_GLOVE_HZ = 40.0
    const val MIN_GLOVE_MATCHED = 0.95
    const val MAX_GLOVE_GAP_SEC = 0.10
    const val MAX_VISION_MS = 20.0

    /** perf = per recorded frame (proc_ms, camera frames skipped). */
    class Perf(val procMs: Double, val skipped: Int)

    fun compute(
        df: List<SyncedRow>,
        glove: List<GloveSample>,
        tRec0: Double,
        recordSec: Double,
        perf: List<Perf>?,
        handStats: Map<String, Any?>?,
    ): LinkedHashMap<String, Any?> {
        val n = df.size
        if (n < 2) {
            return linkedMapOf(
                "n_frames" to n, "fps" to 0.0, "detected_frac" to 0.0, "max_gap_sec" to null,
                "glove_samples" to 0, "glove_hz" to 0.0, "glove_matched_frac" to 0.0,
                "glove_max_gap_sec" to null, "glove_max_abs_dt_ms" to null,
                "glove_packets_dropped" to null, "glove_delay_above_min" to null,
                "vision_latency" to null, "hand_picking" to handStats,
                "warnings" to listOf("too few frames"),
            )
        }
        val ts = df.map { it.frame.tSec }
        val span = ts.last() - ts.first()
        val fps = if (span > 0) (n - 1) / span else 0.0
        var maxGap = Double.NEGATIVE_INFINITY
        for (i in 1 until n) maxGap = maxOf(maxGap, ts[i] - ts[i - 1])
        val det = df.sumOf { it.frame.detected }.toDouble() / n

        // glove stream inside the recording window only (buffer order, like the recorder)
        val gIn = glove.map { it.t - tRec0 }.filter { it >= 0 && it < recordSec }
        val gloveHz = gIn.size / recordSec
        var gloveGap: Double? = null
        if (gIn.size > 1) {
            var m = Double.NEGATIVE_INFINITY
            for (i in 1 until gIn.size) m = maxOf(m, gIn[i] - gIn[i - 1])
            gloveGap = m
        }
        val matched = df.count { !it.glove[0].isNaN() }.toDouble() / n
        val absDt = df.map { it.gloveDtMs }.filter { !it.isNaN() }.map { Math.abs(it) }
        val maxDt: Double? = if (absDt.isNotEmpty()) absDt.max() else null

        // transport: packets lost (BLE seq gaps) and per-packet radio delay
        val inTake = glove.filter { it.t - tRec0 >= 0 && it.t - tRec0 < recordSec }
        var dropped: Int? = null
        var delay: LinkedHashMap<String, Any?>? = null
        if (inTake.size > 1 && inTake.all { it.seq >= 0 }) {
            var sum = 0
            for (i in 1 until inTake.size) {
                val gap = Math.floorMod(inTake[i].seq - inTake[i - 1].seq - 1, 65536)
                if (gap < 1000) sum += gap
            }
            dropped = sum
            val d = DoubleArray(inTake.size) { (inTake[it].tArrival - inTake[it].t) * 1000 }
            delay = linkedMapOf(
                "median_ms" to pyRound(Stats.median(d), 1),
                "p95_ms" to pyRound(Stats.percentile(d, 95.0), 1),
                "max_ms" to pyRound(Stats.max(d), 1),
            )
        }

        val warnings = mutableListOf<String>()
        if (fps < MIN_FPS) warnings += "low fps (${pyFixed(fps, 1)})"
        if (det < MIN_DETECTED) warnings += "low detection (${pyPercent0(det)})"
        if (maxGap > MAX_GAP_SEC) warnings += "gap of ${pyFixed(maxGap * 1000, 0)} ms between frames"
        if (gloveHz < MIN_GLOVE_HZ) warnings += "low glove rate (${pyFixed(gloveHz, 0)} Hz)"
        if (matched < MIN_GLOVE_MATCHED) warnings += "only ${pyPercent0(matched)} of frames have glove data"
        if (gloveGap != null && gloveGap > MAX_GLOVE_GAP_SEC) warnings += "glove silent for ${pyFixed(gloveGap * 1000, 0)} ms"
        if (dropped != null && dropped != 0) warnings += "$dropped glove packets lost"

        // vision speed: per recorded frame
        var vision: LinkedHashMap<String, Any?>? = null
        if (!perf.isNullOrEmpty()) {
            val pm = DoubleArray(perf.size) { perf[it].procMs }
            val median = pyRound(Stats.median(pm), 1)
            vision = linkedMapOf(
                "n_frames" to pm.size,
                "median_ms" to median,
                "p95_ms" to pyRound(Stats.percentile(pm, 95.0), 1),
                "max_ms" to pyRound(Stats.max(pm), 1),
                "within_20ms_frac" to pyRound(pm.count { it <= MAX_VISION_MS }.toDouble() / pm.size, 4),
                "camera_frames_skipped" to perf.sumOf { it.skipped },
            )
            if (median > MAX_VISION_MS) {
                warnings += "vision ${pyFixed(median, 0)} ms/frame (> ${pyFixed(MAX_VISION_MS, 0)})"
            }
        }
        return linkedMapOf(
            "n_frames" to n,
            "fps" to pyRound(fps, 2),
            "detected_frac" to pyRound(det, 4),
            "max_gap_sec" to pyRound(maxGap, 4),
            "glove_samples" to gIn.size,
            "glove_hz" to pyRound(gloveHz, 1),
            "glove_matched_frac" to pyRound(matched, 4),
            "glove_max_gap_sec" to gloveGap?.let { pyRound(it, 4) },
            "glove_max_abs_dt_ms" to maxDt,
            "glove_packets_dropped" to dropped,
            "glove_delay_above_min" to delay,
            "vision_latency" to vision,
            "hand_picking" to handStats,
            "warnings" to warnings,
        )
    }
}
