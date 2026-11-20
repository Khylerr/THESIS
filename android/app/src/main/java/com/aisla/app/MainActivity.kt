package com.aisla.app

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.text.SpannableStringBuilder
import android.text.Spanned
import android.text.style.ForegroundColorSpan
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.camera.core.CameraSelector
import androidx.core.content.ContextCompat
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import com.aisla.core.FlexCalibration
import com.aisla.core.HandPicker
import com.aisla.core.Normalizer
import com.aisla.core.PyFormat
import com.aisla.core.Quality
import com.aisla.core.Stats
import com.aisla.core.SyncedRow
import com.aisla.core.TakeRecorder
import com.aisla.core.TakeSync
import org.json.JSONArray
import org.json.JSONObject
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter
import java.util.concurrent.Executors
import kotlin.concurrent.thread

/**
 * Take recorder, phone version of fslRecorder.py: camera + MediaPipe + BLE glove, 4 s takes
 * after a 3 s countdown, synced and quality-checked the same way, saved in the same CSV layout
 * plus the normalized features. (Live sign recognition comes later, once the model exists.)
 */
class MainActivity : AppCompatActivity() {

    companion object {
        const val RECORD_SEC = 4.0
        const val COUNTDOWN_SEC = 3.0
        const val SYNC_DIRECTION = "nearest"
        const val SYNC_TOLERANCE_SEC = 0.04
        const val HAND_MODE = "assume"
        const val LOG_OTHER = false   // one-handed signs only: no other_detected/o_* columns
        const val NOMINAL_FPS = 30.0
        const val VISION_BUDGET_MS = 1000.0 / 30
        val FLEX_CAL_METHOD = "two-point: open hand (glove CAL zero) then fist; mean of the last " +
            "${PyFormat.pyRepr(FlexCalibration.AVG_SEC).removeSuffix(".0")} s of a " +
            "${PyFormat.pyRepr(FlexCalibration.HOLD_SEC).removeSuffix(".0")} s hold each"
    }

    private lateinit var overlay: OverlayView
    private lateinit var bigText: TextView
    private lateinit var lights: TextView
    private lateinit var gloveText: TextView
    private lateinit var info: TextView
    private lateinit var editSigner: EditText
    private lateinit var editSigns: EditText
    private lateinit var editReps: EditText
    private lateinit var btnHand: Button
    private lateinit var btnStart: Button
    private lateinit var btnKeep: Button
    private lateinit var btnRedo: Button

    private var cfg: SharedConfig? = null
    private lateinit var camera: CameraPipeline
    private lateinit var glove: GloveBle
    private lateinit var store: TakeStore
    private val io = Executors.newSingleThreadExecutor()
    private val ui = Handler(Looper.getMainLooper())
    private val session = LocalDate.now().format(DateTimeFormatter.BASIC_ISO_DATE)

    // ---- analysis-thread state (only touched on camera.executor) ----
    @Volatile private var tracker: HandTracker? = null
    private var picker = HandPicker(HAND_MODE, "Right")
    private val recorder = TakeRecorder(RECORD_SEC, COUNTDOWN_SEC, LOG_OTHER)
    private var prevFrameNs = 0L
    private var current: TakeInfo? = null
    private val camLatencyMs = ArrayList<Double>()
    private var tsFallbacks = 0

    // ---- live stats for the status lights (written on the analysis thread) ----
    private val statsLock = Any()
    private val frameTimes = ArrayDeque<Double>()
    private val procMs = ArrayDeque<Double>()
    private val syncMs = ArrayDeque<Double>()
    private val skippedRecent = ArrayDeque<Int>()
    private val convertMsQ = ArrayDeque<Double>()
    private val mediapipeMsQ = ArrayDeque<Double>()
    private var lastBitmap: android.graphics.Bitmap? = null   // analysis thread only
    @Volatile private var handOk = false
    @Volatile private var imageSize = Pair(0, 0)

    // ---- session state (main thread) ----
    private var plan = mutableListOf<String>()
    private var planKey = ""
    private var planDone = 0
    private var pending: PendingTake? = null
    @Volatile private var rtt: Map<String, Any>? = null
    /** This session's flex calibration; shared with the Inference screen (AppSession). */
    private var flexCal: AppSession.StoredCal?
        get() = AppSession.flexCal
        set(v) {
            AppSession.flexCal = v
        }
    private var calibrating = false
    private var rttStarted = false

    private class TakeInfo(
        val signer: String, val sign: String, val rep: Int, val gloveHand: String, val banner: String,
        val flexCal: AppSession.StoredCal,
    )

    private class PendingTake(
        val take: TakeInfo, val rows: List<SyncedRow>, val quality: LinkedHashMap<String, Any?>,
        val tRec0: Double, val tEnd: Double, val imageW: Int, val imageH: Int, val rotation: Int,
        val bufferW: Int, val bufferH: Int, val lens: Int, val camLatencyMs: DoubleArray, val tsFallbacks: Int,
    )

    private val permissionLauncher =
        registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { res ->
            if (res[Manifest.permission.CAMERA] == true) startVision() else showInfo("Camera permission is needed.")
            if (bluetoothPermissions().all { res[it] == true }) glove.start()
            else showInfo("Bluetooth permission is needed for the glove.")
        }

    // ------------------------------------------------------------------ setup
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        // Android 15+ draws the app behind the status/navigation bars: keep the UI clear of them
        val root = findViewById<View>(R.id.root)
        val pad = root.paddingLeft
        ViewCompat.setOnApplyWindowInsetsListener(root) { v, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout())
            v.setPadding(pad + bars.left, pad + bars.top, pad + bars.right, pad + bars.bottom)
            insets
        }
        overlay = findViewById(R.id.overlay)
        bigText = findViewById(R.id.bigText)
        lights = findViewById(R.id.lights)
        gloveText = findViewById(R.id.gloveText)
        info = findViewById(R.id.info)
        editSigner = findViewById(R.id.editSigner)
        editSigns = findViewById(R.id.editSigns)
        editReps = findViewById(R.id.editReps)
        btnHand = findViewById(R.id.btnHand)
        btnStart = findViewById(R.id.btnStart)
        btnKeep = findViewById(R.id.btnKeep)
        btnRedo = findViewById(R.id.btnRedo)

        store = TakeStore(this)
        glove = AppSession.glove(this)   // one BLE connection for the whole app
        camera = CameraPipeline(this, ::onFrame)

        cfg = try {
            SharedConfig.load(this)
        } catch (e: Exception) {
            showInfo("Cannot read ${SharedConfig.ASSET}: ${e.message}")
            null
        }

        btnStart.setOnClickListener { startTake() }
        btnKeep.setOnClickListener { keepTake() }
        btnRedo.setOnClickListener { redoTake() }
        findViewById<Button>(R.id.btnCal).setOnClickListener { runFlexCalibration() }
        findViewById<Button>(R.id.btnLens).setOnClickListener { camera.switchLens() }
        val btnGpu = findViewById<Button>(R.id.btnGpu)
        btnGpu.setOnClickListener {
            if (recorder.active || pending != null) return@setOnClickListener
            // Uses the analysis thread on purpose (clean timings): the picture pauses meanwhile
            btnGpu.isEnabled = false
            btnStart.isEnabled = false
            bigText.text = "GPU test running (~10 s)\ncamera paused, keep your hand still"
            showInfo("Running CPU vs GPU test...")
            camera.executor.execute {
                val trk = tracker
                val bmp = lastBitmap
                val msg = if (trk == null || bmp == null) "Camera not running yet." else try {
                    DelegateBench.run(applicationContext, trk, bmp, java.io.File(getExternalFilesDir(null), "bench"))
                } catch (e: Throwable) {
                    "GPU test failed: ${e.message}"
                }
                ui.post {
                    showInfo(msg)
                    bigText.text = ""
                    btnGpu.isEnabled = true
                    btnStart.isEnabled = true
                }
            }
        }
        findViewById<Button>(R.id.btnInference).setOnClickListener {
            if (recorder.active || pending != null || calibrating) {
                showInfo("Finish the current take / calibration first.")
            } else {
                startActivity(Intent(this, InferenceActivity::class.java))
            }
        }
        btnHand.setOnClickListener {
            val hand = if (btnHand.text == "Right") "Left" else "Right"
            btnHand.text = hand
            camera.executor.execute { picker = HandPicker(HAND_MODE, hand) }
        }

        permissionLauncher.launch((listOf(Manifest.permission.CAMERA) + bluetoothPermissions()).toTypedArray())
        ui.post(ticker)
    }

    private fun bluetoothPermissions(): List<String> =
        if (Build.VERSION.SDK_INT >= 31) listOf(Manifest.permission.BLUETOOTH_SCAN, Manifest.permission.BLUETOOTH_CONNECT)
        else listOf(Manifest.permission.ACCESS_FINE_LOCATION)

    private fun startVision() {
        val c = cfg ?: return
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) return
        camera.executor.execute {
            try {
                if (tracker == null) tracker = HandTracker(applicationContext, c)
                ui.post { camera.start() }
            } catch (e: Exception) {
                ui.post { showInfo("MediaPipe setup failed: ${e.message}") }
            }
        }
    }

    /** Back from the Inference screen (which took the camera): take the camera again. */
    override fun onStart() {
        super.onStart()
        if (tracker != null) camera.start()
    }

    override fun onDestroy() {
        super.onDestroy()
        ui.removeCallbacksAndMessages(null)
        if (isFinishing) glove.stop()   // the glove connection belongs to the app (AppSession)
        camera.executor.execute {
            tracker?.close()
            tracker = null
        }
        camera.shutdown()
        io.shutdown()
    }

    // ------------------------------------------------------------------ per frame (analysis thread)
    private fun onFrame(frame: CameraPipeline.Frame) {
        val trk = tracker ?: return
        val tSec = frame.tFrameNs / 1e9
        lastBitmap = frame.bitmap
        val tMp = SystemClock.elapsedRealtimeNanos()
        val hands = try {
            trk.process(frame.bitmap, tSec)
        } catch (e: Exception) {
            ui.post { showInfo("MediaPipe: ${e.message}") }
            return
        }
        val mpMs = (SystemClock.elapsedRealtimeNanos() - tMp) / 1e6
        val procMsNow = (SystemClock.elapsedRealtimeNanos() - frame.tArriveNs) / 1e6
        val skipped = if (prevFrameNs > 0)
            maxOf(0, Math.rint((frame.tFrameNs - prevFrameNs) / 1e9 * NOMINAL_FPS).toInt() - 1) else 0
        prevFrameNs = frame.tFrameNs
        val (g, o) = picker.pick(hands, tSec)
        val w = frame.bitmap.width
        val h = frame.bitmap.height
        imageSize = Pair(w, h)

        // frame time minus the closest glove sample = the gap the take's sync will see
        val gap = glove.nearestGap(tSec)
        synchronized(statsLock) {
            push(frameTimes, tSec, 120)
            push(procMs, procMsNow, 60)
            push(skippedRecent, skipped, 60)
            push(convertMsQ, frame.convertMs, 60)
            push(mediapipeMsQ, mpMs, 60)
            if (gap != null) push(syncMs, -gap * 1000, 60)
        }
        handOk = g != null

        val banner: String = when (val st = recorder.onFrame(tSec, g, o, procMsNow, skipped)) {
            is TakeRecorder.Status.Idle -> ""
            is TakeRecorder.Status.Countdown -> {
                picker.resetStats()   // handedness stats count during the recording only
                "Get ready: ${st.secondsLeft.toInt() + 1}"
            }
            is TakeRecorder.Status.Recording -> {
                camLatencyMs += (frame.tArriveNs - frame.tFrameNs) / 1e6
                if (frame.timestampFallback) tsFallbacks++
                "REC ${PyFormat.pyFixed(st.secondsLeft, 1)} s" + if (g == null) "\ngloved hand NOT tracked" else ""
            }
            is TakeRecorder.Status.Finished -> {
                finishTake(st, frame)
                "Review the take"
            }
        }
        val drawn = hands.map { Pair(it, it === g) }
        val shown = frame.bitmap
        ui.post {
            overlay.setFrame(shown, drawn)
            if (bigText.text.toString() != banner) bigText.text = banner
        }
    }

    private fun <T> push(q: ArrayDeque<T>, v: T, max: Int) {
        q.addLast(v)
        while (q.size > max) q.removeFirst()
    }

    /** Analysis thread: the take just ended -> sync + quality, then ask keep/redo. */
    private fun finishTake(st: TakeRecorder.Status.Finished, frame: CameraPipeline.Frame) {
        val take = current ?: return
        val margin = SYNC_TOLERANCE_SEC   // small margin so the first/last frame can find a neighbour
        val gloveWin = glove.window(st.tRec0 - margin, st.tEnd + margin)
        val rows = TakeSync.sync(st.rows, gloveWin, st.tRec0, SYNC_DIRECTION, SYNC_TOLERANCE_SEC)
        val q = Quality.compute(rows, gloveWin, st.tRec0, RECORD_SEC, st.perf, picker.stats())
        val p = PendingTake(
            take, rows, q, st.tRec0, st.tEnd, frame.bitmap.width, frame.bitmap.height, frame.rotationDegrees,
            frame.bufferWidth, frame.bufferHeight, camera.lensFacing, camLatencyMs.toDoubleArray(), tsFallbacks,
        )
        ui.post { showReview(p) }
    }

    // ------------------------------------------------------------------ takes (main thread)
    private fun startTake() {
        if (pending != null) return
        if (tracker == null) {
            showInfo("Camera / MediaPipe not ready yet.")
            return
        }
        val latest = glove.latest()
        if (!glove.connected || latest == null || GloveBle.nowSec() - latest.t > 0.5) {
            showInfo("Waiting for glove data...")   // same rule as the desktop recorder
            return
        }
        val cal = flexCal
        if (calibrating) return
        if (cal == null || !flexCalValid(cal)) {
            showInfo("Calibrate the glove first: press Cal (open hand, then fist).")
            return
        }
        val signer = editSigner.text.toString().trim()
        val signs = editSigns.text.toString().split(',').map { it.trim() }.filter { it.isNotEmpty() }
        val reps = editReps.text.toString().toIntOrNull() ?: 0
        if (signer.isEmpty() || signs.isEmpty() || reps <= 0) {
            showInfo("Fill in signer, signs and reps.")
            return
        }
        val key = "$signer|${signs.joinToString(",")}|$reps"
        if (key != planKey || plan.isEmpty()) {
            plan = store.buildPlan(signer, signs, reps)
            planKey = key
            planDone = 0
            if (plan.isEmpty()) {
                showInfo("Nothing left to record for these signs.")
                return
            }
        }
        val sign = plan[0]
        val rep = store.nextRep(signer, sign)
        val banner = "[${planDone + 1}/${planDone + plan.size}] $sign  (rep $rep/$reps)"
        val takeInfo = TakeInfo(signer, sign, rep, btnHand.text.toString(), banner, cal)
        btnStart.isEnabled = false
        showInfo(banner)
        camera.executor.execute {
            current = takeInfo
            camLatencyMs.clear()
            tsFallbacks = 0
            picker.resetStats()
            recorder.start(GloveBle.nowSec())
        }
    }

    private fun showReview(p: PendingTake) {
        pending = p
        val q = p.quality
        @Suppress("UNCHECKED_CAST")
        val vis = q["vision_latency"] as Map<String, Any?>?
        @Suppress("UNCHECKED_CAST")
        val warnings = q["warnings"] as List<String>
        val fps = q["fps"] as Double
        val sb = StringBuilder()
        sb.append(p.take.banner).append('\n')
        sb.append("${q["n_frames"]} frames, ${PyFormat.pyFixed(fps, 1)} fps, ")
            .append("${PyFormat.pyPercent0(q["detected_frac"] as Double)} detected\n")
        sb.append("glove ${PyFormat.pyFixed(q["glove_hz"] as Double, 0)} Hz, ")
            .append("${PyFormat.pyPercent0(q["glove_matched_frac"] as Double)} synced")
        if (vis != null) sb.append(" | vision ${PyFormat.pyFixed(vis["median_ms"] as Double, 0)} ms/frame")
        for (wn in warnings) sb.append("\nWARNING: ").append(wn)
        showInfo(sb.toString())
        btnKeep.isEnabled = true
        btnRedo.isEnabled = true
    }

    private fun keepTake() {
        val p = pending ?: return
        val c = cfg ?: return
        val trk = tracker ?: return
        pending = null
        btnKeep.isEnabled = false
        btnRedo.isEnabled = false
        val meta = buildMeta(p, c, trk.modelSha256)
        io.execute {
            val msg = try {
                val f = store.save(p.take.signer, p.take.sign, p.take.rep, p.rows, LOG_OTHER, meta,
                    p.imageW.toDouble(), p.imageH.toDouble(), p.take.flexCal.cal)
                "saved ${f.name}"
            } catch (e: Exception) {
                "SAVE FAILED: ${e.message}"
            }
            ui.post {
                if (msg.startsWith("saved")) {
                    if (plan.isNotEmpty() && plan[0] == p.take.sign) plan.removeAt(0)
                    planDone++
                }
                showInfo(msg + if (plan.isEmpty()) "\nAll planned takes done." else "\nNext: ${plan[0]}")
                btnStart.isEnabled = true
            }
        }
    }

    private fun redoTake() {
        pending = null
        btnKeep.isEnabled = false
        btnRedo.isEnabled = false
        btnStart.isEnabled = true
        showInfo("Discarded, redo: ${plan.firstOrNull() ?: ""}")
    }

    private fun buildMeta(p: PendingTake, c: SharedConfig, modelSha: String): JSONObject {
        val lat = p.camLatencyMs
        val range = camera.fpsRange
        return JSONObject().apply {
            put("platform", "android")
            put("signer", p.take.signer)
            put("sign", p.take.sign)
            put("rep", p.take.rep)
            put("session", session)
            put("glove_hand", p.take.gloveHand)
            put("saved_local", LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss")))
            put("record_sec", RECORD_SEC)
            put("countdown_sec", COUNTDOWN_SEC)
            put("flipped_before_processing", true)
            put("clock", "SystemClock.elapsedRealtimeNanos (seconds)")
            put("record_start_clock_sec", p.tRec0)
            put("record_end_clock_sec", p.tEnd)
            put("camera_requested", JSONObject().put("width", 640).put("height", 480).put("fps", 30))
            put("camera_reported", JSONObject().put("width", p.bufferW).put("height", p.bufferH)
                .put("fps_range", range?.let { "[${it.lower}, ${it.upper}]" } ?: JSONObject.NULL))
            put("mediapipe_input", JSONObject().put("width", p.imageW).put("height", p.imageH)
                .put("rotation_degrees", p.rotation).put("mirrored", true))
            put("camera", JSONObject().apply {
                put("lens", if (p.lens == CameraSelector.LENS_FACING_FRONT) "front" else "back")
                put("frame_timestamp", "sensor timestamp (start of exposure) on elapsedRealtimeNanos")
                put("sensor_timestamp_source", camera.timestampSource)
                put("timestamp_fallback_frames", p.tsFallbacks)
                if (lat.isNotEmpty()) {
                    put("capture_to_analyzer_ms", JSONObject()
                        .put("median", PyFormat.pyRound(Stats.median(lat), 1))
                        .put("p95", PyFormat.pyRound(Stats.percentile(lat, 95.0), 1))
                        .put("max", PyFormat.pyRound(Stats.max(lat), 1)))
                }
                put("frames_skipped_method", "estimated from sensor timestamp gaps at $NOMINAL_FPS fps")
            })
            put("device", JSONObject().put("manufacturer", Build.MANUFACTURER).put("model", Build.MODEL)
                .put("android_sdk", Build.VERSION.SDK_INT))
            put("glove", JSONObject().apply {
                put("transport", "ble")
                put("device", glove.deviceName)
                put("ble_mtu", glove.mtu ?: JSONObject.NULL)
                put("columns", TakeStore.gloveColumnsJson())
                put("timestamp", "ESP32 millis() per sample, mapped to the phone clock " +
                    "(elapsedRealtimeNanos) via the minimum (arrival - device time) over a 10 s sliding window")
                put("units", "flex: ADC counts minus calibration baseline; acc: m/s^2; gyro: rad/s")
                put("sync_method", "AsofJoin.nearest (Kotlin port of pandas.merge_asof, golden-tested)")
                put("sync_direction", SYNC_DIRECTION)
                put("sync_tolerance_sec", SYNC_TOLERANCE_SEC)
                put("calibration", glove.calibration)
                put("round_trip_latency_session", TakeStore.toJson(rtt))
                put("packets_dropped_session", glove.nDropped)
                put("malformed_packets_session", glove.nBad)
                put("last_status_line", glove.lastStatus)
            })
            put("feature_spec_version", Normalizer.SPEC_VERSION)
            // two-point flex calibration of this session (same keys as fslRecorder.py)
            put("flex_calibration", JSONObject()
                .put("open", JSONArray(p.take.flexCal.cal.open.toList()))
                .put("closed", JSONArray(p.take.flexCal.cal.closed.toList()))
                .put("time", p.take.flexCal.time)
                .put("method", FLEX_CAL_METHOD))
            put("mediapipe_version", BuildConfig.MEDIAPIPE_VERSION)
            put("mediapipe_settings", c.settingsJson(modelSha))
            put("hand_mode", HAND_MODE)
            put("quality", TakeStore.toJson(p.quality))
        }
    }

    // ------------------------------------------------------------------ glove calibration (main thread)
    private fun flexCalValid(c: AppSession.StoredCal) = c.connectionId == glove.connectionId && c.gloveStatus == glove.calibration

    /** Open hand (also re-zeroes the glove) for HOLD_SEC, then a fist; averages the last AVG_SEC of each. */
    private fun runFlexCalibration() {
        if (calibrating || recorder.active || pending != null) return
        if (!glove.connected) {
            showInfo("Glove not connected.")
            return
        }
        calibrating = true
        btnStart.isEnabled = false
        glove.sendCommand("CAL")
        holdPose("OPEN hand: fingers straight, flat, still") { open ->
            holdPose("Make a TIGHT FIST and hold it") { closed ->
                calibrating = false
                btnStart.isEnabled = true
                bigText.text = ""
                try {
                    val c = FlexCalibration.fromSamples(open, closed)
                    flexCal = AppSession.StoredCal(c, LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss")),
                        glove.connectionId, glove.calibration)
                    showInfo("Glove calibrated. Fist minus open (ADC counts): " +
                        (0 until 5).joinToString(" ") { "F${it + 1} ${PyFormat.pyFixed(c.closed[it] - c.open[it], 0)}" })
                } catch (e: IllegalArgumentException) {
                    flexCal = null
                    showInfo("Glove calibration FAILED: ${e.message}")
                }
            }
        }
    }

    private fun holdPose(prompt: String, then: (List<DoubleArray>) -> Unit) {
        val tEnd = SystemClock.elapsedRealtime() + (FlexCalibration.HOLD_SEC * 1000).toLong()
        val tick = object : Runnable {
            override fun run() {
                val left = (tEnd - SystemClock.elapsedRealtime()) / 1000.0
                if (left > 0) {
                    bigText.text = "$prompt\nhold still: ${PyFormat.pyFixed(left, 1)} s"
                    ui.postDelayed(this, 100)
                } else {
                    then(glove.recent(FlexCalibration.AVG_SEC).map { it.values })
                }
            }
        }
        ui.post(tick)
    }

    private fun showInfo(text: String) {
        info.text = text
    }

    // ------------------------------------------------------------------ status lights (main thread)
    private val ticker = object : Runnable {
        override fun run() {
            updateLights()
            ui.postDelayed(this, 100)
        }
    }

    private fun updateLights() {
        val now = GloveBle.nowSec()
        val sb = SpannableStringBuilder()
        fun light(color: Int, label: String, detail: String) {
            val start = sb.length
            sb.append("● ")
            sb.setSpan(ForegroundColorSpan(color), start, sb.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
            sb.append(label.padEnd(7)).append(detail).append('\n')
        }
        val green = Color.rgb(60, 180, 60)
        val yellow = Color.rgb(230, 170, 0)
        val red = Color.rgb(220, 50, 50)
        val grey = Color.GRAY

        val ts = synchronized(statsLock) { frameTimes.filter { it >= now - 1.0 } }
        val pm = synchronized(statsLock) { procMs.toList() }
        val sm = synchronized(statsLock) { syncMs.toList() }
        val sk = synchronized(statsLock) { skippedRecent.sum() }
        val cm = synchronized(statsLock) { convertMsQ.toDoubleArray() }
        val mm = synchronized(statsLock) { mediapipeMsQ.toDoubleArray() }
        val fps = if (ts.size > 2) (ts.size - 1) / (ts.last() - ts.first()) else 0.0
        light(if (fps >= Quality.MIN_FPS) green else if (fps > 0) yellow else red, "CAMERA",
            "${PyFormat.pyFixed(fps, 1)} fps  ${imageSize.first}x${imageSize.second}" +
                (if (camera.lastError.isNotEmpty()) "  ${camera.lastError}" else ""))
        light(if (handOk) green else red, "HAND", "${btnHand.text} hand " + if (handOk) "tracked" else "NOT FOUND")

        val last = glove.latest()
        val age = last?.let { (now - it.t) * 1000 }
        val hz = glove.rateHz()
        val gloveRed: Boolean
        if (!glove.connected) {
            gloveRed = true
            light(red, "GLOVE", "${glove.state} ${glove.lastError}")
        } else if (age == null || age > 500) {
            gloveRed = true
            light(red, "GLOVE", "connected, NO DATA")
        } else {
            gloveRed = false
            light(if (hz >= Quality.MIN_GLOVE_HZ) green else yellow, "GLOVE",
                "${PyFormat.pyFixed(hz, 0)} Hz   last ${PyFormat.pyFixed(age, 0)} ms ago")
        }
        // live glove values (same units as the CSV): flex counts, accel m/s^2, gyro rad/s
        if (last != null && !gloveRed) {
            val v = last.values
            sb.append("  flex  ").append((0 until 5).joinToString(" ") { "F${it + 1}:${PyFormat.pyFixed(v[it], 0).padStart(5)}" }).append('\n')
            sb.append("  acc   ").append((5 until 8).joinToString(" ") { PyFormat.pyFixed(v[it], 2).padStart(6) })
                .append("   gyro ").append((8 until 11).joinToString(" ") { PyFormat.pyFixed(v[it], 2).padStart(6) }).append('\n')
        }
        val fc = flexCal
        when {
            calibrating -> light(yellow, "FLEXCAL", "calibrating...")
            fc == null -> light(red, "FLEXCAL", "NOT DONE: press Cal (open hand, then fist)")
            !flexCalValid(fc) -> light(red, "FLEXCAL", "glove reconnected/re-zeroed: press Cal again")
            else -> light(green, "FLEXCAL", "OK  fist-open " + (0 until 5).joinToString(" ") {
                "F${it + 1}:${PyFormat.pyFixed(fc.cal.closed[it] - fc.cal.open[it], 0)}" })
        }
        val rec = glove.recent(1.0)
        when {
            rec.isEmpty() -> light(grey, "IMU", "-")
            rec.all { s -> (5 until 11).all { s.values[it] == 0.0 } } -> light(yellow, "IMU", "no data (all zeros: MPU missing?)")
            else -> light(green, "IMU", "OK")
        }
        if (sm.isNotEmpty() && !gloveRed) {
            val worst = sm.maxOf { Math.abs(it) }
            val tol = SYNC_TOLERANCE_SEC * 1000
            light(if (worst <= tol) green else if (worst <= 100) yellow else red, "SYNC",
                "frame-glove gap ${PyFormat.pyFixed(Stats.median(sm.toDoubleArray()), 0)} ms (max ${PyFormat.pyFixed(worst, 0)})")
        } else {
            light(red, "SYNC", "no glove data")
        }
        if (pm.isNotEmpty()) {
            val med = Stats.median(pm.toDoubleArray())
            light(if (med <= Quality.MAX_VISION_MS) green else if (med <= VISION_BUDGET_MS) yellow else red, "SPEED",
                "${PyFormat.pyFixed(med, 1)} ms/frame (max ${PyFormat.pyFixed(pm.max(), 0)})  " +
                    "headroom ${PyFormat.pyFixed(VISION_BUDGET_MS - med, 0)} ms" + if (sk > 0) "  $sk skipped" else "")
            if (cm.isNotEmpty() && mm.isNotEmpty()) {
                sb.append("  = convert ${PyFormat.pyFixed(Stats.median(cm), 1)} ms + MediaPipe ")
                    .append(PyFormat.pyFixed(Stats.median(mm), 1)).append(" ms + rest\n")
            }
        } else {
            light(grey, "SPEED", "-")
        }
        lights.text = sb
        gloveText.text = "Glove: " + if (glove.connected) "connected (BLE)" +
            (if (glove.lastStatus.isNotEmpty()) " · ${glove.lastStatus}" else "") else glove.state

        if (glove.connected && !rttStarted) {   // once per session, like the desktop recorder
            rttStarted = true
            thread(name = "glove-rtt") { rtt = glove.measureRtt(30) }
        }
    }
}
