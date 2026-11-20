package com.aisla.app

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.graphics.Typeface
import android.util.AttributeSet
import android.util.TypedValue
import android.view.View
import java.util.Locale

/**
 * Shown instead of the camera picture when a model runs without the camera: the five flex
 * sensors as bars (0 = open hand, 1 = fist, from the two-point calibration) and the IMU values.
 */
class GloveView @JvmOverloads constructor(context: Context, attrs: AttributeSet? = null) : View(context, attrs) {

    private var flex: DoubleArray? = null     // 5 normalized values, null = not calibrated / no data
    private var imu: DoubleArray? = null      // acc x,y,z (m/s^2), gyro x,y,z (rad/s)

    private val dp = resources.displayMetrics.density
    private val sp = TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_SP, 1f, resources.displayMetrics)
    private val title = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.rgb(170, 178, 190); textSize = 13f * sp; textAlign = Paint.Align.CENTER
    }
    private val small = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.rgb(170, 178, 190); textSize = 12f * sp; textAlign = Paint.Align.CENTER
    }
    private val mono = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.rgb(170, 178, 190); textSize = 11f * sp; typeface = Typeface.MONOSPACE; textAlign = Paint.Align.CENTER
    }
    private val track = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.rgb(38, 42, 50) }
    private val fill = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.rgb(110, 155, 255) }
    private val rect = RectF()

    /** true while a message is shown on top: the bars are drawn faint. */
    var dimmed = false
        set(v) {
            if (field != v) {
                field = v
                invalidate()
            }
        }

    fun set(flexNorm: DoubleArray?, imuValues: DoubleArray?) {
        flex = flexNorm
        imu = imuValues
        invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val cx = width / 2f
        val alpha = if (dimmed) 60 else 255
        for (p in listOf(small, mono, track, fill)) p.alpha = alpha
        canvas.drawText("Camera is off for this model", cx, 22f * dp, title)

        val top = 36f * dp
        val bottom = height - 54f * dp
        if (bottom - top < 30f * dp) return
        val n = 5
        val barW = minOf(34f * dp, width / (n * 2.2f))
        val step = minOf(width / (n + 1f), barW * 2.1f)
        val startX = cx - step * (n - 1) / 2f
        val f = flex
        for (i in 0 until n) {
            val x = startX + step * i
            rect.set(x - barW / 2, top, x + barW / 2, bottom)
            canvas.drawRoundRect(rect, 8f * dp, 8f * dp, track)
            if (f != null) {
                val v = f[i].coerceIn(0.0, 1.0).toFloat()
                if (v > 0f) {
                    rect.set(x - barW / 2, bottom - maxOf((bottom - top) * v, 16f * dp), x + barW / 2, bottom)
                    canvas.drawRoundRect(rect, 8f * dp, 8f * dp, fill)
                }
            }
            canvas.drawText("F${i + 1}", x, bottom + 15f * dp, small)
            if (f != null) canvas.drawText(String.format(Locale.US, "%.2f", f[i]), x, bottom + 29f * dp, mono)
        }
        val m = imu
        if (m != null) {
            canvas.drawText(
                String.format(Locale.US, "acc %5.1f %5.1f %5.1f   gyro %5.2f %5.2f %5.2f", m[0], m[1], m[2], m[3], m[4], m[5]),
                cx, height - 8f * dp, mono,
            )
        }
    }
}
