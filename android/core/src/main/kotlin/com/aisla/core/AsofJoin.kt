package com.aisla.core

/**
 * pandas.merge_asof without pandas: for each left key, the index of the matching right key
 * (-1 = no match). Same algorithm as pandas/_libs/join.pyx, so ties and tolerance edges
 * resolve the same way:
 *   backward = last right <= left, forward = first right >= left,
 *   nearest  = the closer of the two; an exact tie goes to backward.
 * Both arrays must be sorted ascending. A match farther than [tolerance] is dropped.
 */
object AsofJoin {

    fun join(left: DoubleArray, right: DoubleArray, direction: String, tolerance: Double?): IntArray =
        when (direction) {
            "backward" -> backward(left, right, tolerance)
            "forward" -> forward(left, right, tolerance)
            "nearest" -> nearest(left, right, tolerance)
            else -> throw IllegalArgumentException("direction must be nearest, backward or forward")
        }

    fun backward(left: DoubleArray, right: DoubleArray, tolerance: Double?): IntArray {
        val out = IntArray(left.size)
        var rightPos = 0
        for (leftPos in left.indices) {
            if (rightPos < 0) rightPos = 0
            while (rightPos < right.size && right[rightPos] <= left[leftPos]) rightPos++
            rightPos--
            out[leftPos] = rightPos
            if (tolerance != null && rightPos != -1) {
                val diff = left[leftPos] - right[rightPos]
                if (diff > tolerance) out[leftPos] = -1
            }
        }
        return out
    }

    fun forward(left: DoubleArray, right: DoubleArray, tolerance: Double?): IntArray {
        val out = IntArray(left.size)
        val rightSize = right.size
        var rightPos = rightSize - 1
        for (leftPos in left.indices.reversed()) {
            if (rightPos == rightSize) rightPos = rightSize - 1
            while (rightPos >= 0 && right[rightPos] >= left[leftPos]) rightPos--
            rightPos++
            out[leftPos] = if (rightPos != rightSize) rightPos else -1
            if (tolerance != null && rightPos != rightSize) {
                val diff = right[rightPos] - left[leftPos]
                if (diff > tolerance) out[leftPos] = -1
            }
        }
        return out
    }

    fun nearest(left: DoubleArray, right: DoubleArray, tolerance: Double?): IntArray {
        val b = backward(left, right, tolerance)
        val f = forward(left, right, tolerance)
        val out = IntArray(left.size)
        for (i in left.indices) {
            out[i] = when {
                b[i] == -1 -> f[i]
                f[i] == -1 -> b[i]
                else -> {
                    val bdiff = left[i] - right[b[i]]
                    val fdiff = right[f[i]] - left[i]
                    if (bdiff <= fdiff) b[i] else f[i]
                }
            }
        }
        return out
    }
}
