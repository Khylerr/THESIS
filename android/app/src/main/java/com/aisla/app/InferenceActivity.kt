package com.aisla.app

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.graphics.Typeface
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.text.SpannableStringBuilder
import android.text.Spanned
import android.text.style.ForegroundColorSpan
import android.text.style.StyleSpan
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.widget.ArrayAdapter
import android.widget.ProgressBar
import android.widget.RadioButton
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.appcompat.widget.SwitchCompat
import androidx.core.content.ContextCompat
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import com.aisla.core.FlexCalibration
import com.aisla.core.HandPicker
import com.aisla.core.Normalizer
import com.aisla.core.Quality
import com.aisla.core.SignModel
import com.aisla.core.SignWindow
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter
import java.util.Locale
import java.util.concurrent.Executors
import java.util.concurrent.RejectedExecutionException
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Inference screen: pick one of the trained sign models (assets/<id>.aislm) and test it.
 *
 * A model says in its file which inputs it uses. Only those are turned on and asked for:
 * a camera-only model never waits for the glove or its calibration, a glove-only model runs
 * with the camera and MediaPipe switched off.
 *
 * Every prediction is made from one 4 s window turned into the 120 x 79 features of a recorded,
 * normalized take (SignWindow = the recorder's own sync + Normalizer code), because that is what
 * the models were trained on. Two ways to choose the window:
 *   Live      - the last 4 s, again every 0.3 s.
 *   4 s take  - countdown, then exactly 4 s, like recording a take.
 */
class InferenceActivity : AppCompatActivity() {

    companion object {
        const val COUNTDOWN_SEC = 3.0
        const val TICK_MS = 100L
        const val LIVE_PERIOD_MS = 300L
        const val KEEP_FRAMES_SEC = 10.0      // countdown + take + margin
        const val CONFIDENT = 0.60            // below this the answer is shown as "not sure"
        const val MIN_VALID_FRAC = 0.50       // less tracked hand / glove data than this = warning
        const val GLOVE_FRESH_SEC = 0.5       // same rule as the recorder
        const val CAMERA_FRESH_SEC = 1.0
        const val HAND_FRESH_SEC = 0.5
        const val TAKE_WAIT_SEC = 0.8         // longest wait for the last frames/samples of a take
        const val HAND_MODE = "assume"        // same as the recorder
        private const val PREFS = "inference"

        /**
         * On "CAL" the glove firmware stops streaming while it zeroes itself: 50 samples x 10 ms
         * = about 0.7 s, longer if it also re-initialises the IMU (hand_sign_glove_ble.ino,
         * calibrateSensors). That pause is normal, so during a calibration only a much longer
         * silence counts as "glove gone". (Bug until 2026-11-20: the 0.5 s GLOVE_FRESH_SEC rule
         * was used here and every calibration on this screen stopped at once.)
         */
        const val CAL_STALL_SEC = 2.5

        /** During a calibration: is the glove really gone? lastSampleAgeSec = null: never sent anything. */
        fun calibrationLost(connected: Boolean, lastSampleAgeSec: Double?): Boolean =
            !connected || lastSampleAgeSec == null || lastSampleAgeSec > CAL_STALL_SEC
    }

    private enum class Mode { LIVE, TAKE }
    private enum class Btn { NONE, ALLOW_CAMERA, ALLOW_BLUETOOTH, CALIBRATE, CANCEL_CAL, WAIT, START_TAKE, CANCEL_TAKE, PAUSE, RESUME }

    private class TakeState(val tRec0: Double, var submitted: Boolean = false)
    private class CalState(var phase: Int, var tEndMs: Long, var open: List<DoubleArray>? = null)

    private class Inputs(
        val useCam: Boolean, val useGlove: Boolean,
        val camPermission: Boolean, val btPermission: Boolean,
        val camRunning: Boolean, val handVisible: Boolean, val fps: Double,
        val gloveLive: Boolean, val gloveHz: Double, val calValid: Boolean,
        val blocking: String?, val blockButton: Btn,
    )

    /** One window's features and what the model said about it (pred = null: nothing usable in the window). */
    internal class Outcome(
        val window: SignWindow.Window, val pred: SignModel.Prediction?, val ms: Double,
        val model: SignModel, val usedCam: Boolean, val usedGlove: Boolean, val fromTake: Boolean,
    )

    // ---- views ----
    private lateinit var overlay: OverlayView
    private lateinit var gloveView: GloveView
    private lateinit var banner: TextView
    private lateinit var btnFlip: TextView
    private lateinit var progress: ProgressBar
    private lateinit var modelCard: View
    private lateinit var modelTitle: TextView
    private lateinit var modelSubtitle: TextView
    private lateinit var chipCamera: TextView
    private lateinit var chipGlove: TextView
    private lateinit var chipCal: TextView
    private lateinit var switchCamera: SwitchCompat
    private lateinit var resultLabel: TextView
    private lateinit var resultConf: TextView
    private lateinit var resultHint: TextView
    private lateinit var resultDetail: TextView
    private lateinit var bars: ProbBarsView
    private lateinit var modeLive: TextView
    private lateinit var modeTake: TextView
    private lateinit var btnAction: TextView

    // ---- inputs ----
    private lateinit var glove: GloveBle
    private lateinit var camera: CameraPipeline
    private var cfg: SharedConfig? = null
    @Volatile private var tracker: HandTracker? = null
    private var trackerStarting = false                       // main thread
    private val picker = HandPicker(HAND_MODE, "Right")      // camera thread only
    @Volatile private var cameraError = ""

    private val lock = Any()
    private val frames = ArrayDeque<SignWindow.Frame>()       // guarded by lock
    private var imageW = 0                                    // guarded by lock
    private var imageH = 0                                    // guarded by lock
    private var lastHandT = -1e9                              // guarded by lock

    // ---- state (main thread) ----
    private val ui = Handler(Looper.getMainLooper())
    private val inferExec = Executors.newSingleThreadExecutor()
    private val inferBusy = AtomicBoolean(false)
    internal var models: List<SignModel> = emptyList()
        private set
    private var loadErrors = ""
    private var model: SignModel? = null
    private var optCamera = false                 // glove model: also feed the camera (as trained)
    private var mode = Mode.LIVE
    private var paused = false
    private var started = false
    private var destroyed = false
    private var epoch = 0                         // +1 whenever running windows become meaningless
    private var tValidFrom = Double.MAX_VALUE     // a live window may not start before this
    private var wasReady = false
    private var lastLiveMs = 0L
    private var take: TakeState? = null
    private var cal: CalState? = null
    private var button = Btn.NONE
    private var showingResult = false
    private val asked = HashSet<String>()

    private val permissionLauncher =
        registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { res ->
            if (res.values.any { !it }) {
                Toast.makeText(this, "Not allowed. You can allow it in Android Settings > Apps > AISL-A > Permissions.",
                    Toast.LENGTH_LONG).show()
            }
            applyInputs()
        }

    // ------------------------------------------------------------------ setup
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_inference)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        val root = findViewById<View>(R.id.infRoot)
        val pad = root.paddingLeft
        ViewCompat.setOnApplyWindowInsetsListener(root) { v, insets ->
            val b = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout())
            v.setPadding(pad + b.left, pad + b.top, pad + b.right, pad + b.bottom)
            insets
        }
        overlay = findViewById(R.id.infOverlay)
        gloveView = findViewById(R.id.gloveView)
        banner = findViewById(R.id.banner)
        btnFlip = findViewById(R.id.btnFlip)
        progress = findViewById(R.id.windowProgress)
        modelCard = findViewById(R.id.modelCard)
        modelTitle = findViewById(R.id.modelTitle)
        modelSubtitle = findViewById(R.id.modelSubtitle)
        chipCamera = findViewById(R.id.chipCamera)
        chipGlove = findViewById(R.id.chipGlove)
        chipCal = findViewById(R.id.chipCal)
        switchCamera = findViewById(R.id.switchCamera)
        resultLabel = findViewById(R.id.resultLabel)
        resultConf = findViewById(R.id.resultConf)
        resultHint = findViewById(R.id.resultHint)
        resultDetail = findViewById(R.id.resultDetail)
        bars = findViewById(R.id.bars)
        modeLive = findViewById(R.id.modeLive)
        modeTake = findViewById(R.id.modeTake)
        btnAction = findViewById(R.id.btnAction)
        findViewById<View>(R.id.stage).clipToOutline = true

        glove = AppSession.glove(this)
        camera = CameraPipeline(this, ::onFrame)
        cfg = try {
            SharedConfig.load(this)
        } catch (e: Exception) {
            cameraError = "Cannot read ${SharedConfig.ASSET}: ${e.message}"
            null
        }
        loadModels()

        findViewById<View>(R.id.btnBack).setOnClickListener { finish() }
        modelCard.setOnClickListener { pickModel() }
        chipCal.setOnClickListener { if (model?.let { usesGlove(it) } == true) startCalibration() }
        switchCamera.setOnCheckedChangeListener { _, on ->
            if (on != optCamera) {
                optCamera = on
                applyInputs()
                restartWindow()
                clearResult()
            }
        }
        btnFlip.setOnClickListener {
            camera.switchLens()
            synchronized(lock) { frames.clear() }
            restartWindow()
            if (mode == Mode.LIVE) clearResult()
        }
        modeLive.setOnClickListener { setMode(Mode.LIVE) }
        modeTake.setOnClickListener { setMode(Mode.TAKE) }
        btnAction.setOnClickListener { onAction() }

        val prefs = getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        mode = if (prefs.getString("mode", "") == Mode.TAKE.name) Mode.TAKE else Mode.LIVE
        showMode()
        val first = models.firstOrNull { it.id == prefs.getString("model", "") } ?: models.firstOrNull()
        if (first != null) {
            selectModel(first)
        } else {
            modelTitle.text = "No model found"
            modelSubtitle.text = "Run models/export_models.py and rebuild"
            banner.text = "No usable model in this build.\n$loadErrors"
            setButton(Btn.NONE)
        }
    }

    /** Every assets/<id>.aislm whose input layout is the one this app's Normalizer produces. */
    private fun loadModels() {
        val errors = StringBuilder()
        val found = ArrayList<SignModel>()
        for (name in (assets.list("") ?: emptyArray()).filter { it.endsWith(".aislm") }.sorted()) {
            try {
                val m = assets.open(name).use { SignModel.parse(it.readBytes()) }
                val steps = Math.rint(Normalizer.RESAMPLE_SEC * Normalizer.RESAMPLE_HZ).toInt()
                check(m.featureSpecVersion == Normalizer.SPEC_VERSION) {
                    "made for feature spec v${m.featureSpecVersion}, this app writes v${Normalizer.SPEC_VERSION}"
                }
                check(m.inFeatures == Normalizer.FEATURE_COLUMNS.size && m.seqLen == steps && m.hz == Normalizer.RESAMPLE_HZ) {
                    "expects ${m.seqLen} x ${m.inFeatures} at ${m.hz} Hz, this app produces " +
                        "$steps x ${Normalizer.FEATURE_COLUMNS.size} at ${Normalizer.RESAMPLE_HZ} Hz"
                }
                found += m
            } catch (e: Throwable) {
                errors.append(name).append(": ").append(e.message).append('\n')
            }
        }
        models = found.sortedWith(compareBy({ it.order }, { it.id }))
        loadErrors = errors.toString().trim()
    }

    internal val cameraRunning: Boolean get() = camera.running

    private fun usesCamera(m: SignModel) =
        m.camera == SignModel.Need.REQUIRED || (m.camera == SignModel.Need.OPTIONAL && optCamera)

    private fun usesGlove(m: SignModel) = m.glove != SignModel.Need.OFF

    internal fun selectModel(m: SignModel) {
        model = m
        getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putString("model", m.id).apply()
        optCamera = false
        switchCamera.isChecked = false
        paused = false
        modelTitle.text = m.title
        modelSubtitle.text = "${m.subtitle} · ${m.classes.size} signs"
        modelCard.contentDescription = "Model: ${m.title}, ${m.subtitle}. Tap to change."
        bars.setClasses(m.classes)
        applyInputs()
        restartWindow()
        clearResult()
    }

    private fun pickModel() {
        if (models.isEmpty() || cal != null) return
        val adapter = object : ArrayAdapter<SignModel>(this, R.layout.item_model, models) {
            override fun getView(position: Int, convertView: View?, parent: ViewGroup): View {
                val v = convertView ?: layoutInflater.inflate(R.layout.item_model, parent, false)
                val m = models[position]
                v.findViewById<RadioButton>(R.id.itemRadio).isChecked = m === model
                v.findViewById<TextView>(R.id.itemTitle).text = m.title
                v.findViewById<TextView>(R.id.itemSubtitle).text =
                    if (m.note.isEmpty()) m.subtitle else "${m.subtitle}\n${m.note}"
                return v
            }
        }
        AlertDialog.Builder(this)
            .setTitle("Choose a model")
            .setAdapter(adapter) { _, which -> if (models[which] !== model) selectModel(models[which]) }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun setMode(m: Mode) {
        if (m == mode || cal != null) return
        mode = m
        getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putString("mode", m.name).apply()
        paused = false
        showMode()
        restartWindow()
        clearResult()
    }

    private fun showMode() {
        for ((v, on) in listOf(modeLive to (mode == Mode.LIVE), modeTake to (mode == Mode.TAKE))) {
            if (on) v.setBackgroundResource(R.drawable.inf_segment_on) else v.background = null
            v.setTextColor(ContextCompat.getColor(this, if (on) R.color.inf_text else R.color.inf_text2))
            v.isSelected = on
        }
    }

    // ------------------------------------------------------------------ permissions + inputs on/off
    private fun hasCameraPermission() =
        ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED

    private fun bluetoothPermissions(): List<String> =
        if (Build.VERSION.SDK_INT >= 31) listOf(Manifest.permission.BLUETOOTH_SCAN, Manifest.permission.BLUETOOTH_CONNECT)
        else listOf(Manifest.permission.ACCESS_FINE_LOCATION)

    private fun hasBluetoothPermission() =
        bluetoothPermissions().all { ContextCompat.checkSelfPermission(this, it) == PackageManager.PERMISSION_GRANTED }

    /** Turns on exactly what the chosen model uses and turns the camera off when it does not. */
    private fun applyInputs() {
        val m = model ?: return
        val useCam = usesCamera(m)
        val useGlove = usesGlove(m)

        val missing = ArrayList<String>()
        if (useCam && !hasCameraPermission()) missing += Manifest.permission.CAMERA
        if (useGlove && !hasBluetoothPermission()) missing += bluetoothPermissions()
        if (started && missing.isNotEmpty() && !asked.containsAll(missing)) {   // ask once by itself
            asked += missing
            permissionLauncher.launch(missing.toTypedArray())
        }

        if (useCam && hasCameraPermission()) {
            if (started) startCamera()
        } else {
            camera.stop()
            synchronized(lock) {
                frames.clear()
                lastHandT = -1e9
            }
        }
        if (useGlove && hasBluetoothPermission()) glove.start()   // shared with the recorder; no-op if running

        overlay.visibility = if (useCam) View.VISIBLE else View.GONE
        btnFlip.visibility = if (useCam) View.VISIBLE else View.GONE
        gloveView.visibility = if (useCam) View.GONE else View.VISIBLE
        switchCamera.visibility = if (m.camera == SignModel.Need.OPTIONAL) View.VISIBLE else View.GONE
    }

    private fun startCamera() {
        val c = cfg ?: return
        if (tracker != null) {
            camera.start()
            return
        }
        if (trackerStarting) return
        trackerStarting = true
        try {
            camera.executor.execute {
                try {
                    tracker = HandTracker(applicationContext, c)
                    cameraError = ""
                } catch (e: Throwable) {
                    cameraError = "MediaPipe setup failed: ${e.message}"
                }
                ui.post {
                    trackerStarting = false
                    val m = model
                    if (started && tracker != null && m != null && usesCamera(m) && hasCameraPermission()) camera.start()
                }
            }
        } catch (e: RejectedExecutionException) {
            trackerStarting = false
        }
    }

    override fun onStart() {
        super.onStart()
        started = true
        wasReady = false
        applyInputs()
        restartWindow()
        ui.removeCallbacks(ticker)
        ui.post(ticker)
    }

    override fun onStop() {
        super.onStop()
        started = false
        ui.removeCallbacks(ticker)
        take = null
        cal = null
        epoch++
    }

    override fun onDestroy() {
        super.onDestroy()
        destroyed = true
        ui.removeCallbacks(ticker)
        try {
            camera.executor.execute {
                tracker?.close()
                tracker = null
            }
        } catch (_: RejectedExecutionException) {
        }
        camera.shutdown()
        inferExec.shutdown()
        // the glove stays connected: it belongs to the whole app (AppSession)
    }

    // ------------------------------------------------------------------ camera thread
    private fun onFrame(frame: CameraPipeline.Frame) {
        val trk = tracker ?: return
        val tSec = frame.tFrameNs / 1e9
        val hands = try {
            trk.process(frame.bitmap, tSec)
        } catch (e: Exception) {
            cameraError = "MediaPipe: ${e.message}"
            return
        }
        if (cameraError.isNotEmpty()) cameraError = ""   // a failed frame must not block for good
        val (g, _) = picker.pick(hands, tSec)
        synchronized(lock) {
            if (frames.isNotEmpty() && tSec <= frames.last().t) return   // keep time strictly increasing
            frames.addLast(SignWindow.Frame(tSec, g))
            while (frames.first().t < tSec - KEEP_FRAMES_SEC) frames.removeFirst()
            imageW = frame.bitmap.width
            imageH = frame.bitmap.height
            if (g != null) lastHandT = tSec
        }
        val drawn = hands.map { Pair(it, it === g) }
        ui.post { if (started) overlay.setFrame(frame.bitmap, drawn) }
    }

    // ------------------------------------------------------------------ the 100 ms tick (main thread)
    private val ticker = object : Runnable {
        override fun run() {
            if (!started) return
            try {
                tick()
            } finally {
                ui.postDelayed(this, TICK_MS)
            }
        }
    }

    private fun readInputs(m: SignModel, now: Double): Inputs {
        val useCam = usesCamera(m)
        val useGlove = usesGlove(m)
        val camPerm = hasCameraPermission()
        val btPerm = hasBluetoothPermission()
        var newest = -1e9
        var hand = -1e9
        var n1s = 0
        synchronized(lock) {
            if (frames.isNotEmpty()) newest = frames.last().t
            hand = lastHandT
            for (f in frames) if (f.t >= now - 1.0) n1s++
        }
        val camRunning = useCam && now - newest <= CAMERA_FRESH_SEC
        val handVisible = camRunning && now - hand <= HAND_FRESH_SEC
        val last = glove.latest()
        val gloveLive = glove.connected && last != null && now - last.t <= GLOVE_FRESH_SEC
        val calValid = AppSession.flexCalValid(glove)

        // the first thing that stops this model from running, and the button that fixes it
        val block: Pair<String, Btn>? = when {
            useCam && !camPerm -> Pair("The camera permission is needed", Btn.ALLOW_CAMERA)
            useGlove && !btPerm -> Pair("The Bluetooth permission is needed\nfor the glove", Btn.ALLOW_BLUETOOTH)
            useCam && cameraError.isNotEmpty() -> Pair(cameraError, Btn.WAIT)
            useCam && camera.lastError.isNotEmpty() && !camRunning -> Pair(camera.lastError, Btn.WAIT)
            useGlove && !gloveLive -> Pair(
                "Waiting for the glove\n" + when {
                    glove.connected -> "connected, no data yet"
                    glove.lastError.isNotEmpty() -> glove.lastError
                    else -> glove.state
                }, Btn.WAIT)
            useCam && !camRunning -> Pair("Starting the camera…", Btn.WAIT)
            useGlove && !calValid -> Pair("Calibrate the glove first\nopen hand, then a fist (6 s)", Btn.CALIBRATE)
            else -> null
        }
        return Inputs(useCam, useGlove, camPerm, btPerm, camRunning, handVisible, n1s.toDouble(),
            gloveLive, glove.rateHz(), calValid, block?.first, block?.second ?: Btn.NONE)
    }

    private fun tick() {
        val m = model ?: return
        val now = GloveBle.nowSec()
        val inp = readInputs(m, now)
        showChips(inp)
        if (!inp.useCam) showGlovePanel(inp)

        val ready = inp.blocking == null && cal == null
        if (ready && !wasReady) restartWindow()            // inputs just became usable: collect from now
        if (!ready && wasReady) {
            if (take != null) Toast.makeText(this, "Take cancelled", Toast.LENGTH_SHORT).show()
            take = null
            epoch++
            if (mode == Mode.LIVE) clearResult()
        }
        wasReady = ready

        when {
            cal != null -> stepCalibration(inp)
            inp.blocking != null -> {
                setBanner(inp.blocking)
                progress.visibility = View.INVISIBLE
                setButton(inp.blockButton)
            }
            mode == Mode.TAKE -> stepTake(m, now, inp)
            else -> stepLive(m, inp)
        }
    }

    private fun restartWindow() {
        epoch++
        take = null
        tValidFrom = GloveBle.nowSec()
        lastLiveMs = 0L
        progress.visibility = View.INVISIBLE
    }

    // ------------------------------------------------------------------ live mode
    private fun stepLive(m: SignModel, inp: Inputs) {
        if (paused) {
            setBanner("")
            progress.visibility = View.INVISIBLE
            setButton(Btn.RESUME)
            return
        }
        setButton(Btn.PAUSE)
        if (inp.useCam && m.camera == SignModel.Need.REQUIRED && !inp.handVisible) setBanner("Show your signing hand\nto the camera")
        else setBanner("")
        val nowMs = SystemClock.uptimeMillis()
        if (nowMs - lastLiveMs < LIVE_PERIOD_MS || !inferBusy.compareAndSet(false, true)) return
        lastLiveMs = nowMs
        val ep = epoch
        val validFrom = tValidFrom
        val useCam = inp.useCam
        val useGlove = inp.useGlove
        val flexCal = if (useGlove) AppSession.flexCal?.cal else null
        submit {
            val tNewest = if (useCam) synchronized(lock) { frames.lastOrNull()?.t } else glove.latest()?.t
            val tRec0 = tNewest?.let { SignWindow.liveStart(it) }
            if (tRec0 == null || tRec0 < validFrom) {
                val frac = if (tNewest == null) 0.0 else (tNewest - validFrom) / (SignWindow.DURATION_SEC - SignWindow.STEP_SEC)
                ui.post { if (ep == epoch && started) showCollecting(frac) }
            } else {
                val out = infer(m, tRec0, useCam, useGlove, flexCal, fromTake = false)
                ui.post { if (ep == epoch && started && !paused) showOutcome(out) }
            }
        }
    }

    // ------------------------------------------------------------------ 4 s take mode
    private fun stepTake(m: SignModel, now: Double, inp: Inputs) {
        val tk = take
        if (tk == null) {
            setButton(Btn.START_TAKE)
            progress.visibility = View.INVISIBLE
            setBanner(when {
                m.camera == SignModel.Need.REQUIRED && !inp.handVisible -> "Show your signing hand\nto the camera"
                !showingResult -> "Press Start take,\nthen sign after the countdown"
                else -> ""
            })
            return
        }
        setButton(Btn.CANCEL_TAKE)
        val tRec = now - tk.tRec0
        progress.visibility = View.VISIBLE
        when {
            tRec < 0 -> {
                setBanner("Get ready\n${Math.ceil(-tRec).toInt()}")
                progress.progress = 0
            }
            tRec < SignWindow.DURATION_SEC -> {
                setBanner("Sign now\n" + String.format(Locale.US, "%.1f s", SignWindow.DURATION_SEC - tRec))
                progress.progress = (tRec / SignWindow.DURATION_SEC * 1000).toInt()
            }
            else -> {
                setBanner("Reading the take…")
                progress.progress = 1000
                if (tk.submitted) return
                // wait until the last frames / glove samples of the window have arrived
                val newest = if (inp.useCam) synchronized(lock) { frames.lastOrNull()?.t } else glove.latest()?.t
                val complete = newest != null && newest >= tk.tRec0 + SignWindow.DURATION_SEC
                if (!complete && tRec < SignWindow.DURATION_SEC + TAKE_WAIT_SEC) return
                if (!inferBusy.compareAndSet(false, true)) return
                tk.submitted = true
                val ep = epoch
                val useCam = inp.useCam
                val useGlove = inp.useGlove
                val flexCal = if (useGlove) AppSession.flexCal?.cal else null
                val tRec0 = tk.tRec0
                submit {
                    val out = infer(m, tRec0, useCam, useGlove, flexCal, fromTake = true)
                    ui.post {
                        if (ep == epoch && started) {
                            take = null
                            progress.visibility = View.INVISIBLE
                            showOutcome(out)
                        }
                    }
                }
            }
        }
    }

    // ------------------------------------------------------------------ inference (background thread)
    private fun submit(job: () -> Unit) {
        if (destroyed) {
            inferBusy.set(false)
            return
        }
        try {
            inferExec.execute {
                try {
                    job()
                } catch (e: Throwable) {
                    val msg = "Inference failed: ${e.message}"
                    ui.post { if (started) showError(msg) }
                } finally {
                    inferBusy.set(false)
                }
            }
        } catch (e: RejectedExecutionException) {
            inferBusy.set(false)
        }
    }

    /** One window [tRec0, tRec0 + 4 s) -> features -> model. Inputs the model does not use are left out. */
    private fun infer(
        m: SignModel, tRec0: Double, useCam: Boolean, useGlove: Boolean, flexCal: FlexCalibration?, fromTake: Boolean,
    ): Outcome {
        val t0 = SystemClock.elapsedRealtimeNanos()
        val fr: List<SignWindow.Frame>
        var w = 1
        var h = 1
        if (useCam) {
            synchronized(lock) {
                fr = frames.filter { it.t >= tRec0 - 0.1 && it.t <= tRec0 + SignWindow.DURATION_SEC + 0.1 }
                w = maxOf(imageW, 1)
                h = maxOf(imageH, 1)
            }
        } else {
            fr = SignWindow.gridFrames(tRec0)
        }
        val gl = if (useGlove) glove.window(tRec0 - 0.1, tRec0 + SignWindow.DURATION_SEC + 0.1) else emptyList()
        val win = SignWindow.build(fr, gl, tRec0, w.toDouble(), h.toDouble(), flexCal)
        val noHand = m.camera == SignModel.Need.REQUIRED && win.handValidFrac == 0.0
        val noGlove = m.glove == SignModel.Need.REQUIRED && win.gloveValidFrac == 0.0
        val pred = if (noHand || noGlove) null else m.predict(win.x)
        val ms = (SystemClock.elapsedRealtimeNanos() - t0) / 1e6
        return Outcome(win, pred, ms, m, useCam, useGlove, fromTake)
    }

    // ------------------------------------------------------------------ glove calibration (main thread)
    private fun startCalibration() {
        if (cal != null || take != null) return
        val m = model ?: return
        if (!usesGlove(m)) return
        val last = glove.latest()
        if (!glove.connected || last == null || GloveBle.nowSec() - last.t > GLOVE_FRESH_SEC) {
            Toast.makeText(this, "The glove is not sending data yet", Toast.LENGTH_SHORT).show()
            return
        }
        epoch++
        clearResult()
        glove.sendCommand("CAL")   // open-hand pose = the glove's own zero, like the recorder's Cal
        cal = CalState(0, SystemClock.elapsedRealtime() + (FlexCalibration.HOLD_SEC * 1000).toLong())
    }

    private fun stepCalibration(inp: Inputs) {
        val c = cal ?: return
        setButton(Btn.CANCEL_CAL)
        val lastSample = glove.latest()
        if (calibrationLost(glove.connected, lastSample?.let { GloveBle.nowSec() - it.t })) {
            cal = null
            progress.visibility = View.INVISIBLE
            AlertDialog.Builder(this).setTitle("Calibration stopped")
                .setMessage("No data from the glove for more than ${CAL_STALL_SEC} s. Check that it is on and near the phone, then calibrate again.")
                .setPositiveButton("OK", null).show()
            return
        }
        val leftMs = c.tEndMs - SystemClock.elapsedRealtime()
        val total = FlexCalibration.HOLD_SEC * 1000
        progress.visibility = View.VISIBLE
        progress.progress = ((1 - leftMs / total).coerceIn(0.0, 1.0) * 1000).toInt()
        if (leftMs > 0) {
            val left = String.format(Locale.US, "%.1f s", leftMs / 1000.0)
            setBanner(if (c.phase == 0) "Step 1 of 2: OPEN hand\nfingers straight, flat, still\n$left"
            else "Step 2 of 2: TIGHT FIST\nhold it\n$left")
            return
        }
        val samples = glove.recent(FlexCalibration.AVG_SEC).map { it.values }
        if (c.phase == 0) {
            c.open = samples
            c.phase = 1
            c.tEndMs = SystemClock.elapsedRealtime() + total.toLong()
            return
        }
        cal = null
        progress.visibility = View.INVISIBLE
        try {
            val fc = FlexCalibration.fromSamples(c.open ?: emptyList(), samples)
            AppSession.flexCal = AppSession.StoredCal(
                fc, LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss")),
                glove.connectionId, glove.calibration,
            )
            Toast.makeText(this, "Glove calibrated", Toast.LENGTH_SHORT).show()
        } catch (e: IllegalArgumentException) {
            AppSession.flexCal = null
            AlertDialog.Builder(this).setTitle("Calibration failed")
                .setMessage(e.message).setPositiveButton("OK", null).show()
        }
        wasReady = false   // start a fresh window with the new calibration
    }

    // ------------------------------------------------------------------ main button
    private fun setButton(b: Btn) {
        if (b == button && btnAction.text.isNotEmpty()) return
        button = b
        btnAction.text = when (b) {
            Btn.NONE -> "No model"
            Btn.ALLOW_CAMERA -> "Allow camera"
            Btn.ALLOW_BLUETOOTH -> "Allow Bluetooth"
            Btn.CALIBRATE -> "Calibrate glove"
            Btn.CANCEL_CAL -> "Cancel calibration"
            Btn.WAIT -> "Waiting…"
            Btn.START_TAKE -> "Start take"
            Btn.CANCEL_TAKE -> "Cancel"
            Btn.PAUSE -> "Pause"
            Btn.RESUME -> "Resume"
        }
        btnAction.isEnabled = b != Btn.NONE && b != Btn.WAIT
    }

    private fun onAction() {
        when (button) {
            Btn.ALLOW_CAMERA -> permissionLauncher.launch(arrayOf(Manifest.permission.CAMERA))
            Btn.ALLOW_BLUETOOTH -> permissionLauncher.launch(bluetoothPermissions().toTypedArray())
            Btn.CALIBRATE -> startCalibration()
            Btn.CANCEL_CAL -> {
                cal = null
                progress.visibility = View.INVISIBLE
            }
            Btn.START_TAKE -> {
                epoch++
                clearResult()
                take = TakeState(GloveBle.nowSec() + COUNTDOWN_SEC)
            }
            Btn.CANCEL_TAKE -> {
                take = null
                epoch++
                progress.visibility = View.INVISIBLE
            }
            Btn.PAUSE -> paused = true
            Btn.RESUME -> {
                paused = false
                lastLiveMs = 0L
            }
            Btn.NONE, Btn.WAIT -> Unit
        }
        if (started) tick()
    }

    // ------------------------------------------------------------------ what is shown
    private fun setBanner(text: String) {
        if (banner.text.toString() != text) banner.text = text
        gloveView.dimmed = text.isNotEmpty()   // keep the message readable over the bars
    }

    private fun clearResult() {
        showingResult = false
        resultLabel.text = "–"
        resultLabel.setTextColor(ContextCompat.getColor(this, R.color.inf_text2))
        resultConf.text = ""
        resultHint.text = ""
        resultDetail.text = ""
        bars.setProbs(null)
    }

    private fun showCollecting(frac: Double) {
        clearResult()
        val f = frac.coerceIn(0.0, 1.0)
        progress.visibility = View.VISIBLE
        progress.progress = (f * 1000).toInt()
        resultHint.text = String.format(Locale.US, "Collecting the first 4 s… %.1f s", f * SignWindow.DURATION_SEC)
    }

    private fun showError(msg: String) {
        clearResult()
        showingResult = true
        resultHint.text = msg
    }

    private fun pct(v: Double) = "${Math.round(v * 100)}%"

    internal fun showOutcome(o: Outcome) {
        if (!o.fromTake) progress.visibility = View.INVISIBLE
        val win = o.window
        val detail = ArrayList<String>()
        if (o.usedCam) detail += "hand in ${pct(win.handValidFrac)} of the 4 s"
        if (o.usedGlove) detail += "glove in ${pct(win.gloveValidFrac)}"
        detail += String.format(Locale.US, "%.0f ms", o.ms)
        detail += if (o.fromTake) "take" else "live"
        val p = o.pred
        if (p == null) {
            clearResult()
            showingResult = true
            resultHint.text = when {
                o.model.camera == SignModel.Need.REQUIRED && win.handValidFrac == 0.0 ->
                    "No hand was tracked in these 4 s. Keep the signing hand inside the picture."
                else -> "No calibrated glove data in these 4 s."
            }
            resultDetail.text = detail.joinToString(" · ")
            return
        }
        showingResult = true
        val top = p.top
        val conf = p.probs[top]
        val sure = conf >= CONFIDENT
        val lowHand = o.model.camera == SignModel.Need.REQUIRED && win.handValidFrac < MIN_VALID_FRAC
        val lowGlove = o.model.glove == SignModel.Need.REQUIRED && win.gloveValidFrac < MIN_VALID_FRAC
        resultLabel.text = o.model.classes[top]
        resultLabel.setTextColor(ContextCompat.getColor(this, if (sure && !lowHand && !lowGlove) R.color.inf_text else R.color.inf_warn))
        resultConf.text = pct(conf)
        resultHint.text = when {
            lowHand -> "Hand tracked in only ${pct(win.handValidFrac)} of the 4 s: do not trust this result."
            lowGlove -> "Glove data in only ${pct(win.gloveValidFrac)} of the 4 s: do not trust this result."
            !sure -> "Not sure (below ${pct(CONFIDENT)}). The model always answers one of its ${o.model.classes.size} signs."
            else -> ""
        }
        bars.setProbs(p.probs, top, sure && !lowHand && !lowGlove)
        resultDetail.text = detail.joinToString(" · ")
    }

    private fun chip(v: TextView, colorRes: Int, title: String, status: String) {
        val sb = SpannableStringBuilder()
        sb.append("● ")
        sb.setSpan(ForegroundColorSpan(ContextCompat.getColor(this, colorRes)), 0, 1, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
        val a = sb.length
        sb.append(title)
        sb.setSpan(StyleSpan(Typeface.BOLD), a, sb.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
        sb.setSpan(ForegroundColorSpan(ContextCompat.getColor(this, R.color.inf_text)), a, sb.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
        sb.append('\n').append(status)
        if (v.text.toString() != sb.toString() || v.tag != colorRes) {
            v.text = sb
            v.tag = colorRes
            v.contentDescription = "$title: $status"
        }
    }

    private fun showChips(inp: Inputs) {
        when {
            !inp.useCam -> chip(chipCamera, R.color.inf_idle, "Camera", "off · not used")
            !inp.camPermission -> chip(chipCamera, R.color.inf_bad, "Camera", "no permission")
            !inp.camRunning -> chip(chipCamera, R.color.inf_warn, "Camera", "starting…")
            inp.handVisible -> chip(chipCamera, R.color.inf_ok, "Camera", String.format(Locale.US, "hand tracked · %.0f fps", inp.fps))
            else -> chip(chipCamera, R.color.inf_warn, "Camera", "no hand in view")
        }
        when {
            // say when it is connected anyway, so "not used" is not read as "not connected"
            !inp.useGlove -> chip(chipGlove, R.color.inf_idle, "Glove", if (inp.gloveLive) "connected · not used" else "not used")
            !inp.btPermission -> chip(chipGlove, R.color.inf_bad, "Glove", "no permission")
            inp.gloveLive -> chip(chipGlove, if (inp.gloveHz >= Quality.MIN_GLOVE_HZ) R.color.inf_ok else R.color.inf_warn,
                "Glove", String.format(Locale.US, "connected · %.0f Hz", inp.gloveHz))
            else -> chip(chipGlove, R.color.inf_bad, "Glove", if (glove.connected) "no data" else glove.state)
        }
        when {
            !inp.useGlove -> chip(chipCal, R.color.inf_idle, "Calibration", "not needed")
            cal != null -> chip(chipCal, R.color.inf_warn, "Calibration", "in progress…")
            inp.calValid -> chip(chipCal, R.color.inf_ok, "Calibration", "done · tap to redo")
            else -> chip(chipCal, R.color.inf_bad, "Calibration", "tap to calibrate")
        }
        chipCal.isClickable = inp.useGlove
    }

    private fun showGlovePanel(inp: Inputs) {
        val last = glove.latest()
        if (!inp.gloveLive || last == null) {
            gloveView.set(null, null)
            return
        }
        val v = last.values
        val fc = if (inp.calValid) AppSession.flexCal?.cal else null
        gloveView.set(fc?.normalize(v), DoubleArray(6) { v[5 + it] })
    }
}
