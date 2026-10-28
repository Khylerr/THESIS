package com.aisla.app

import android.graphics.Bitmap
import android.graphics.Matrix
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CaptureRequest
import android.os.SystemClock
import android.util.Log
import android.util.Range
import android.util.Size
import androidx.annotation.OptIn
import androidx.appcompat.app.AppCompatActivity
import androidx.camera.camera2.interop.Camera2CameraInfo
import androidx.camera.camera2.interop.Camera2Interop
import androidx.camera.camera2.interop.ExperimentalCamera2Interop
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import androidx.camera.core.resolutionselector.AspectRatioStrategy
import androidx.camera.core.resolutionselector.ResolutionSelector
import androidx.camera.core.resolutionselector.ResolutionStrategy
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.core.content.ContextCompat
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

/**
 * CameraX -> the same kind of image the desktop recorder gives MediaPipe.
 *
 * Webcam (fslRecorder.py): 640x480, already upright, then cv2.flip(frame, 1) (mirrored).
 * CameraX: frames come in the sensor's orientation (usually rotated 90/270 degrees) and are
 * never mirrored, front or back lens. So every frame is rotated upright, then mirrored
 * horizontally, for BOTH lenses, exactly like the webcam frames. Pixels are moved, not
 * resampled (filter = false). The size differs (e.g. 480x640 portrait): aisl_norm /
 * Normalizer take care of that.
 *
 * Timestamps: the sensor timestamp (start of exposure) moved onto
 * SystemClock.elapsedRealtimeNanos, the clock the glove samples use.
 */
class CameraPipeline(
    private val activity: AppCompatActivity,
    private val onFrame: (Frame) -> Unit,   // called on [executor]
) {
    class Frame(
        val bitmap: Bitmap,        // upright + mirrored, what MediaPipe sees
        val tFrameNs: Long,        // capture time on elapsedRealtimeNanos
        val tArriveNs: Long,       // when the analyzer got it
        val rotationDegrees: Int,
        val bufferWidth: Int,
        val bufferHeight: Int,
        val timestampFallback: Boolean,   // sensor timestamp unusable -> arrival time used
        val convertMs: Double,     // ImageProxy -> upright mirrored bitmap
    )

    val executor: ExecutorService = Executors.newSingleThreadExecutor()
    var lensFacing = CameraSelector.LENS_FACING_FRONT
        private set

    // What was set up (saved in each take's JSON)
    @Volatile var fpsRange: Range<Int>? = null
        private set
    @Volatile var timestampSource: String = "unknown"
        private set
    @Volatile var lastError: String = ""
        private set

    private var provider: ProcessCameraProvider? = null

    fun start(lens: Int = lensFacing) {
        lensFacing = lens
        val future = ProcessCameraProvider.getInstance(activity)
        future.addListener({
            try {
                val p = future.get()
                provider = p
                bind(p)
            } catch (e: Exception) {
                lastError = "camera: ${e.message}"
                Log.e(TAG, "camera start failed", e)
            }
        }, ContextCompat.getMainExecutor(activity))
    }

    @OptIn(ExperimentalCamera2Interop::class)
    private fun bind(p: ProcessCameraProvider) {
        val selector = CameraSelector.Builder().requireLensFacing(lensFacing).build()
        val info = p.availableCameraInfos.firstOrNull { selector.filter(listOf(it)).isNotEmpty() }
            ?: throw IllegalStateException("no ${if (lensFacing == CameraSelector.LENS_FACING_FRONT) "front" else "back"} camera")
        val c2 = Camera2CameraInfo.from(info)
        val range = chooseFpsRange(c2.getCameraCharacteristic(CameraCharacteristics.CONTROL_AE_AVAILABLE_TARGET_FPS_RANGES))
        timestampSource = when (c2.getCameraCharacteristic(CameraCharacteristics.SENSOR_INFO_TIMESTAMP_SOURCE)) {
            CameraCharacteristics.SENSOR_INFO_TIMESTAMP_SOURCE_REALTIME -> "REALTIME"
            CameraCharacteristics.SENSOR_INFO_TIMESTAMP_SOURCE_UNKNOWN -> "UNKNOWN"
            else -> "unreported"
        }
        fpsRange = range

        // No separate Preview stream: the screen shows the analyzed frames (OverlayView), so
        // what you see is exactly what MediaPipe sees. 640x480 (4:3) like the webcam recorder
        val analysisBuilder = ImageAnalysis.Builder()
            .setResolutionSelector(
                ResolutionSelector.Builder()
                    .setAspectRatioStrategy(AspectRatioStrategy.RATIO_4_3_FALLBACK_AUTO_STRATEGY)
                    .setResolutionStrategy(
                        ResolutionStrategy(Size(640, 480), ResolutionStrategy.FALLBACK_RULE_CLOSEST_HIGHER_THEN_LOWER)
                    )
                    .build()
            )
            .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)   // always the newest frame
            .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_RGBA_8888)
        if (range != null) {
            // fixed 30 fps (like the webcam): auto-exposure may not drop the frame rate in dim light
            Camera2Interop.Extender(analysisBuilder).setCaptureRequestOption(CaptureRequest.CONTROL_AE_TARGET_FPS_RANGE, range)
        }
        val analysis = analysisBuilder.build()
        analysis.setAnalyzer(executor) { image -> handle(image) }

        p.unbindAll()
        p.bindToLifecycle(activity, selector, analysis)
        lastError = ""
    }

    fun switchLens() {
        lensFacing = if (lensFacing == CameraSelector.LENS_FACING_FRONT) CameraSelector.LENS_FACING_BACK
        else CameraSelector.LENS_FACING_FRONT
        provider?.let {
            try {
                bind(it)
            } catch (e: Exception) {
                lastError = "camera: ${e.message}"
            }
        }
    }

    private fun handle(image: ImageProxy) {
        val tArrive = SystemClock.elapsedRealtimeNanos()
        val frame = try {
            val (tFrame, fallback) = toElapsedRealtime(image.imageInfo.timestamp, tArrive)
            val rotation = image.imageInfo.rotationDegrees
            val raw = image.toBitmap()
            val m = Matrix()
            m.postRotate(rotation.toFloat())   // upright first ...
            m.postScale(-1f, 1f)               // ... then mirror, like cv2.flip(frame, 1)
            val upright = Bitmap.createBitmap(raw, 0, 0, raw.width, raw.height, m, false)
            val convertMs = (SystemClock.elapsedRealtimeNanos() - tArrive) / 1e6
            Frame(upright, tFrame, tArrive, rotation, image.width, image.height, fallback, convertMs)
        } catch (e: Exception) {
            lastError = "frame: ${e.message}"
            Log.e(TAG, "frame conversion failed", e)
            return
        } finally {
            image.close()   // let the camera deliver the next frame while this one is processed
        }
        onFrame(frame)
    }

    fun shutdown() {
        executor.shutdown()
    }

    companion object {
        private const val TAG = "CameraPipeline"

        /** [30, 30] if the camera has it, else the range reaching 30 with the highest minimum. */
        fun chooseFpsRange(ranges: Array<Range<Int>>?): Range<Int>? {
            if (ranges.isNullOrEmpty()) return null
            ranges.firstOrNull { it.lower == 30 && it.upper == 30 }?.let { return it }
            return ranges.filter { it.upper == 30 }.maxByOrNull { it.lower }
        }

        /**
         * Sensor timestamps are on elapsedRealtimeNanos (REALTIME) or on System.nanoTime
         * (UNKNOWN), depending on the phone. Decide per frame by which clock the timestamp is
         * close to; convert to elapsedRealtimeNanos. Unusable -> arrival time (flagged).
         */
        fun toElapsedRealtime(sensorNs: Long, arrivalRealtimeNs: Long): Pair<Long, Boolean> {
            val monoNow = System.nanoTime()
            val rtNow = SystemClock.elapsedRealtimeNanos()
            val t = if (Math.abs(rtNow - sensorNs) <= Math.abs(monoNow - sensorNs)) sensorNs
            else sensorNs + (rtNow - monoNow)
            val age = arrivalRealtimeNs - t
            return if (age in 0..1_000_000_000L) Pair(t, false) else Pair(arrivalRealtimeNs, true)
        }
    }
}
