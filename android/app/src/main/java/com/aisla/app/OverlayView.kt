package com.aisla.app

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.util.AttributeSet
import android.view.View
import com.aisla.core.Hand

/**
 * Shows exactly the image MediaPipe analyzed (upright, mirrored) with its landmarks on top.
 * Drawing the analyzed frame itself (instead of a separate camera preview) means the
 * landmarks always line up, on any phone or tablet, and you see what the model sees.
 */
class OverlayView @JvmOverloads constructor(context: Context, attrs: AttributeSet? = null) : View(context, attrs) {

    private var frame: Bitmap? = null
    private var hands: List<Pair<Hand, Boolean>> = emptyList()   // (hand, is glove hand)
    private val dst = RectF()

    private val glovePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.GREEN; strokeWidth = 5f }
    private val otherPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.rgb(255, 170, 0); strokeWidth = 4f }
    private val bitmapPaint = Paint(Paint.FILTER_BITMAP_FLAG)

    fun setFrame(frame: Bitmap, hands: List<Pair<Hand, Boolean>>) {
        this.frame = frame
        this.hands = hands
        invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val bmp = frame ?: return
        val imgW = bmp.width.toFloat()
        val imgH = bmp.height.toFloat()
        val s = minOf(width / imgW, height / imgH)
        val ox = (width - imgW * s) / 2f
        val oy = (height - imgH * s) / 2f
        dst.set(ox, oy, ox + imgW * s, oy + imgH * s)
        canvas.drawBitmap(bmp, null, dst, bitmapPaint)
        fun px(h: Hand, i: Int) = ox + h.xyz[3 * i].toFloat() * imgW * s
        fun py(h: Hand, i: Int) = oy + h.xyz[3 * i + 1].toFloat() * imgH * s
        for ((h, isGlove) in hands) {
            val p = if (isGlove) glovePaint else otherPaint
            for ((a, b) in CONNECTIONS) canvas.drawLine(px(h, a), py(h, a), px(h, b), py(h, b), p)
            for (i in 0 until 21) canvas.drawCircle(px(h, i), py(h, i), 6f, p)
        }
    }

    companion object {
        private val CONNECTIONS = listOf(
            0 to 1, 1 to 2, 2 to 3, 3 to 4,
            0 to 5, 5 to 6, 6 to 7, 7 to 8,
            5 to 9, 9 to 10, 10 to 11, 11 to 12,
            9 to 13, 13 to 14, 14 to 15, 15 to 16,
            13 to 17, 0 to 17, 17 to 18, 18 to 19, 19 to 20,
        )
    }
}
