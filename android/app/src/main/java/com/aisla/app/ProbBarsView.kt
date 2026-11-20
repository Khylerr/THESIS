package com.aisla.app

import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.RectF
import android.graphics.Typeface
import android.util.AttributeSet
import android.util.TypedValue
import android.view.View
import androidx.core.content.ContextCompat

/** One row per class: name, probability bar, percent. Rows keep their place; the top class is highlighted. */
class ProbBarsView @JvmOverloads constructor(context: Context, attrs: AttributeSet? = null) : View(context, attrs) {

    private var labels: List<String> = emptyList()
    private var probs: DoubleArray? = null
    private var top = -1
    private var confident = true

    private val dp = resources.displayMetrics.density
    private val sp = TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_SP, 1f, resources.displayMetrics)
    private val rowH = 22f * dp
    private val text = Paint(Paint.ANTI_ALIAS_FLAG).apply { textSize = 13f * sp }
    private val bar = Paint(Paint.ANTI_ALIAS_FLAG)
    private val rect = RectF()

    private val cText = ContextCompat.getColor(context, R.color.inf_text)
    private val cText2 = ContextCompat.getColor(context, R.color.inf_text2)
    private val cTrack = ContextCompat.getColor(context, R.color.inf_track)
    private val cBar = ContextCompat.getColor(context, R.color.inf_bar)
    private val cAccent = ContextCompat.getColor(context, R.color.inf_accent)
    private val cWarn = ContextCompat.getColor(context, R.color.inf_warn)

    fun setClasses(names: List<String>) {
        labels = names
        probs = null
        top = -1
        requestLayout()
        invalidate()
    }

    /** p = null clears the bars. confident = false paints the top bar in the warning colour. */
    fun setProbs(p: DoubleArray?, topIndex: Int = -1, confident: Boolean = true) {
        probs = p
        top = topIndex
        this.confident = confident
        invalidate()
    }

    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        val h = (rowH * labels.size).toInt() + paddingTop + paddingBottom
        setMeasuredDimension(getDefaultSize(suggestedMinimumWidth, widthMeasureSpec), resolveSize(h, heightMeasureSpec))
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        if (labels.isEmpty()) return
        text.typeface = Typeface.DEFAULT_BOLD
        val labelW = minOf(labels.maxOf { text.measureText(it) }, width * 0.38f)
        val pctW = text.measureText("100%")
        val gap = 8f * dp
        val x0 = paddingLeft.toFloat()
        val barL = x0 + labelW + gap
        val barR = width - paddingRight - pctW - gap
        val p = probs
        for (i in labels.indices) {
            val cy = paddingTop + rowH * i + rowH / 2
            val isTop = p != null && i == top
            text.typeface = if (isTop) Typeface.DEFAULT_BOLD else Typeface.DEFAULT
            text.color = if (isTop) cText else cText2
            text.textAlign = Paint.Align.LEFT
            val base = cy - (text.descent() + text.ascent()) / 2
            canvas.drawText(labels[i], x0, base, text)

            val half = 4f * dp
            rect.set(barL, cy - half, barR, cy + half)
            bar.color = cTrack
            canvas.drawRoundRect(rect, half, half, bar)
            if (p != null) {
                val v = p[i].coerceIn(0.0, 1.0).toFloat()
                if (v > 0.004f) {
                    rect.set(barL, cy - half, barL + maxOf((barR - barL) * v, 2 * half), cy + half)
                    bar.color = if (!isTop) cBar else if (confident) cAccent else cWarn
                    canvas.drawRoundRect(rect, half, half, bar)
                }
                text.textAlign = Paint.Align.RIGHT
                canvas.drawText("${Math.round(p[i] * 100)}%", (width - paddingRight).toFloat(), base, text)
            }
        }
    }
}
