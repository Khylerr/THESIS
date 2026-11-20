package com.aisla.app

import android.Manifest
import android.app.Application
import android.graphics.Bitmap
import android.graphics.Canvas
import android.os.Looper
import android.view.View
import android.widget.TextView
import androidx.appcompat.app.AlertDialog
import androidx.test.core.app.ApplicationProvider
import com.aisla.core.SignModel
import com.aisla.core.SignWindow
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import org.robolectric.shadows.ShadowDialog
import java.io.File
import java.io.FileOutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.time.Duration

/**
 * The Inference screen on the JVM (Robolectric, real layout + real drawing): no phone, camera or
 * glove needed. Checks that the screen opens, offers the four models, and turns the camera /
 * glove requirement off for the unimodal models. Writes a PNG of every state to
 * app/build/inference_screens/ so the layout can be looked at.
 */
@RunWith(RobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [35], qualifiers = "w411dp-h891dp-420dpi")
class InferenceScreenTest {

    private val outDir = File(System.getProperty("screens.dir") ?: "build/inference_screens").apply { mkdirs() }
    private val goldenDir = File(System.getProperty("golden.dir") ?: "../../shared/golden")
    private val bt = arrayOf(Manifest.permission.BLUETOOTH_SCAN, Manifest.permission.BLUETOOTH_CONNECT)

    private fun grant(vararg permissions: String) {
        shadowOf(ApplicationProvider.getApplicationContext<Application>()).grantPermissions(*permissions)
    }

    private fun idle(ms: Long = 350) = shadowOf(Looper.getMainLooper()).idleFor(Duration.ofMillis(ms))

    private fun launch(): InferenceActivity {
        val a = Robolectric.buildActivity(InferenceActivity::class.java).setup().get()
        idle()
        return a
    }

    private fun text(a: InferenceActivity, id: Int) = a.findViewById<TextView>(id).text.toString()
    private fun visible(a: InferenceActivity, id: Int) = a.findViewById<View>(id).visibility == View.VISIBLE

    private fun shot(a: InferenceActivity, name: String) {
        val v = a.window.decorView
        assertTrue("screen not laid out", v.width > 0 && v.height > 0)
        val bmp = Bitmap.createBitmap(v.width, v.height, Bitmap.Config.ARGB_8888)
        v.draw(Canvas(bmp))
        FileOutputStream(File(outDir, "$name.png")).use { bmp.compress(Bitmap.CompressFormat.PNG, 100, it) }
    }

    private fun pick(a: InferenceActivity, id: String) {
        a.selectModel(a.models.first { it.id == id })
        idle()
    }

    @Test
    fun offersTheFourModelsAndRemembersTheChoice() {
        val a = launch()
        assertEquals(
            listOf("multimodal_raw", "multimodal_augmented_60reps", "unimodal_vision_raw", "unimodal_glove_raw"),
            a.models.map { it.id },
        )
        assertEquals("Multimodal", text(a, R.id.modelTitle))            // first in the list by default
        assertEquals("Camera + glove · 7 signs", text(a, R.id.modelSubtitle))

        // the picker lists all four; choosing one switches the model
        a.findViewById<View>(R.id.modelCard).performClick()
        idle()
        val dialog = ShadowDialog.getLatestDialog() as AlertDialog
        assertEquals(4, dialog.listView.adapter.count)
        dialog.window!!.decorView.let { v ->
            val bmp = Bitmap.createBitmap(v.width, v.height, Bitmap.Config.ARGB_8888)
            v.draw(Canvas(bmp))
            FileOutputStream(File(outDir, "00_model_picker.png")).use { bmp.compress(Bitmap.CompressFormat.PNG, 100, it) }
        }
        val row = dialog.listView.adapter.getView(3, null, dialog.listView)
        assertEquals("Glove only", row.findViewById<TextView>(R.id.itemTitle).text.toString())
        dialog.listView.performItemClick(row, 3, 3L)
        idle()
        assertEquals("Glove only", text(a, R.id.modelTitle))

        // reopened: the last model is selected again
        val b = launch()
        assertEquals("Glove only", text(b, R.id.modelTitle))
    }

    @Test
    fun multimodalNeedsCameraGloveAndCalibration() {
        grant(*bt)   // camera permission left out: MediaPipe cannot load on the JVM anyway
        val a = launch()
        pick(a, "multimodal_raw")
        assertTrue(text(a, R.id.chipCamera), text(a, R.id.chipCamera).endsWith("no permission"))
        assertFalse(text(a, R.id.chipGlove).contains("not used"))
        assertTrue(text(a, R.id.chipCal), text(a, R.id.chipCal).contains("tap to calibrate"))
        assertTrue(a.findViewById<View>(R.id.chipCal).isClickable)
        assertTrue(visible(a, R.id.infOverlay))
        assertFalse(visible(a, R.id.gloveView))
        assertFalse(visible(a, R.id.switchCamera))
        assertTrue(text(a, R.id.banner), text(a, R.id.banner).startsWith("The camera permission"))
        assertEquals("Allow camera", text(a, R.id.btnAction))
        shot(a, "01_multimodal_needs_camera_and_glove")
    }

    @Test
    fun visionModelDoesNotAskForTheGlove() {
        grant(Manifest.permission.CAMERA)          // no Bluetooth permission at all
        val a = launch()
        pick(a, "unimodal_vision_raw")
        assertEquals("Vision only", text(a, R.id.modelTitle))
        assertTrue(text(a, R.id.chipGlove), text(a, R.id.chipGlove).endsWith("not used"))
        assertTrue(text(a, R.id.chipCal), text(a, R.id.chipCal).endsWith("not needed"))
        assertFalse(a.findViewById<View>(R.id.chipCal).isClickable)
        assertFalse(text(a, R.id.chipCamera).contains("not used"))
        assertTrue(visible(a, R.id.infOverlay))
        assertTrue(visible(a, R.id.btnFlip))
        assertFalse(visible(a, R.id.gloveView))
        val banner = text(a, R.id.banner)
        assertFalse(banner, banner.contains("glove", ignoreCase = true) || banner.contains("Bluetooth"))
        assertFalse(text(a, R.id.btnAction).contains("Bluetooth") || text(a, R.id.btnAction).contains("Calibrate"))
        shot(a, "02_vision_only")
    }

    @Test
    fun gloveModelTurnsTheCameraOff() {
        grant(*bt)                                 // no camera permission at all
        val a = launch()
        pick(a, "unimodal_glove_raw")
        assertEquals("Glove only", text(a, R.id.modelTitle))
        assertTrue(text(a, R.id.chipCamera), text(a, R.id.chipCamera).endsWith("off · not used"))
        assertFalse(text(a, R.id.chipGlove).contains("not used"))
        assertFalse(visible(a, R.id.infOverlay))
        assertFalse(visible(a, R.id.btnFlip))
        assertTrue(visible(a, R.id.gloveView))
        assertTrue(visible(a, R.id.switchCamera))  // optional: feed the camera as in training
        assertFalse(a.cameraRunning)
        val banner = text(a, R.id.banner)
        assertTrue(banner, banner.startsWith("Waiting for the glove"))
        assertFalse(text(a, R.id.btnAction).contains("camera", ignoreCase = true))
        shot(a, "03_glove_only_waiting_for_glove")

        // back to a camera model: the camera part is shown again
        pick(a, "multimodal_raw")
        assertTrue(visible(a, R.id.infOverlay))
        assertFalse(visible(a, R.id.gloveView))
        assertFalse(visible(a, R.id.switchCamera))
    }

    @Test
    fun withoutPermissionsTheButtonAsksOnlyForWhatTheModelUses() {
        val a = launch()
        pick(a, "unimodal_vision_raw")
        assertEquals("Allow camera", text(a, R.id.btnAction))
        pick(a, "unimodal_glove_raw")
        assertEquals("Allow Bluetooth", text(a, R.id.btnAction))
        pick(a, "multimodal_augmented_60reps")
        assertEquals("Allow camera", text(a, R.id.btnAction))
        assertTrue(a.findViewById<View>(R.id.btnAction).isEnabled)
        shot(a, "04_multimodal_no_permission")
    }

    @Test
    fun modeSwitchKeepsTheScreenConsistent() {
        val a = launch()
        a.findViewById<View>(R.id.modeTake).performClick()
        idle()
        assertTrue(a.findViewById<View>(R.id.modeTake).isSelected)
        assertFalse(a.findViewById<View>(R.id.modeLive).isSelected)
        val b = launch()                           // mode is remembered
        assertTrue(b.findViewById<View>(R.id.modeTake).isSelected)
        b.findViewById<View>(R.id.modeLive).performClick()
        idle()
        assertTrue(b.findViewById<View>(R.id.modeLive).isSelected)
    }

    /**
     * The glove goes silent for about 0.7 s when it gets "CAL" (it is zeroing itself). That must
     * not stop the calibration; only a real loss of the glove may.
     */
    @Test
    fun calibrationSurvivesTheGlovesZeroingPause() {
        assertFalse(InferenceActivity.calibrationLost(connected = true, lastSampleAgeSec = 0.02))
        assertFalse(InferenceActivity.calibrationLost(connected = true, lastSampleAgeSec = 0.7))    // normal CAL pause
        assertFalse(InferenceActivity.calibrationLost(connected = true, lastSampleAgeSec = 1.8))    // CAL + IMU re-init
        assertTrue(InferenceActivity.calibrationLost(connected = true, lastSampleAgeSec = 3.0))     // really silent
        assertTrue(InferenceActivity.calibrationLost(connected = false, lastSampleAgeSec = 0.02))   // link dropped
        assertTrue(InferenceActivity.calibrationLost(connected = true, lastSampleAgeSec = null))    // never sent
        // the pause must fit inside the open-hand hold before its averaged last second starts
        assertTrue(InferenceActivity.CAL_STALL_SEC > InferenceActivity.GLOVE_FRESH_SEC)
        assertTrue(InferenceActivity.CAL_STALL_SEC < com.aisla.core.FlexCalibration.HOLD_SEC)
    }

    /** A prediction on the screen: uses a golden input, so the label must be PyTorch's answer. */
    @Test
    fun resultCardShowsThePrediction() {
        val a = launch()
        val buf = ByteBuffer.wrap(File(goldenDir, "sign_model/inputs.f32").readBytes()).order(ByteOrder.LITTLE_ENDIAN)
        val cases = File(goldenDir, "sign_model/cases.txt").readLines().filter { it.isNotEmpty() }.map { it.substringAfter(' ') }
        val xs = List(cases.size) { Array(120) { DoubleArray(79) { buf.float.toDouble() } } }

        fun show(modelId: String, case: String, hand: Double, glove: Double, name: String): String {
            pick(a, modelId)
            val m: SignModel = a.models.first { it.id == modelId }
            val x = xs[cases.indexOf(case)]
            val win = SignWindow.Window(x, 110, hand, glove)
            a.showOutcome(InferenceActivity.Outcome(win, m.predict(x), 3.2, m, usedCam = m.id != "unimodal_glove_raw",
                usedGlove = m.id != "unimodal_vision_raw", fromTake = false))
            idle(50)
            shot(a, name)
            val expected = File(goldenDir, "sign_model/${modelId}_expected.csv").readLines()
                .first { it.startsWith("$case,") }.substringAfterLast(',')
            assertEquals(expected, text(a, R.id.resultLabel))
            return text(a, R.id.resultHint)
        }

        // confident answer
        assertEquals("", show("multimodal_raw", "phone_take_home_glove_calibrated", 1.0, 1.0, "05_result_confident"))
        assertTrue(text(a, R.id.resultConf).endsWith("%"))
        // below 60 %: flagged as not sure
        assertTrue(show("multimodal_raw", "training_like_means", 1.0, 1.0, "06_result_not_sure").startsWith("Not sure"))
        // little hand in the window: flagged as unreliable
        assertTrue(show("unimodal_vision_raw", "random_normal", 0.3, 0.0, "07_result_low_hand").startsWith("Hand tracked in only 30%"))

        // no hand at all -> no answer
        pick(a, "unimodal_vision_raw")
        val m = a.models.first { it.id == "unimodal_vision_raw" }
        a.showOutcome(InferenceActivity.Outcome(SignWindow.Window(xs[1], 0, 0.0, 0.0), null, 1.0, m, true, false, true))
        assertEquals("–", text(a, R.id.resultLabel))
        assertTrue(text(a, R.id.resultHint).startsWith("No hand was tracked"))
        shot(a, "08_result_no_hand")
    }

    /** Normal phone: everything is on one screen, no scrolling, and the picture area is large. */
    @Test
    fun fitsANormalPhoneWithoutScrolling() {
        grant(*bt)
        val a = launch()
        val scroll = a.findViewById<android.widget.ScrollView>(R.id.infRoot)
        val content = a.findViewById<View>(R.id.infContent)
        val density = a.resources.displayMetrics.density
        for (id in listOf("unimodal_glove_raw", "multimodal_raw", "unimodal_vision_raw")) {
            pick(a, id)
            assertEquals("$id scrolls", scroll.height - scroll.paddingTop - scroll.paddingBottom, content.height)
            assertTrue("$id picture area", a.findViewById<View>(R.id.stage).height >= 250 * density)
        }
    }

    /** Short phone: nothing is squeezed away; the page scrolls instead. */
    @Test
    @Config(sdk = [35], qualifiers = "w360dp-h640dp-xhdpi")
    fun fitsASmallPhone() {
        grant(*bt)
        val a = launch()
        val scroll = a.findViewById<android.widget.ScrollView>(R.id.infRoot)
        val content = a.findViewById<View>(R.id.infContent)
        for (id in listOf("unimodal_glove_raw", "multimodal_raw")) {
            pick(a, id)
            val stage = a.findViewById<View>(R.id.stage)
            val action = a.findViewById<View>(R.id.btnAction)
            val density = a.resources.displayMetrics.density
            assertTrue("$id: picture area only ${stage.height / density} dp tall", stage.height >= 170 * density)
            assertTrue(a.findViewById<View>(R.id.bars).height >= 7 * 20 * density)
            assertTrue("$id: main button is cut", action.height >= 48 * density)
            // the page is taller than this screen, so it must scroll down to the main button
            assertTrue("$id: nothing to scroll", content.height > scroll.height - scroll.paddingTop - scroll.paddingBottom)
            shot(a, "09_small_phone_${id}_top")
            scroll.scrollTo(0, content.height)
            idle(50)
            val loc = IntArray(2)
            action.getLocationInWindow(loc)
            assertTrue("$id: main button not reachable by scrolling", loc[1] + action.height <= scroll.height)
            shot(a, "09_small_phone_${id}_scrolled")
            scroll.scrollTo(0, 0)
        }
    }
}
