package com.aisla.core

import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * One trained sign classifier (.aislm, written by models/export_models.py from a PyTorch
 * checkpoint) and its forward pass in plain Kotlin, eval mode:
 *
 *   x [T][in]  --zero the model's masked columns-->
 *   Conv1d(in -> C, kernel K, zero padding P) -> BatchNorm -> ReLU          (dropout = identity)
 *   -> bidirectional LSTM(C -> H) -> the output at the LAST time step [2H]  (pooling "last_step")
 *   -> BatchNorm -> Linear(2H -> classes) -> softmax
 *
 * Checked against real PyTorch on the same inputs by SignModelTest (shared/golden/sign_model,
 * made by models/make_model_golden.py). The input layout, mask, padding and pooling are read
 * from the file header, never assumed here: an unknown value is an error, not a guess.
 */
class SignModel private constructor(val header: Map<String, String>, private val w: Map<String, FloatArray>) {

    enum class Need { REQUIRED, OPTIONAL, OFF }

    val id: String = text("id")
    val order: Int = int("order")
    val title: String = text("title")
    val subtitle: String = text("subtitle")
    val note: String = header["note"] ?: ""
    val modality: String = text("modality")
    val camera: Need = need("camera")
    val glove: Need = need("glove")
    val classes: List<String> = text("classes").split('|')
    val featureSpecVersion: Int = int("feature_spec_version")
    val inFeatures: Int = int("in_features")
    val seqLen: Int = int("seq_len")
    val hz: Double = text("hz").toDouble()
    val sourceFile: String = header["source_file"] ?: ""
    val sourceSha256: String = header["source_sha256"] ?: ""

    /** true = this input column is set to 0 before the network (as it was in training). */
    val zeroCols: BooleanArray = parseZeroCols(header["zero_cols"] ?: "", inFeatures)

    private val kernel = int("conv_kernel")
    private val padding = int("conv_padding")
    private val channels = int("conv_channels")
    private val hidden = int("lstm_hidden")
    private val bnEps = text("bn_eps").toDouble()

    private val convW = tensor("conv1d.weight", channels * inFeatures * kernel)
    private val convB = tensor("conv1d.bias", channels)
    private val bn1Scale: DoubleArray
    private val bn1Shift: DoubleArray
    private val bn2Scale: DoubleArray
    private val bn2Shift: DoubleArray
    private val fcW = tensor("fc.weight", classes.size * 2 * hidden)
    private val fcB = tensor("fc.bias", classes.size)

    init {
        require(text("format") == "1") { "$id: unknown .aislm format ${header["format"]}" }
        require(text("pooling") == "last_step") { "$id: pooling '${header["pooling"]}' is not implemented" }
        require(kernel >= 1 && padding >= 0 && 2 * padding <= kernel - 1) { "$id: bad conv kernel/padding" }
        require(classes.size >= 2 && classes.all { it.isNotEmpty() }) { "$id: bad class list" }
        require(camera != Need.OFF || glove != Need.OFF) { "$id: model uses neither camera nor glove" }
        val a = affine("bn1", channels)
        bn1Scale = a.first
        bn1Shift = a.second
        val b = affine("bn2", 2 * hidden)
        bn2Scale = b.first
        bn2Shift = b.second
        for (suffix in listOf("", "_reverse")) {
            tensor("bilstm.weight_ih_l0$suffix", 4 * hidden * channels)
            tensor("bilstm.weight_hh_l0$suffix", 4 * hidden * hidden)
            tensor("bilstm.bias_ih_l0$suffix", 4 * hidden)
            tensor("bilstm.bias_hh_l0$suffix", 4 * hidden)
        }
    }

    class Prediction(val logits: DoubleArray, val probs: DoubleArray) {
        /** Class indices, most likely first. */
        val ranked: List<Int> = probs.indices.sortedByDescending { probs[it] }
        val top: Int get() = ranked[0]
    }

    /** x = [T][inFeatures] rows of normalized features (Normalizer.FEATURE_COLUMNS order), T >= 1. */
    fun predict(x: Array<DoubleArray>): Prediction {
        val z = logits(x)
        val m = z.max()
        val e = DoubleArray(z.size) { Math.exp(z[it] - m) }
        val s = e.sum()
        return Prediction(z, DoubleArray(z.size) { e[it] / s })
    }

    fun logits(x: Array<DoubleArray>): DoubleArray {
        require(x.isNotEmpty()) { "empty sequence" }
        for (row in x) {
            require(row.size == inFeatures) { "row has ${row.size} values, model $id needs $inFeatures" }
            for (v in row) require(!v.isNaN() && !v.isInfinite()) { "input has NaN/inf" }
        }
        val tOut = x.size + 2 * padding - (kernel - 1)
        require(tOut >= 1) { "sequence too short" }

        // Conv1d + BatchNorm + ReLU -> seq[t][c]
        val seq = Array(tOut) { DoubleArray(channels) }
        for (t in 0 until tOut) {
            val out = seq[t]
            for (o in 0 until channels) {
                var acc = convB[o].toDouble()
                for (k in 0 until kernel) {
                    val src = t + k - padding
                    if (src < 0 || src >= x.size) continue   // zero padding
                    val row = x[src]
                    val base = (o * inFeatures) * kernel + k
                    for (c in 0 until inFeatures) {
                        if (!zeroCols[c]) acc += convW[base + c * kernel] * row[c]
                    }
                }
                val v = acc * bn1Scale[o] + bn1Shift[o]
                out[o] = if (v > 0.0) v else 0.0
            }
        }

        // Bidirectional LSTM; the classifier reads the output at the last time step:
        // forward direction after the whole sequence, backward direction after its first step.
        val fwd = lstm(seq, "", reverse = false)
        val bwd = lstm(seq, "_reverse", reverse = true)
        val feat = DoubleArray(2 * hidden)
        for (j in 0 until hidden) {
            feat[j] = fwd[tOut - 1][j]
            feat[hidden + j] = bwd[tOut - 1][j]
        }

        // BatchNorm + Linear
        val n = 2 * hidden
        for (j in 0 until n) feat[j] = feat[j] * bn2Scale[j] + bn2Shift[j]
        return DoubleArray(classes.size) { c ->
            var acc = fcB[c].toDouble()
            for (j in 0 until n) acc += fcW[c * n + j] * feat[j]
            acc
        }
    }

    /** PyTorch nn.LSTM, one direction: gates in the order i, f, g, o. Returns out[t][hidden] by time index. */
    private fun lstm(seq: Array<DoubleArray>, suffix: String, reverse: Boolean): Array<DoubleArray> {
        val wIh = w.getValue("bilstm.weight_ih_l0$suffix")
        val wHh = w.getValue("bilstm.weight_hh_l0$suffix")
        val bIh = w.getValue("bilstm.bias_ih_l0$suffix")
        val bHh = w.getValue("bilstm.bias_hh_l0$suffix")
        val hSize = hidden
        val out = Array(seq.size) { DoubleArray(hSize) }
        var h = DoubleArray(hSize)
        val c = DoubleArray(hSize)
        val gates = DoubleArray(4 * hSize)
        val order = if (reverse) seq.indices.reversed() else seq.indices
        for (t in order) {
            val xt = seq[t]
            for (g in 0 until 4 * hSize) {
                var acc = bIh[g].toDouble() + bHh[g].toDouble()
                val a = g * channels
                for (k in 0 until channels) acc += wIh[a + k] * xt[k]
                val b = g * hSize
                for (k in 0 until hSize) acc += wHh[b + k] * h[k]
                gates[g] = acc
            }
            val hNew = out[t]
            for (j in 0 until hSize) {
                val i = sigmoid(gates[j])
                val f = sigmoid(gates[hSize + j])
                val g = Math.tanh(gates[2 * hSize + j])
                val o = sigmoid(gates[3 * hSize + j])
                c[j] = f * c[j] + i * g
                hNew[j] = o * Math.tanh(c[j])
            }
            h = hNew
        }
        return out
    }

    private fun sigmoid(v: Double) = 1.0 / (1.0 + Math.exp(-v))

    /** BatchNorm in eval mode as y = x * scale + shift. */
    private fun affine(name: String, n: Int): Pair<DoubleArray, DoubleArray> {
        val gamma = tensor("$name.weight", n)
        val beta = tensor("$name.bias", n)
        val mean = tensor("$name.running_mean", n)
        val variance = tensor("$name.running_var", n)
        val scale = DoubleArray(n) { gamma[it] / Math.sqrt(variance[it] + bnEps) }
        val shift = DoubleArray(n) { beta[it] - mean[it] * scale[it] }
        return Pair(scale, shift)
    }

    private fun text(key: String): String = header[key] ?: throw IllegalArgumentException("model header has no '$key'")
    private fun int(key: String): Int = text(key).toInt()
    private fun need(key: String): Need = when (val v = text(key)) {
        "required" -> Need.REQUIRED
        "optional" -> Need.OPTIONAL
        "off" -> Need.OFF
        else -> throw IllegalArgumentException("model header: $key='$v' (required | optional | off)")
    }

    private fun tensor(name: String, size: Int): FloatArray {
        val t = w[name] ?: throw IllegalArgumentException("$id: tensor $name missing")
        require(t.size == size) { "$id: tensor $name has ${t.size} values, expected $size" }
        return t
    }

    companion object {
        private val MAGIC = "AISLM1\n".toByteArray(Charsets.US_ASCII)

        /** "63-78", "0-62,70-71" or "" -> flags per column. */
        fun parseZeroCols(spec: String, n: Int): BooleanArray {
            val out = BooleanArray(n)
            for (part in spec.split(',').map { it.trim() }.filter { it.isNotEmpty() }) {
                val ab = part.split('-')
                require(ab.size == 2) { "zero_cols: bad range '$part'" }
                val a = ab[0].toInt()
                val b = ab[1].toInt()
                require(a in 0..b && b < n) { "zero_cols: range '$part' outside 0..${n - 1}" }
                for (i in a..b) out[i] = true
            }
            return out
        }

        fun parse(bytes: ByteArray): SignModel {
            require(bytes.size > MAGIC.size + 4 && bytes.copyOfRange(0, MAGIC.size).contentEquals(MAGIC)) {
                "not an AISLM1 model file"
            }
            val buf = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)
            buf.position(MAGIC.size)
            val n = buf.int
            require(n > 0 && n <= buf.remaining()) { "model file: bad header length" }
            val headerBytes = ByteArray(n)
            buf.get(headerBytes)
            val header = LinkedHashMap<String, String>()
            for (line in String(headerBytes, Charsets.UTF_8).split('\n')) {
                if (line.isEmpty()) continue
                val eq = line.indexOf('=')
                require(eq > 0) { "model file: bad header line '$line'" }
                header[line.substring(0, eq)] = line.substring(eq + 1)
            }
            val tensors = LinkedHashMap<String, FloatArray>()
            val list = header["tensors"] ?: throw IllegalArgumentException("model file: no tensor list")
            for (item in list.split(',')) {
                val (name, dims) = item.split(':')
                val count = dims.split('x').fold(1) { acc, d -> acc * d.toInt() }
                require(count > 0 && buf.remaining() >= 4 * count) { "model file: tensor $name is cut off" }
                val a = FloatArray(count)
                for (i in 0 until count) {
                    val v = buf.float
                    require(!v.isNaN() && !v.isInfinite()) { "model file: tensor $name has NaN/inf" }
                    a[i] = v
                }
                tensors[name] = a
            }
            require(buf.remaining() == 0) { "model file: ${buf.remaining()} unexpected bytes at the end" }
            return SignModel(header, tensors)
        }
    }
}
