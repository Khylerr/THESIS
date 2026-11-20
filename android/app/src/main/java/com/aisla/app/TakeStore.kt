package com.aisla.app

import android.content.Context
import com.aisla.core.FlexCalibration
import com.aisla.core.GLOVE_COLS
import com.aisla.core.Normalizer
import com.aisla.core.SyncedRow
import com.aisla.core.TakeSchema
import com.aisla.core.TakeSync
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/**
 * Where takes go, named and counted like fslRecorder.py:
 *   <app files>/data/<signer>/<signer>_<sign>_repNN.csv + .json     (raw take, same 143 columns)
 *   <app files>/data_norm/<signer>/<signer>_<sign>_repNN_norm.csv   (Normalizer output)
 * <app files> = Android/data/com.aisla.app/files on the phone (reachable over USB).
 */
class TakeStore(context: Context) {
    val root: File = File(context.getExternalFilesDir(null) ?: context.filesDir, "data")
    val normRoot: File = File(root.parentFile, "data_norm")

    fun slug(text: String) = Regex("[^A-Za-z0-9_-]+").replace(text, "-").trim('-')

    private fun prefix(signer: String, sign: String) = "${signer}_${slug(sign)}_rep"

    fun existingCount(signer: String, sign: String): Int {
        val p = prefix(signer, sign)
        return File(root, signer).listFiles()?.count { it.name.startsWith(p) && it.name.endsWith(".csv") } ?: 0
    }

    fun takeFile(signer: String, sign: String, rep: Int, ext: String) =
        File(File(root, signer), "${prefix(signer, sign)}${"%02d".format(rep)}$ext")

    fun nextRep(signer: String, sign: String): Int {
        var rep = existingCount(signer, sign) + 1
        while (takeFile(signer, sign, rep, ".csv").exists()) rep++
        return rep
    }

    /** Cycle through the signs each round (shuffled), like build_plan(). */
    fun buildPlan(signer: String, signs: List<String>, reps: Int): MutableList<String> {
        val remaining = signs.associateWith { maxOf(0, reps - existingCount(signer, it)) }
        val plan = mutableListOf<String>()
        val rounds = remaining.values.maxOrNull() ?: 0
        for (r in 0 until rounds) plan += signs.filter { remaining.getValue(it) > r }.shuffled()
        return plan
    }

    /** Writes CSV + JSON + normalized CSV. Returns the CSV file. */
    fun save(
        signer: String, sign: String, rep: Int,
        rows: List<SyncedRow>, logOther: Boolean, meta: JSONObject,
        imageWidth: Double, imageHeight: Double, flexCal: FlexCalibration,
    ): File {
        val csv = takeFile(signer, sign, rep, ".csv")
        csv.parentFile?.mkdirs()
        csv.bufferedWriter().use { TakeSync.writeCsv(it, rows, logOther) }
        meta.put("columns", TakeSchema.outputColumns(logOther).size)
        takeFile(signer, sign, rep, ".json").writeText(meta.toString(2))

        val norm = File(File(normRoot, signer), csv.nameWithoutExtension + "_norm.csv")
        norm.parentFile?.mkdirs()
        norm.bufferedWriter().use {
            Normalizer.writeCsv(it, Normalizer.normalizeTake(rows, logOther, imageWidth, imageHeight, flexCal))
        }
        return csv
    }

    companion object {
        /** Kotlin map/list -> org.json (null -> JSON null). */
        fun toJson(v: Any?): Any = when (v) {
            null -> JSONObject.NULL
            is Map<*, *> -> JSONObject().also { o -> v.forEach { (k, x) -> o.put(k.toString(), toJson(x)) } }
            is List<*> -> JSONArray().also { a -> v.forEach { a.put(toJson(it)) } }
            is Double -> if (v.isNaN() || v.isInfinite()) JSONObject.NULL else v
            else -> v
        }

        fun gloveColumnsJson() = JSONArray(GLOVE_COLS)
    }
}
