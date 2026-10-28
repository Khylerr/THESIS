package com.aisla.core

const val N_LM = 21

/**
 * One hand found by MediaPipe on the mirrored, upright image.
 * label = the signer's real hand ("Left"/"Right", already corrected, see SharedConfig),
 * score = MediaPipe's handedness score, xyz = 63 values x0,y0,z0,...,z20 (raw, 0..1).
 */
class Hand(val label: String, val score: Double, val xyz: DoubleArray) {
    init {
        require(xyz.size == 3 * N_LM)
    }

    val wristX: Double get() = xyz[0]
    val wristY: Double get() = xyz[1]
}

/**
 * Decides which detected hand is the gloved one, frame by frame. Port of fslRecorder.HandPicker.
 *
 * mode "label":  MediaPipe's Left/Right label decides.
 * mode "assume": label ignored. One hand -> it is the glove hand (unless it appeared far from
 *                where the glove hand just was). Two hands -> the one closest to the glove
 *                hand's position in the last 0.5 s, else the one on the glove-hand side.
 */
class HandPicker(val mode: String, val gloveHand: String) {
    init {
        require(mode == "assume" || mode == "label") { "hand mode must be assume or label" }
        require(gloveHand == "Left" || gloveHand == "Right") { "glove hand must be Left or Right" }
    }

    private var prevX = 0.0
    private var prevY = 0.0
    private var hasPrev = false
    private var prevT = -1e9
    var nGlove = 0
        private set
    var nLabelMismatch = 0
        private set

    fun resetStats() {
        nGlove = 0
        nLabelMismatch = 0
    }

    private fun dist(h: Hand): Double = Math.hypot(h.wristX - prevX, h.wristY - prevY)

    /** Returns (glove hand, other hand); either can be null. */
    fun pick(found: List<Hand>, t: Double): Pair<Hand?, Hand?> {
        val glove: Hand? = if (mode == "label") {
            found.filter { it.label == gloveHand }.maxByOrNull { it.score }
        } else {
            val recent = hasPrev && t - prevT < 0.5
            when {
                found.size == 1 -> {
                    val h = found[0]
                    if (recent && dist(h) > JUMP) null else h   // glove hand left; this is the other hand
                }
                found.size > 1 -> when {
                    recent -> found.minByOrNull { dist(it) }
                    gloveHand == "Right" -> found.maxByOrNull { it.wristX }
                    else -> found.minByOrNull { it.wristX }
                }
                else -> null
            }
        }
        val other = found.filter { it !== glove }.maxByOrNull { it.score }
        if (glove != null) {
            prevX = glove.wristX
            prevY = glove.wristY
            prevT = t
            hasPrev = true
            nGlove++
            if (glove.label != gloveHand) nLabelMismatch++
        }
        return Pair(glove, other)
    }

    /** Same keys as the recorder's hand_picking stats. */
    fun stats(): LinkedHashMap<String, Any?> = linkedMapOf(
        "mode" to mode,
        "mediapipe_label_mismatch_frac" to
            (if (nGlove > 0) PyFormat.pyRound(nLabelMismatch.toDouble() / nGlove, 4) else null),
    )

    companion object {
        const val JUMP = 0.30   // normalized distance: a lone hand this far away = the other hand
    }
}
