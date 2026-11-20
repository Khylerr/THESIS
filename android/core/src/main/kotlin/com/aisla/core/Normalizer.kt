package com.aisla.core

/**
 * Cross-device feature normalization, spec v3 (glove hand only; two-point flex calibration). Line-for-line port of MediaPipe/aisl_norm.py;
 * both are checked against shared/golden/norm_expected (NormalizerTest). Change both or neither.
 *
 * Per hand (raw MediaPipe x,y,z of the mirrored upright image of size W x H):
 *   X = x*W, Y = y*H, Z = z*W;  s = mean 3D distance wrist -> MCP 5, 9, 13, 17
 *   shape    = (P_i - P_0) / s                         (63 values)
 *   position = (X_0 - W/2) / min(W,H), (Y_0 - H/2) / min(W,H)   (2 values)
 * Glove: flex1..5 = (v - open) / (closed - open) from the take's FlexCalibration (none -> glove
 * invalid), IMU as recorded. Time: resampled to a fixed 30 Hz grid over 4 s.
 */
object Normalizer {
    const val SPEC_VERSION = 3   // v2: other hand removed (79 columns); v3: two-point flex calibration
    const val RESAMPLE_HZ = 30.0
    const val RESAMPLE_SEC = 4.0
    const val MAX_GAP_SEC = 0.10
    const val MIN_PALM_PX = 1e-6
    private val PALM_MCPS = intArrayOf(5, 9, 13, 17)

    private fun handFeatureNames(prefix: String): List<String> =
        TakeSchema.COORDS.map { prefix + it } + listOf(prefix + "px", prefix + "py")

    val HAND_FEATS = handFeatureNames("").size   // 65

    val FEATURE_COLUMNS: List<String> =
        listOf("t", "g_valid") + handFeatureNames("g_") +
            listOf("glove_valid") + GLOVE_COLS

    /** 63 raw values -> 65 features, or null if the hand is missing or degenerate. */
    fun normalizeHand(xyz: DoubleArray, width: Double, height: Double): DoubleArray? {
        if (xyz.size != 3 * N_LM || xyz.any { it.isNaN() || it.isInfinite() }) return null
        val w = width
        val h = height
        val px = DoubleArray(N_LM) { xyz[3 * it] * w }
        val py = DoubleArray(N_LM) { xyz[3 * it + 1] * h }
        val pz = DoubleArray(N_LM) { xyz[3 * it + 2] * w }

        fun dist0(j: Int): Double {
            val dx = px[j] - px[0]
            val dy = py[j] - py[0]
            val dz = pz[j] - pz[0]
            return Math.sqrt(dx * dx + dy * dy + dz * dz)
        }

        val s = (dist0(PALM_MCPS[0]) + dist0(PALM_MCPS[1]) + dist0(PALM_MCPS[2]) + dist0(PALM_MCPS[3])) / 4.0
        if (!(s > MIN_PALM_PX)) return null
        val f = DoubleArray(HAND_FEATS)
        for (i in 0 until N_LM) {
            f[3 * i] = (px[i] - px[0]) / s
            f[3 * i + 1] = (py[i] - py[0]) / s
            f[3 * i + 2] = (pz[i] - pz[0]) / s
        }
        val m = Math.min(w, h)
        f[3 * N_LM] = (px[0] - w / 2.0) / m
        f[3 * N_LM + 1] = (py[0] - h / 2.0) / m
        return f
    }

    /** 11 glove values with flex normalized, or null (no sample in this frame / no calibration). */
    fun gloveValues(v: DoubleArray, flexCal: FlexCalibration?): DoubleArray? {
        if (flexCal == null || v.size != GLOVE_COLS.size || v.any { it.isNaN() || it.isInfinite() }) return null
        val flex = flexCal.normalize(v)
        return DoubleArray(v.size) { if (it < 5) flex[it] else v[it] }
    }

    class Step(val valid: Boolean, val values: DoubleArray)

    /** Irregular frames -> fixed grid t_k = k / hz (see aisl_norm.resample). */
    fun resample(
        times: DoubleArray,
        feats: List<DoubleArray?>,
        nFeats: Int,
        hz: Double = RESAMPLE_HZ,
        duration: Double = RESAMPLE_SEC,
        maxGap: Double = MAX_GAP_SEC,
    ): List<Step> {
        for (i in 1 until times.size) require(times[i] >= times[i - 1]) { "frame times must be non-decreasing" }
        val nOut = Math.rint(duration * hz).toInt()
        val good = feats.indices.filter { feats[it] != null }
        val half = maxGap / 2.0
        val out = ArrayList<Step>(nOut)
        for (k in 0 until nOut) {
            val g = k / hz
            var a = -1   // last valid frame with t <= g
            var b = -1   // first valid frame with t > g
            for (i in good) {
                if (times[i] <= g) {
                    a = i
                } else {
                    b = i
                    break
                }
            }
            if (a >= 0 && times[a] == g) {
                out += Step(true, feats[a]!!.copyOf())
            } else if (a >= 0 && b >= 0 && times[b] - times[a] <= maxGap) {
                val w = (g - times[a]) / (times[b] - times[a])
                val fa = feats[a]!!
                val fb = feats[b]!!
                out += Step(true, DoubleArray(nFeats) { j -> fa[j] + w * (fb[j] - fa[j]) })
            } else {
                val da = if (a >= 0) g - times[a] else Double.POSITIVE_INFINITY
                val db = if (b >= 0) times[b] - g else Double.POSITIVE_INFINITY
                out += when {
                    da <= db && da <= half -> Step(true, feats[a]!!.copyOf())
                    db < da && db <= half -> Step(true, feats[b]!!.copyOf())
                    else -> Step(false, DoubleArray(nFeats))
                }
            }
        }
        return out
    }

    /** Take rows (recorder CSV layout, values as parsed) -> FEATURE_COLUMNS rows on the grid. */
    fun normalizeTake(
        header: List<String>, rows: List<DoubleArray>, width: Double, height: Double, flexCal: FlexCalibration?,
    ): List<DoubleArray> {
        val col = header.withIndex().associate { it.value to it.index }
        fun idx(prefix: String) = TakeSchema.COORDS.map { col.getValue(prefix + it) }.toIntArray()
        val gIdx = idx("")
        val glIdx = if (GLOVE_COLS.all { it in col }) GLOVE_COLS.map { col.getValue(it) }.toIntArray() else null
        val tCol = col.getValue("t_sec")
        val detCol = col.getValue("detected")

        val times = DoubleArray(rows.size) { rows[it][tCol] }
        val gF = rows.map { r -> if (r[detCol] == 1.0) normalizeHand(pick(r, gIdx), width, height) else null }
        val glF = rows.map { r -> if (glIdx != null) gloveValues(pick(r, glIdx), flexCal) else null }

        val g = resample(times, gF, HAND_FEATS)
        val gl = resample(times, glF, GLOVE_COLS.size)
        return List(g.size) { k ->
            val row = DoubleArray(FEATURE_COLUMNS.size)
            var p = 0
            row[p++] = k / RESAMPLE_HZ
            row[p++] = if (g[k].valid) 1.0 else 0.0
            for (v in g[k].values) row[p++] = v
            row[p++] = if (gl[k].valid) 1.0 else 0.0
            for (v in gl[k].values) row[p++] = v
            row
        }
    }

    /** Synced take straight from memory (same numbers the saved CSV parses back to). */
    fun normalizeTake(
        rows: List<SyncedRow>, logOther: Boolean, width: Double, height: Double, flexCal: FlexCalibration?,
    ): List<DoubleArray> = normalizeTake(TakeSchema.outputColumns(logOther), rows.map { it.values() }, width, height, flexCal)

    fun writeCsv(out: Appendable, rows: List<DoubleArray>) {
        out.append(FEATURE_COLUMNS.joinToString(",")).append('\n')
        for (r in rows) out.append(r.joinToString(",") { PyFormat.pyRepr(it) }).append('\n')
    }

    private fun pick(r: DoubleArray, idx: IntArray) = DoubleArray(idx.size) { r[idx[it]] }
}
