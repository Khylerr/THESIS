package com.aisla.app

import android.content.Context
import com.aisla.core.FlexCalibration

/**
 * What the recorder screen (MainActivity) and the Inference screen share while the app runs:
 * the one BLE glove connection (BLE allows a single central, and reconnecting would throw away
 * the calibration) and this session's two-point flex calibration.
 */
object AppSession {
    /** A flex calibration + what it is tied to: it stops being valid when the glove reconnects or re-zeroes. */
    class StoredCal(val cal: FlexCalibration, val time: String, val connectionId: Int, val gloveStatus: String)

    @Volatile var flexCal: StoredCal? = null

    private var gloveRef: GloveBle? = null

    @Synchronized
    fun glove(context: Context): GloveBle =
        gloveRef ?: GloveBle(context.applicationContext).also { gloveRef = it }

    fun flexCalValid(glove: GloveBle): Boolean {
        val c = flexCal ?: return false
        return c.connectionId == glove.connectionId && c.gloveStatus == glove.calibration
    }
}
