package com.aisla.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * The Kotlin forward pass (SignModel) must give what real PyTorch gives for the same checkpoint
 * and the same input. Reference: shared/golden/sign_model/, written by
 * models/make_model_golden.py (torch.load of models/checkpoints/<id>.pth + a torch nn.Module).
 * Also checks that SignWindow builds the same features as a recorded take.
 */
class SignModelTest {
    private val goldenDir = File(System.getProperty("golden.dir") ?: "../../shared/golden")
    private val modelDir = File(System.getProperty("models.dir") ?: "../../shared/models")
    private val ids = listOf("multimodal_raw", "multimodal_augmented_60reps", "unimodal_vision_raw", "unimodal_glove_raw")

    private fun model(id: String): SignModel {
        val f = File(modelDir, "$id.aislm")
        assertTrue("missing $f (run models/export_models.py)", f.isFile)
        return SignModel.parse(f.readBytes())
    }

    private fun golden(name: String): File {
        val f = File(goldenDir, "sign_model/$name")
        assertTrue("missing $f (run models/make_model_golden.py)", f.isFile)
        return f
    }

    /** inputs.f32: float32 little-endian, cases x 120 x 79. */
    private fun inputs(): List<Array<DoubleArray>> {
        val meta = golden("inputs_shape.txt").readText().trim().split(' ').map { it.toInt() }
        val (n, t, c) = meta
        val buf = ByteBuffer.wrap(golden("inputs.f32").readBytes()).order(ByteOrder.LITTLE_ENDIAN)
        assertEquals(n * t * c * 4, buf.remaining())
        return List(n) { Array(t) { DoubleArray(c) { buf.float.toDouble() } } }
    }

    @Test
    fun headersDescribeTheFourModels() {
        val all = ids.map { model(it) }
        for (m in all) {
            assertEquals(listOf("B", "E", "F", "L", "R", "U", "i-love-you"), m.classes)
            assertEquals(Normalizer.FEATURE_COLUMNS.size, m.inFeatures)
            assertEquals(Normalizer.SPEC_VERSION, m.featureSpecVersion)
            assertEquals(Math.rint(Normalizer.RESAMPLE_SEC * Normalizer.RESAMPLE_HZ).toInt(), m.seqLen)
            assertEquals(Normalizer.RESAMPLE_HZ, m.hz, 0.0)
        }
        assertEquals(listOf(1, 2, 3, 4), all.map { it.order })
        val cols = Normalizer.FEATURE_COLUMNS
        fun zeroed(id: String) = model(id).zeroCols.withIndex().filter { it.value }.map { cols[it.index] }
        assertEquals(emptyList<String>(), zeroed("multimodal_raw"))
        assertEquals(emptyList<String>(), zeroed("multimodal_augmented_60reps"))
        // the masks the checkpoints were trained with (HANDOFF 14.2): [63:] and [:63]
        assertEquals(cols.subList(63, 79), zeroed("unimodal_vision_raw"))
        assertEquals(cols.subList(0, 63), zeroed("unimodal_glove_raw"))
        assertEquals("g_y20", cols[63])
        assertEquals("glove_valid", cols[67])
        assertEquals(SignModel.Need.OFF, model("unimodal_vision_raw").glove)
        assertEquals(SignModel.Need.REQUIRED, model("unimodal_vision_raw").camera)
        assertEquals(SignModel.Need.REQUIRED, model("unimodal_glove_raw").glove)
        assertEquals(SignModel.Need.OPTIONAL, model("unimodal_glove_raw").camera)
    }

    @Test
    fun forwardPassMatchesPyTorch() {
        val xs = inputs()
        assertTrue(xs.size >= 4)
        for (id in ids) {
            val m = model(id)
            val t = Csv.read(golden("${id}_expected.csv"))
            assertEquals(xs.size, t.rows.size)
            val n = m.classes.size
            var worst = 0.0
            for ((i, r) in t.rows.withIndex()) {
                val p = m.predict(xs[i])
                for (k in 0 until n) {
                    val expLogit = r[1 + k].toDouble()
                    val expProb = r[1 + n + k].toDouble()
                    worst = maxOf(worst, Math.abs(expLogit - p.logits[k]))
                    if (Math.abs(expLogit - p.logits[k]) > 2e-4) {
                        fail("$id case ${r[0]} logit ${m.classes[k]}: PyTorch $expLogit, Kotlin ${p.logits[k]}")
                    }
                    assertEquals("$id case ${r[0]} prob ${m.classes[k]}", expProb, p.probs[k], 2e-5)
                }
                assertEquals("$id case ${r[0]} top class", r[1 + 2 * n], m.classes[p.top])
                assertEquals(1.0, p.probs.sum(), 1e-12)
            }
            println("$id: ${t.rows.size} cases, largest |logit difference| vs PyTorch = $worst")
        }
    }

    @Test
    fun maskedColumnsCannotChangeTheResult() {
        val x = inputs()[0]
        for (id in listOf("unimodal_vision_raw", "unimodal_glove_raw")) {
            val m = model(id)
            val base = m.logits(x)
            val changed = Array(x.size) { t -> DoubleArray(x[t].size) { c -> if (m.zeroCols[c]) 1000.0 + t + c else x[t][c] } }
            assertTrue("$id", base.contentEquals(m.logits(changed)))
            // ... while a live column does
            val live = m.zeroCols.indexOfFirst { !it }
            val moved = Array(x.size) { t -> x[t].copyOf().also { it[live] += 1.0 } }
            assertFalse("$id live column $live", base.contentEquals(m.logits(moved)))
        }
    }

    @Test
    fun brokenFilesAndInputsAreRejected() {
        val bytes = File(modelDir, "multimodal_raw.aislm").readBytes()
        fun rejects(what: String, block: () -> Unit) {
            try {
                block()
            } catch (e: IllegalArgumentException) {
                return
            }
            fail("accepted: $what")
        }
        rejects("truncated file") { SignModel.parse(bytes.copyOf(bytes.size - 4)) }
        rejects("extra bytes") { SignModel.parse(bytes + ByteArray(4)) }
        rejects("wrong magic") { SignModel.parse(bytes.copyOf().also { it[0] = 'X'.code.toByte() }) }
        val m = SignModel.parse(bytes)
        rejects("wrong width") { m.logits(arrayOf(DoubleArray(78))) }
        rejects("NaN") { m.logits(Array(120) { DoubleArray(79) }.also { it[5][7] = Double.NaN }) }
        rejects("empty") { m.logits(arrayOf()) }
    }

    // ------------------------------------------------------------------ SignWindow
    private fun d(s: String) = PyFormat.parseCell(s)

    private fun same(what: String, expected: Double, actual: Double) {
        val ok = (expected.isNaN() && actual.isNaN()) || expected.toRawBits() == actual.toRawBits()
        if (!ok) fail("$what: expected ${PyFormat.pyRepr(expected)} got ${PyFormat.pyRepr(actual)}")
    }

    private fun frameHand(cells: List<String>, at: Int): Hand? {
        if (cells[at] != "1") return null
        return Hand("Right", d(cells[at + 1]), DoubleArray(63) { d(cells[at + 2 + it]) })
    }

    /**
     * The golden take (frames + glove buffer of the recorder test): SignWindow must give the same
     * 120 x 79 numbers as normalizing the take CSV that the Python recorder code wrote for it.
     */
    @Test
    fun windowEqualsTheNormalizedRecordedTake() {
        val meta = File(goldenDir, "take_meta.json").readText()
        val tRec0 = d(Regex("\"t_rec0\"\\s*:\\s*\"?([-0-9.eE+]+)\"?").find(meta)!!.groupValues[1])
        val frameCells = Csv.read(File(goldenDir, "take_frames_input.csv")).rows
        val glove = Csv.read(File(goldenDir, "take_glove_input.csv")).rows.map { c ->
            GloveSample(d(c[0]), DoubleArray(11) { d(c[1 + it]) }, d(c[12]), c[13].toInt(), c[14].toInt())
        }
        val cal = FlexCalibration(doubleArrayOf(10.0, -20.0, 5.0, 0.0, 30.0), doubleArrayOf(900.0, 700.0, 650.0, 800.0, 500.0))
        val w = 480.0
        val h = 640.0

        val (header, takeRows) = Csv.readNumbers(File(goldenDir, "take_expected.csv"))
        val expected = Normalizer.normalizeTake(header, takeRows, w, h, cal)

        val rows = frameCells.map { c -> FrameRow.build(c[0].toInt(), d(c[1]), frameHand(c, 2), null, logOther = false) }
        val win = SignWindow.fromRows(rows, glove, tRec0, w, h, cal)
        assertEquals(120, win.x.size)
        assertEquals(expected.size, win.x.size)
        for (i in expected.indices) for (k in expected[i].indices) {
            same("step $i ${Normalizer.FEATURE_COLUMNS[k]}", expected[i][k], win.x[i][k])
        }
        assertEquals(rows.size, win.nFrames)
        assertEquals(expected.count { it[1] == 1.0 } / 120.0, win.handValidFrac, 0.0)
        assertEquals(expected.count { it[67] == 1.0 } / 120.0, win.gloveValidFrac, 0.0)
        assertTrue("golden take has no tracked hand", win.handValidFrac > 0.5)
        assertTrue("golden take has no glove data", win.gloveValidFrac > 0.5)

        // same take through build(): frames on the host clock, plus frames outside the window
        val frames = frameCells.map { c -> SignWindow.Frame(tRec0 + d(c[1]), frameHand(c, 2)) } +
            listOf(SignWindow.Frame(tRec0 - 0.5, null), SignWindow.Frame(tRec0 + 4.05, null), SignWindow.Frame(tRec0 + 9.0, null))
        val viaBuild = SignWindow.build(frames.shuffled(java.util.Random(1)), glove, tRec0, w, h, cal)
        assertEquals(rows.size, viaBuild.nFrames)
        for (i in expected.indices) for (k in expected[i].indices) {
            assertEquals("build step $i ${Normalizer.FEATURE_COLUMNS[k]}", expected[i][k], viaBuild.x[i][k], 1e-9)
        }

        // no calibration -> glove columns invalid and zero, hand columns unchanged
        val noCal = SignWindow.fromRows(rows, glove, tRec0, w, h, null)
        assertEquals(0.0, noCal.gloveValidFrac, 0.0)
        for (i in 0 until 120) {
            for (k in 67 until 79) assertEquals(0.0, noCal.x[i][k], 0.0)
            for (k in 0 until 67) same("no-cal step $i col $k", expected[i][k], noCal.x[i][k])
        }
    }

    @Test
    fun gloveOnlyWindowUsesTheGridAndLeavesTheHandEmpty() {
        val t0 = 5000.0
        val cal = FlexCalibration(DoubleArray(5) { 0.0 }, DoubleArray(5) { 1000.0 })
        // 50 Hz glove, flex1 ramps 0 -> 1000 over the 4 s, acc_x = 2
        val glove = List(260) { i ->
            val t = t0 - 0.5 + i * 0.02
            val v = DoubleArray(11)
            v[0] = (t - t0) * 250.0
            v[5] = 2.0
            GloveSample(t, v, t, i, 0)
        }
        assertEquals(t0, SignWindow.liveStart(t0 + 4.0 - 1.0 / 30), 1e-9)
        val frames = SignWindow.gridFrames(t0)
        assertEquals(120, frames.size)
        val win = SignWindow.build(frames, glove, t0, 1.0, 1.0, cal)
        assertEquals(120, win.nFrames)
        assertEquals(0.0, win.handValidFrac, 0.0)
        assertEquals(1.0, win.gloveValidFrac, 0.0)
        val flex1 = Normalizer.FEATURE_COLUMNS.indexOf("flex1")
        val accX = Normalizer.FEATURE_COLUMNS.indexOf("acc_x")
        for (k in 0 until 120) {
            assertEquals(k / 30.0, win.x[k][0], 0.0)
            for (c in 1 until 67) assertEquals(0.0, win.x[k][c], 0.0)
            assertEquals(1.0, win.x[k][67], 0.0)
            // nearest 50 Hz sample is at most 10 ms away: 10 ms * 0.25 / s = 0.0025 (+ rounding of t)
            assertEquals("flex1 step $k", k / 30.0 * 0.25, win.x[k][flex1], 0.004)
            assertEquals(2.0, win.x[k][accX], 0.0)
        }
        // glove silent -> everything invalid, still a well-formed window
        val silent = SignWindow.build(frames, emptyList(), t0, 1.0, 1.0, cal)
        assertEquals(0.0, silent.gloveValidFrac, 0.0)
        assertEquals(120, silent.x.size)
    }
}
