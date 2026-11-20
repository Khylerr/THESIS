package com.aisla.core

/** numpy's median / percentile (method "linear"), same arithmetic so results are identical. */
object Stats {

    fun median(values: DoubleArray): Double {
        require(values.isNotEmpty())
        val a = values.sortedArray()
        val n = a.size
        return if (n % 2 == 1) a[n / 2] else (a[n / 2 - 1] + a[n / 2]) / 2.0
    }

    /** np.percentile(values, q) and pandas Series.quantile(q / 100). */
    fun percentile(values: DoubleArray, q: Double): Double {
        require(values.isNotEmpty())
        val a = values.sortedArray()
        val n = a.size
        val virtual = (n - 1) * (q / 100.0)
        val prev = Math.floor(virtual)
        val gamma = virtual - prev
        val i = prev.toInt().coerceIn(0, n - 1)
        val j = (i + 1).coerceIn(0, n - 1)
        val lo = a[i]
        val hi = a[j]
        val diff = hi - lo
        return if (gamma >= 0.5) hi - diff * (1 - gamma) else lo + diff * gamma
    }

    fun max(values: DoubleArray): Double {
        require(values.isNotEmpty())
        var m = values[0]
        for (v in values) if (v > m) m = v
        return m
    }
}
