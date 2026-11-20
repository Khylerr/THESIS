package com.aisla.core

/**
 * Two-point flex calibration: hand fully open (flat, still), then a tight fist.
 * Port of aisl_norm.flex_calibration / normalize_flex (golden-tested):
 *   flex_n = (v - open) / (closed - open)   -> ~0 open, ~1 fist (not clipped)
 */
class FlexCalibration(val open: DoubleArray, val closed: DoubleArray) {
    init {
        require(open.size == 5 && closed.size == 5)
    }

    fun normalize(v: DoubleArray): DoubleArray = DoubleArray(5) { i -> (v[i] - open[i]) / (closed[i] - open[i]) }

    companion object {
        const val HOLD_SEC = 3.0            // hold each pose this long ...
        const val AVG_SEC = 1.0             // ... and average its last second of samples
        const val MIN_SAMPLES = 25          // >= 0.5 s at 50 Hz
        const val MIN_FLEX_RANGE = 100.0    // |closed - open| below this (ADC counts) = not calibrated

        /** Samples: each with flex1..5 first. Throws IllegalArgumentException (same text as Python). */
        fun fromSamples(openSamples: List<DoubleArray>, closedSamples: List<DoubleArray>): FlexCalibration {
            require(openSamples.size >= MIN_SAMPLES && closedSamples.size >= MIN_SAMPLES) {
                "too few glove samples (${openSamples.size} open, ${closedSamples.size} fist; need $MIN_SAMPLES): " +
                    "is the glove streaming?"
            }
            val o = means(openSamples)
            val c = means(closedSamples)
            val bad = (0 until 5).filter { !(Math.abs(c[it] - o[it]) >= MIN_FLEX_RANGE) }.map { "F${it + 1}" }
            require(bad.isEmpty()) {
                "${bad.joinToString(", ")} barely changed between open hand and fist " +
                    "(< ${PyFormat.pyFixed(MIN_FLEX_RANGE, 0)} counts): check the sensor, then redo with a tight fist"
            }
            return FlexCalibration(o, c)
        }

        private fun means(samples: List<DoubleArray>): DoubleArray = DoubleArray(5) { i ->
            var total = 0.0
            for (s in samples) total += s[i]
            total / samples.size
        }
    }
}
