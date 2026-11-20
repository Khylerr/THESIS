package com.aisla.core

import java.nio.ByteBuffer
import java.nio.ByteOrder

/** The 11 sensor values, in the order the ESP32 sends them (same as fslRecorder.GLOVE_COLS). */
val GLOVE_COLS = listOf(
    "flex1", "flex2", "flex3", "flex4", "flex5",
    "acc_x", "acc_y", "acc_z", "gyro_x", "gyro_y", "gyro_z",
)

/** One glove sample on the phone clock (seconds). Same fields as the recorder's buffer items. */
class GloveSample(
    val t: Double,              // t_sync: device time mapped onto the host clock
    val values: DoubleArray,    // 11 values
    val tArrival: Double,       // when the BLE notification arrived
    val seq: Int,
    val flags: Int,
)

/** BLE DATA packet of hand_sign_glove_ble.ino (29 bytes, little-endian). */
class GlovePacket(val seq: Int, val tDevSec: Double, val values: DoubleArray, val flags: Int) {
    companion object {
        const val SIZE = 29

        /** Same as fslRecorder.decode_ble_packet; null if the size is wrong. */
        fun decode(data: ByteArray): GlovePacket? {
            if (data.size != SIZE) return null
            val b = ByteBuffer.wrap(data).order(ByteOrder.LITTLE_ENDIAN)
            val seq = b.short.toInt() and 0xFFFF
            val tMs = b.int.toLong() and 0xFFFFFFFFL
            val v = DoubleArray(11)
            for (i in 0 until 5) v[i] = b.short.toDouble()
            for (i in 5 until 8) v[i] = b.short / 100.0
            for (i in 8 until 11) v[i] = b.short / 1000.0
            val flags = b.get().toInt() and 0xFF
            return GlovePacket(seq, tMs / 1000.0, v, flags)
        }
    }
}

/**
 * Maps the ESP32 clock (millis) onto the host clock. Port of fslRecorder.ClockMapper:
 * offset = min(t_arrival - t_device) over a sliding window (the fastest packets), which
 * removes BLE batching jitter and follows crystal drift; resets if the glove reboots.
 */
class ClockMapper(private val windowSec: Double = 10.0) {
    private val hist = ArrayDeque<DoubleArray>()   // (t_arr, d), d increasing -> O(1) minimum
    var offset: Double? = null
        private set

    fun update(tDev: Double, tArr: Double): Double {
        val d = tArr - tDev
        val prev = offset
        if (prev != null && Math.abs(d - prev) > 1.0) hist.clear()   // glove rebooted / clock jumped
        while (hist.isNotEmpty() && hist.last()[1] >= d) hist.removeLast()
        hist.addLast(doubleArrayOf(tArr, d))
        while (hist.first()[0] < tArr - windowSec) hist.removeFirst()
        val off = hist.first()[1]
        offset = off
        return off
    }
}
