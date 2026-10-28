package com.aisla.app

import android.annotation.SuppressLint
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCallback
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothGattDescriptor
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothProfile
import android.bluetooth.BluetoothStatusCodes
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanFilter
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.Context
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.ParcelUuid
import android.os.SystemClock
import com.aisla.core.ClockMapper
import com.aisla.core.GlovePacket
import com.aisla.core.GloveSample
import com.aisla.core.PyFormat
import com.aisla.core.Stats
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import kotlin.random.Random

/**
 * BLE glove reader: port of fslRecorder.BleGloveReader for hand_sign_glove_ble.ino.
 *
 * Each 29-byte packet carries the ESP32's millis(); ClockMapper maps it onto the phone clock
 * (SystemClock.elapsedRealtimeNanos, in seconds), the clock the camera frames use. Samples go
 * into a rolling 30 s buffer; the take's slice is taken afterwards, like the recorder does.
 * Permissions (BLUETOOTH_SCAN/CONNECT or location on old Android) are requested by MainActivity.
 */
@SuppressLint("MissingPermission")
class GloveBle(private val context: Context, val deviceName: String = DEVICE_NAME) {

    // ---- state shown in the UI / saved with each take ----
    @Volatile var connected = false
        private set
    @Volatile var state = "idle"
        private set
    @Volatile var lastError = ""
        private set
    @Volatile var lastStatus = ""
        private set
    @Volatile var calibration = ""
        private set
    @Volatile var mtu: Int? = null
        private set
    @Volatile var nBad = 0
        private set
    @Volatile var nDropped = 0
        private set
    /** +1 on every (re)connect: a flex calibration from an earlier connection no longer applies. */
    @Volatile var connectionId = 0
        private set

    private val lock = Any()
    private val buf = ArrayDeque<GloveSample>()
    private val clock = ClockMapper()
    private var lastSeq: Int? = null
    private var gatt: BluetoothGatt? = null
    private var scanning = false
    private var wanted = false
    private val main = Handler(Looper.getMainLooper())
    private val pongTimes = ConcurrentHashMap<String, Double>()
    private val pongLatches = ConcurrentHashMap<String, CountDownLatch>()

    // ---------------------------------------------------------------- lifecycle
    fun start() {
        main.post {
            wanted = true
            if (gatt == null && !scanning) scan()
        }
    }

    fun stop() {
        main.post {
            wanted = false
            stopScan()
            gatt?.disconnect()
            gatt?.close()
            gatt = null
            connected = false
            state = "stopped"
        }
    }

    private fun adapter() = context.getSystemService(BluetoothManager::class.java)?.adapter

    private fun scan() {
        val a = adapter()
        if (a == null || !a.isEnabled) {
            lastError = "Bluetooth is off"
            state = "waiting for Bluetooth"
            retry(2000)
            return
        }
        val scanner = a.bluetoothLeScanner ?: run { retry(2000); return }
        val filters = listOf(
            ScanFilter.Builder().setServiceUuid(ParcelUuid(SERVICE_UUID)).build(),
            ScanFilter.Builder().setDeviceName(deviceName).build(),
        )
        val settings = ScanSettings.Builder().setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY).build()
        try {
            scanner.startScan(filters, settings, scanCallback)
        } catch (e: SecurityException) {
            lastError = "no Bluetooth permission"
            return
        }
        scanning = true
        state = "scanning"
        main.postDelayed(scanTimeout, 10_000)
    }

    private val scanTimeout = Runnable {
        if (scanning) {
            stopScan()
            lastError = "'$deviceName' not found (glove off, or connected to another device?)"
            retry(1000)
        }
    }

    private fun stopScan() {
        main.removeCallbacks(scanTimeout)
        if (!scanning) return
        scanning = false
        try {
            adapter()?.bluetoothLeScanner?.stopScan(scanCallback)
        } catch (_: Exception) {
        }
    }

    private fun retry(delayMs: Long) {
        main.postDelayed({ if (wanted && gatt == null && !scanning) scan() }, delayMs)
    }

    private val scanCallback = object : ScanCallback() {
        override fun onScanResult(callbackType: Int, result: ScanResult) {
            main.post {
                if (!scanning) return@post
                stopScan()
                connect(result.device)
            }
        }

        override fun onScanFailed(errorCode: Int) {
            main.post {
                scanning = false
                lastError = "BLE scan failed ($errorCode)"
                retry(2000)
            }
        }
    }

    private fun connect(device: BluetoothDevice) {
        state = "connecting to ${device.address}"
        gatt = device.connectGatt(context, false, gattCallback, BluetoothDevice.TRANSPORT_LE)
    }

    // ---------------------------------------------------------------- GATT
    private val gattCallback = object : BluetoothGattCallback() {
        override fun onConnectionStateChange(g: BluetoothGatt, status: Int, newState: Int) {
            if (newState == BluetoothProfile.STATE_CONNECTED && status == BluetoothGatt.GATT_SUCCESS) {
                state = "negotiating"
                g.requestConnectionPriority(BluetoothGatt.CONNECTION_PRIORITY_HIGH)   // short interval, low latency
                if (!g.requestMtu(100)) g.discoverServices()   // packet is 29 bytes; default payload is 20
            } else {
                connected = false
                lastSeq = null
                if (status != BluetoothGatt.GATT_SUCCESS) lastError = "disconnected (status $status)"
                main.post {
                    g.close()
                    if (gatt === g) gatt = null
                    state = "disconnected"
                    retry(1000)
                }
            }
        }

        override fun onMtuChanged(g: BluetoothGatt, mtu: Int, status: Int) {
            this@GloveBle.mtu = mtu
            g.discoverServices()
        }

        override fun onServicesDiscovered(g: BluetoothGatt, status: Int) {
            if (g.getService(SERVICE_UUID) == null) {
                lastError = "glove service not found (old Bluetooth Classic firmware?)"
                g.disconnect()
                return
            }
            if (!enableNotify(g, STATUS_UUID)) lastError = "could not subscribe to STATUS"
        }

        override fun onDescriptorWrite(g: BluetoothGatt, d: BluetoothGattDescriptor, status: Int) {
            when (d.characteristic.uuid) {
                STATUS_UUID -> if (!enableNotify(g, DATA_UUID)) lastError = "could not subscribe to DATA"
                DATA_UUID -> {
                    connected = status == BluetoothGatt.GATT_SUCCESS
                    state = if (connected) "connected" else "subscribe failed ($status)"
                    if (connected) {
                        lastError = ""
                        connectionId++
                    }
                }
            }
        }

        override fun onCharacteristicChanged(g: BluetoothGatt, ch: BluetoothGattCharacteristic, value: ByteArray) {
            onNotify(ch.uuid, value)   // Android 13+
        }

        @Deprecated("Deprecated in Java")
        override fun onCharacteristicChanged(g: BluetoothGatt, ch: BluetoothGattCharacteristic) {
            if (Build.VERSION.SDK_INT < 33) {
                @Suppress("DEPRECATION")
                onNotify(ch.uuid, ch.value ?: return)   // Android 12 and older
            }
        }
    }

    private fun enableNotify(g: BluetoothGatt, uuid: UUID): Boolean {
        val ch = g.getService(SERVICE_UUID)?.getCharacteristic(uuid) ?: return false
        if (!g.setCharacteristicNotification(ch, true)) return false
        val d = ch.getDescriptor(CCCD_UUID) ?: return false
        return if (Build.VERSION.SDK_INT >= 33) {
            g.writeDescriptor(d, BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE) == BluetoothStatusCodes.SUCCESS
        } else {
            @Suppress("DEPRECATION")
            d.value = BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE
            @Suppress("DEPRECATION")
            g.writeDescriptor(d)
        }
    }

    private fun onNotify(uuid: UUID, value: ByteArray) {
        val tArr = nowSec()
        when (uuid) {
            DATA_UUID -> onData(value, tArr)
            STATUS_UUID -> onStatus(value.toString(Charsets.UTF_8).trim(), tArr)
        }
    }

    private fun onData(data: ByteArray, tArr: Double) {
        val pkt = GlovePacket.decode(data)
        if (pkt == null) {
            nBad++
            if (data.size == 20) lastError = "packets cut to 20 bytes: BLE MTU too small"
            return
        }
        lastSeq?.let { prev ->
            val gap = (pkt.seq - prev - 1) and 0xFFFF
            if (gap < 1000) nDropped += gap
        }
        lastSeq = pkt.seq
        val offset = clock.update(pkt.tDevSec, tArr)
        val s = GloveSample(pkt.tDevSec + offset, pkt.values, tArr, pkt.seq, pkt.flags)
        synchronized(lock) {
            buf.addLast(s)
            while (buf.size > KEEP_SAMPLES) buf.removeFirst()
        }
    }

    private fun onStatus(text: String, tArr: Double) {
        if (text.startsWith("PONG:")) {
            val k = text.substring(5)
            pongTimes[k] = tArr
            pongLatches[k]?.countDown()
            return
        }
        lastStatus = text
        if (text.startsWith("CAL:DONE")) calibration = text
    }

    // ---------------------------------------------------------------- commands
    /** "CAL" = recalibrate, "PING:<id>" = latency probe. True if handed to the BLE stack. */
    fun sendCommand(cmd: String): Boolean {
        val g = gatt ?: return false
        if (!connected) return false
        val ch = g.getService(SERVICE_UUID)?.getCharacteristic(CMD_UUID) ?: return false
        val bytes = cmd.toByteArray(Charsets.UTF_8)
        return if (Build.VERSION.SDK_INT >= 33) {
            g.writeCharacteristic(ch, bytes, BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE) ==
                BluetoothStatusCodes.SUCCESS
        } else {
            ch.writeType = BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE
            @Suppress("DEPRECATION")
            ch.value = bytes
            @Suppress("DEPRECATION")
            g.writeCharacteristic(ch)
        }
    }

    /** Phone -> glove -> phone round trips (blocking; call off the main thread). */
    fun measureRtt(n: Int = 30): Map<String, Any>? {
        val rtts = ArrayList<Double>()
        for (k in 0 until n) {
            val key = "$k-${Random.nextInt(0, 10000)}"
            val latch = CountDownLatch(1)
            pongLatches[key] = latch
            val t0 = nowSec()
            if (sendCommand("PING:$key") && latch.await(1, TimeUnit.SECONDS)) {
                pongTimes[key]?.let { rtts += (it - t0) * 1000 }
            }
            pongLatches.remove(key)
            pongTimes.remove(key)
            Thread.sleep(50)
        }
        if (rtts.isEmpty()) return null
        val r = rtts.toDoubleArray()
        val med = Stats.median(r)
        return linkedMapOf(
            "n" to r.size, "sent" to n,
            "min_ms" to PyFormat.pyRound(r.min(), 1),
            "median_ms" to PyFormat.pyRound(med, 1),
            "p95_ms" to PyFormat.pyRound(Stats.percentile(r, 95.0), 1),
            "max_ms" to PyFormat.pyRound(r.max(), 1),
            "one_way_est_ms" to PyFormat.pyRound(med / 2, 1),
        )
    }

    // ---------------------------------------------------------------- queries
    fun latest(): GloveSample? = synchronized(lock) { buf.lastOrNull() }

    /** Samples with t0 <= t_sync <= t1, in buffer (arrival) order, like the recorder's window(). */
    fun window(t0: Double, t1: Double): List<GloveSample> = synchronized(lock) { buf.filter { it.t in t0..t1 } }

    /** Gap (s) from time t to the closest glove sample: what the take's sync will match. */
    fun nearestGap(t: Double): Double? = synchronized(lock) {
        var best: Double? = null
        for (s in buf) {
            val d = s.t - t
            if (best == null || Math.abs(d) < Math.abs(best)) best = d
        }
        best
    }

    fun recent(spanSec: Double): List<GloveSample> {
        val tMin = nowSec() - spanSec
        return synchronized(lock) { buf.filter { it.t >= tMin } }
    }

    fun rateHz(spanSec: Double = 1.0): Double {
        val tMin = nowSec() - spanSec
        return synchronized(lock) { buf.count { it.tArrival >= tMin } } / spanSec
    }

    companion object {
        const val DEVICE_NAME = "AISL_Glove"
        val SERVICE_UUID: UUID = UUID.fromString("e1273d67-cf0f-4bb7-9477-4f5d92124a6f")
        val DATA_UUID: UUID = UUID.fromString("ecbd02f0-3d5f-4ad5-952a-9e75b163eeab")
        val STATUS_UUID: UUID = UUID.fromString("493ccb74-46cd-4966-8a16-ba3cca3fd116")
        val CMD_UUID: UUID = UUID.fromString("b8b472e5-964d-4b06-ae50-19a91cccb0a2")
        val CCCD_UUID: UUID = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb")
        const val KEEP_SAMPLES = 3000   // 30 s at up to 100 Hz, like the recorder

        /** The host clock, in seconds. Camera frames are put on the same clock. */
        fun nowSec(): Double = SystemClock.elapsedRealtimeNanos() / 1e9
    }
}
