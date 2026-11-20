package com.aisla.app

import android.content.Context
import android.graphics.Bitmap
import com.aisla.core.Hand
import com.aisla.core.PyFormat
import com.aisla.core.Stats
import com.google.mediapipe.framework.image.BitmapImageBuilder
import com.google.mediapipe.tasks.core.Delegate
import com.google.mediapipe.tasks.vision.core.RunningMode
import java.io.File

/**
 * CPU vs GPU on one camera frame (the exact upright, mirrored bitmap MediaPipe gets):
 *  - speed in VIDEO mode (tracking, as used while recording) and IMAGE mode
 *  - how far the GPU landmarks are from the CPU ones (IMAGE mode, same image)
 * Saves frame.png + cpu.csv + gpu.csv to [outDir], so the PC's MediaPipe can be run on the
 * very same image (MediaPipe/compare_bench.py).
 */
object DelegateBench {

    fun run(context: Context, tracker: HandTracker, frame: Bitmap, outDir: File): String {
        outDir.mkdirs()
        File(outDir, "frame.png").outputStream().use { frame.compress(Bitmap.CompressFormat.PNG, 100, it) }
        val img = BitmapImageBuilder(frame).build()
        val report = StringBuilder("GPU test on ${frame.width}x${frame.height} frame\n")
        val hands = LinkedHashMap<String, List<Hand>>()

        for ((name, delegate) in listOf("cpu" to Delegate.CPU, "gpu" to Delegate.GPU)) {
            try {
                // speed while tracking (VIDEO mode, 30 fps timestamps)
                val video = tracker.create(context, RunningMode.VIDEO, delegate)
                val vt = ArrayList<Double>()
                video.use {
                    for (i in 0 until 30) {
                        val t0 = System.nanoTime()
                        video.detectForVideo(img, i * 33L)
                        if (i >= 5) vt += (System.nanoTime() - t0) / 1e6
                    }
                }
                // landmarks + speed without tracking (IMAGE mode, comparable with the PC)
                val image = tracker.create(context, RunningMode.IMAGE, delegate)
                val it2 = ArrayList<Double>()
                image.use {
                    var last = image.detect(img)
                    for (i in 0 until 15) {
                        val t0 = System.nanoTime()
                        last = image.detect(img)
                        it2 += (System.nanoTime() - t0) / 1e6
                    }
                    hands[name] = tracker.toHands(last)
                }
                writeHands(File(outDir, "$name.csv"), hands.getValue(name))
                report.append("${name.uppercase()}: tracking ${PyFormat.pyFixed(Stats.median(vt.toDoubleArray()), 1)} ms, " +
                    "full detect ${PyFormat.pyFixed(Stats.median(it2.toDoubleArray()), 1)} ms, " +
                    "${hands.getValue(name).size} hand(s)\n")
            } catch (e: Throwable) {
                report.append("${name.uppercase()}: FAILED ${e.javaClass.simpleName}: ${e.message}\n")
            }
        }

        val c = hands["cpu"]?.firstOrNull()
        val g = hands["gpu"]?.firstOrNull()
        if (c != null && g != null) {
            var maxXy = 0.0
            var maxZ = 0.0
            for (k in 0 until 21) {
                maxXy = maxOf(maxXy, Math.abs(c.xyz[3 * k] - g.xyz[3 * k]) * frame.width,
                    Math.abs(c.xyz[3 * k + 1] - g.xyz[3 * k + 1]) * frame.height)
                maxZ = maxOf(maxZ, Math.abs(c.xyz[3 * k + 2] - g.xyz[3 * k + 2]))
            }
            report.append("GPU vs CPU: max ${PyFormat.pyFixed(maxXy, 2)} px in x/y, " +
                "max ${PyFormat.pyFixed(maxZ, 4)} in z (labels ${c.label}/${g.label})")
        } else {
            report.append("No hand in both results: hold the hand up and run the test again.")
        }
        File(outDir, "report.txt").writeText(report.toString())
        return report.toString()
    }

    private fun writeHands(f: File, hands: List<Hand>) {
        f.bufferedWriter().use { w ->
            w.append("hand,label,score," + (0 until 21).joinToString(",") { "x$it,y$it,z$it" }).append('\n')
            for ((i, h) in hands.withIndex()) {
                w.append("$i,${h.label},${PyFormat.pyRepr(h.score)},")
                w.append(h.xyz.joinToString(",") { PyFormat.pyRepr(it) }).append('\n')
            }
        }
    }
}
