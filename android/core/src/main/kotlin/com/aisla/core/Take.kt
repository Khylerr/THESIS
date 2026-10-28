package com.aisla.core

/** Take CSV layout, identical to fslRecorder.py's make_header / output_columns. */
object TakeSchema {
    val COORDS: List<String> = (0 until N_LM).flatMap { i -> listOf("x$i", "y$i", "z$i") }
    val INT_COLS = setOf("frame", "detected", "other_detected")

    fun header(logOther: Boolean): List<String> {
        val h = mutableListOf("frame", "t_sec", "detected", "hand_conf")
        h += COORDS
        if (logOther) {
            h += "other_detected"
            h += COORDS.map { "o_$it" }
        }
        return h
    }

    fun outputColumns(logOther: Boolean): List<String> = header(logOther) + GLOVE_COLS + "glove_dt_ms"
}

private val NAN63 = DoubleArray(3 * N_LM) { Double.NaN }

/** One camera frame of a take (before sync). o == null when the other hand is not logged. */
class FrameRow(
    val frame: Int,
    val tSec: Double,
    val detected: Int,
    val handConf: Double,
    val g: DoubleArray,
    val otherDetected: Int,
    val o: DoubleArray?,
) {
    companion object {
        /** fslRecorder.build_row: one row per frame, always; missing hand -> 0 and NaN. */
        fun build(frameIdx: Int, tRec: Double, glove: Hand?, other: Hand?, logOther: Boolean): FrameRow {
            val tSec = PyFormat.pyRound(tRec, 4)
            val o = if (logOther) (other?.xyz?.copyOf() ?: NAN63.copyOf()) else null
            return if (glove != null) {
                FrameRow(frameIdx, tSec, 1, PyFormat.pyRound(glove.score, 4), glove.xyz.copyOf(),
                    if (other != null) 1 else 0, o)
            } else {
                FrameRow(frameIdx, tSec, 0, Double.NaN, NAN63.copyOf(), if (other != null) 1 else 0, o)
            }
        }
    }
}

/** A frame after sync: + the matched glove sample (NaN if none within tolerance). */
class SyncedRow(val frame: FrameRow, val glove: DoubleArray, val gloveTSec: Double, val gloveDtMs: Double) {

    /** All output columns as numbers, in TakeSchema.outputColumns order (what the CSV parses back to). */
    fun values(): DoubleArray {
        val f = frame
        val out = ArrayList<Double>(150)
        out += f.frame.toDouble()
        out += f.tSec
        out += f.detected.toDouble()
        out += f.handConf
        f.g.forEach { out += it }
        if (f.o != null) {
            out += f.otherDetected.toDouble()
            f.o.forEach { out += it }
        }
        glove.forEach { out += it }
        out += gloveDtMs
        return out.toDoubleArray()
    }
}

object TakeSync {

    /**
     * fslRecorder.sync_streams: every camera frame gets the glove sample closest in time
     * (pandas.merge_asof, direction/tolerance as given), on the time axis "seconds since
     * recording start". glove = the buffer slice for this take, in buffer order.
     */
    fun sync(
        rows: List<FrameRow>,
        glove: List<GloveSample>,
        tRec0: Double,
        direction: String = "nearest",
        tolerance: Double = 0.04,
    ): List<SyncedRow> {
        val frames = rows.sortedBy { it.tSec }
        val g = glove.map { Pair(it.t - tRec0, it) }.sortedBy { it.first }
        val left = DoubleArray(frames.size) { frames[it].tSec }
        val right = DoubleArray(g.size) { g[it].first }
        val idx = AsofJoin.join(left, right, direction, tolerance)
        return frames.mapIndexed { i, fr ->
            val j = idx[i]
            if (j >= 0) {
                val gt = g[j].first
                SyncedRow(fr, g[j].second.values.copyOf(), gt, PyFormat.npRound((gt - fr.tSec) * 1000, 1))
            } else {
                SyncedRow(fr, DoubleArray(GLOVE_COLS.size) { Double.NaN }, Double.NaN, Double.NaN)
            }
        }
    }

    /** Writes the take CSV exactly like pandas DataFrame.to_csv(index=False) in the recorder. */
    fun writeCsv(out: Appendable, rows: List<SyncedRow>, logOther: Boolean) {
        val cols = TakeSchema.outputColumns(logOther)
        out.append(cols.joinToString(",")).append('\n')
        val sb = StringBuilder(4096)
        for (r in rows) {
            sb.setLength(0)
            val v = r.values()
            for (k in cols.indices) {
                if (k > 0) sb.append(',')
                if (cols[k] in TakeSchema.INT_COLS) sb.append(v[k].toInt()) else sb.append(PyFormat.csvCell(v[k]))
            }
            out.append(sb).append('\n')
        }
    }
}
