package com.aisla.app

import android.content.Context
import android.graphics.Bitmap
import com.aisla.core.Hand
import com.aisla.core.N_LM
import com.google.mediapipe.framework.image.BitmapImageBuilder
import com.google.mediapipe.tasks.core.BaseOptions
import com.google.mediapipe.tasks.core.Delegate
import com.google.mediapipe.tasks.vision.core.RunningMode
import com.google.mediapipe.tasks.vision.handlandmarker.HandLandmarker
import com.google.mediapipe.tasks.vision.handlandmarker.HandLandmarkerResult
import org.json.JSONObject
import java.io.Closeable
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.security.MessageDigest

/** shared/mediapipe_config.json (bundled as an asset): the settings fslRecorder.py uses too. */
class SharedConfig(private val json: JSONObject) {
    val specVersion = json.getInt("spec_version")
    val api: String = json.getString("api")
    val mediapipeVersion: String = json.getString("mediapipe_version")
    val modelFile: String = json.getString("model_file")
    val modelSha256: String = json.getString("model_sha256")
    val runningMode: String = json.getString("running_mode")
    val delegate: String = json.getString("delegate")
    val numHands = json.getInt("num_hands")
    val minHandDetectionConfidence = json.getDouble("min_hand_detection_confidence")
    val minHandPresenceConfidence = json.getDouble("min_hand_presence_confidence")
    val minTrackingConfidence = json.getDouble("min_tracking_confidence")
    val inputMirrored = json.getBoolean("input_mirrored")
    val invertHandednessLabel = json.getBoolean("invert_handedness_label")

    /** Tasks label -> the signer's real hand (same rule as aisl_norm.handedness_label). */
    fun handednessLabel(categoryName: String): String {
        if (!invertHandednessLabel) return categoryName
        return when (categoryName) {
            "Left" -> "Right"
            "Right" -> "Left"
            else -> categoryName
        }
    }

    /** Same keys/values as fslRecorder.mp_settings() writes into each take's JSON. */
    fun settingsJson(modelSha256: String): JSONObject {
        val o = JSONObject()
        for (k in listOf("api", "model_file", "running_mode", "delegate", "num_hands",
            "min_hand_detection_confidence", "min_hand_presence_confidence",
            "min_tracking_confidence", "input_mirrored", "invert_handedness_label")) {
            o.put(k, json.get(k))
        }
        o.put("model_sha256", modelSha256)
        return o
    }

    companion object {
        const val ASSET = "mediapipe_config.json"

        fun load(context: Context): SharedConfig =
            context.assets.open(ASSET).use { SharedConfig(JSONObject(it.reader().readText())) }
    }
}

/**
 * MediaPipe Tasks HandLandmarker, exactly as fslRecorder.HandTracker sets it up:
 * same model bytes (sha256-checked), VIDEO mode, CPU, same thresholds. The bitmap given to
 * process() must already be upright and mirrored (CameraPipeline does that), like the
 * recorder's cv2.flip(frame, 1) webcam frames.
 */
class HandTracker(context: Context, val cfg: SharedConfig) : Closeable {
    val modelSha256: String
    private val modelBytes: ByteArray
    private val landmarker: HandLandmarker
    private var lastMs = -1L

    init {
        check(cfg.runningMode == "VIDEO" && cfg.delegate == "CPU") {
            "shared config: running_mode must be VIDEO and delegate CPU"
        }
        check(cfg.mediapipeVersion == BuildConfig.MEDIAPIPE_VERSION) {
            "App is built with MediaPipe ${BuildConfig.MEDIAPIPE_VERSION}, shared config says " +
                "${cfg.mediapipeVersion}. Use the same version on desktop and phone."
        }
        val bytes = context.assets.open(cfg.modelFile).use { it.readBytes() }
        modelSha256 = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
        check(modelSha256 == cfg.modelSha256) {
            "${cfg.modelFile} sha256 $modelSha256 != ${cfg.modelSha256} in the shared config"
        }
        modelBytes = bytes
        landmarker = create(context, RunningMode.VIDEO, Delegate.CPU)
    }

    /** A landmarker with the shared settings; mode/delegate other than VIDEO/CPU only for tests. */
    fun create(context: Context, mode: RunningMode, delegate: Delegate): HandLandmarker {
        val buffer = ByteBuffer.allocateDirect(modelBytes.size).order(ByteOrder.nativeOrder())
        buffer.put(modelBytes)
        buffer.rewind()
        val base = BaseOptions.builder()
            .setModelAssetBuffer(buffer)
            .setDelegate(delegate)
            .build()
        val options = HandLandmarker.HandLandmarkerOptions.builder()
            .setBaseOptions(base)
            .setRunningMode(mode)
            .setNumHands(cfg.numHands)
            .setMinHandDetectionConfidence(cfg.minHandDetectionConfidence.toFloat())
            .setMinHandPresenceConfidence(cfg.minHandPresenceConfidence.toFloat())
            .setMinTrackingConfidence(cfg.minTrackingConfidence.toFloat())
            .build()
        return HandLandmarker.createFromOptions(context, options)
    }

    /** Upright, mirrored frame captured at tSec (host clock) -> hands found. */
    fun process(bitmap: Bitmap, tSec: Double): List<Hand> {
        val ms = maxOf(Math.rint(tSec * 1000).toLong(), lastMs + 1)   // VIDEO mode: strictly increasing
        lastMs = ms
        return toHands(landmarker.detectForVideo(BitmapImageBuilder(bitmap).build(), ms))
    }

    fun toHands(result: HandLandmarkerResult): List<Hand> {
        val lms = result.landmarks()
        val hd = result.handedness()
        val n = minOf(lms.size, hd.size)
        return List(n) { i ->
            val c = hd[i][0]
            val pts = lms[i]
            val xyz = DoubleArray(3 * N_LM)
            for (k in 0 until N_LM) {
                xyz[3 * k] = pts[k].x().toDouble()
                xyz[3 * k + 1] = pts[k].y().toDouble()
                xyz[3 * k + 2] = pts[k].z().toDouble()
            }
            Hand(cfg.handednessLabel(c.categoryName()), c.score().toDouble(), xyz)
        }
    }

    override fun close() = landmarker.close()
}
