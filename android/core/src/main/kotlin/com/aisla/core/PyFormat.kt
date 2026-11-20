package com.aisla.core

import java.math.BigDecimal
import java.math.MathContext
import java.math.RoundingMode

/**
 * Python/numpy number semantics, so the phone writes the same numbers as fslRecorder.py.
 *
 * pyRound  = Python round(x, n)          (exact binary value, half-even)
 * npRound  = numpy/pandas .round(n)      (x * 10^n, rint, / 10^n)
 * pyRepr   = Python repr(float)          (shortest text that parses back to x)
 * pyFixed  = Python f"{x:.nf}"           (exact binary value, half-even)
 */
object PyFormat {

    fun pyRound(x: Double, digits: Int): Double {
        if (x.isNaN() || x.isInfinite()) return x
        val r = parse(BigDecimal(x).setScale(digits, RoundingMode.HALF_EVEN).toString())
        return if (r == 0.0 && (x < 0.0 || (x == 0.0 && 1.0 / x < 0.0))) -0.0 else r
    }

    fun npRound(x: Double, digits: Int): Double {
        val f = Math.pow(10.0, digits.toDouble())
        return Math.rint(x * f) / f
    }

    fun pyFixed(x: Double, digits: Int): String {
        if (x.isNaN()) return "nan"
        if (x.isInfinite()) return if (x > 0) "inf" else "-inf"
        val s = BigDecimal(x).setScale(digits, RoundingMode.HALF_EVEN).toPlainString()
        val negZero = x < 0.0 || (x == 0.0 && 1.0 / x < 0.0)
        return if (negZero && !s.startsWith("-")) "-$s" else s
    }

    /** Python f"{x:.0%}" */
    fun pyPercent0(x: Double): String = pyFixed(x * 100, 0) + "%"

    fun pyRepr(x: Double): String {
        if (x.isNaN()) return "nan"
        if (x.isInfinite()) return if (x > 0) "inf" else "-inf"
        if (x == 0.0) return if (1.0 / x < 0.0) "-0.0" else "0.0"
        val d = shortestDecimal(x).stripTrailingZeros()
        val digits = d.unscaledValue().abs().toString()
        val exp = digits.length - 1 - d.scale()          // x = d.ddd * 10^exp
        val sign = if (d.signum() < 0) "-" else ""
        return if (exp < -4 || exp >= 16) {
            val mant = if (digits.length == 1) digits else "${digits[0]}.${digits.substring(1)}"
            val e = (if (exp < 0) "-" else "+") + Math.abs(exp).toString().padStart(2, '0')
            "$sign${mant}e$e"
        } else {
            var s = d.abs().toPlainString()
            if (!s.contains('.')) s += ".0"
            sign + s
        }
    }

    /** One CSV cell the way pandas.to_csv writes a float column (NaN -> empty). */
    fun csvCell(x: Double): String = if (x.isNaN()) "" else pyRepr(x)

    fun parse(s: String): Double = java.lang.Double.parseDouble(s)

    /** CSV cell -> Double like Python float(): "" (pandas NaN) and "nan" (older takes) -> NaN. */
    fun parseCell(s: String): Double = when (s.trim().lowercase()) {
        "", "nan", "-nan" -> Double.NaN
        "inf", "+inf", "infinity" -> Double.POSITIVE_INFINITY
        "-inf", "-infinity" -> Double.NEGATIVE_INFINITY
        else -> parse(s.trim())
    }

    // Shortest decimal that parses back to x; among equally short ones, the closest
    // (what Python's repr does). Digit counts are monotone: if p digits work, p+1 do too,
    // so search down from a count that is known to work.
    private fun shortestDecimal(x: Double): BigDecimal {
        val exact = BigDecimal(x)
        var p = BigDecimal(x.toString()).stripTrailingZeros().precision().coerceIn(1, 17)
        var best = candidates(exact, x, p)
        if (best.isEmpty()) {          // cannot happen (Double.toString round-trips), but be safe
            p = 17
            best = candidates(exact, x, p)
        }
        while (p > 1) {
            val c = candidates(exact, x, p - 1)
            if (c.isEmpty()) break
            best = c
            p--
        }
        if (best.size == 1) return best[0]
        val d0 = best[0].subtract(exact).abs()
        val d1 = best[1].subtract(exact).abs()
        val cmp = d0.compareTo(d1)
        return when {
            cmp < 0 -> best[0]
            cmp > 0 -> best[1]
            else -> exact.round(MathContext(p, RoundingMode.HALF_EVEN))
        }
    }

    private fun candidates(exact: BigDecimal, x: Double, p: Int): List<BigDecimal> {
        val out = ArrayList<BigDecimal>(2)
        val lo = exact.round(MathContext(p, RoundingMode.FLOOR))
        val hi = exact.round(MathContext(p, RoundingMode.CEILING))
        if (parse(lo.toString()) == x) out.add(lo)
        if (hi.compareTo(lo) != 0 && parse(hi.toString()) == x) out.add(hi)
        return out
    }
}
