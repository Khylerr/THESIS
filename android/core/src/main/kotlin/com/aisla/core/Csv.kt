package com.aisla.core

import java.io.File

/** Minimal CSV for the files this project writes (no quoted fields, no commas inside cells). */
object Csv {
    class Table(val header: List<String>, val rows: List<List<String>>) {
        private val col = header.withIndex().associate { it.value to it.index }
        fun index(name: String): Int = col[name] ?: throw IllegalArgumentException("no column $name")
        fun has(name: String) = name in col
    }

    fun read(file: File): Table {
        val lines = file.readLines().filter { it.isNotEmpty() }
        require(lines.isNotEmpty()) { "empty CSV: $file" }
        val header = lines[0].split(',')
        val rows = lines.drop(1).map { line ->
            val cells = line.split(',')
            require(cells.size == header.size) { "$file: row has ${cells.size} cells, header has ${header.size}" }
            cells
        }
        return Table(header, rows)
    }

    /** Numeric table: "" -> NaN. */
    fun readNumbers(file: File): Pair<List<String>, List<DoubleArray>> {
        val t = read(file)
        return Pair(t.header, t.rows.map { r -> DoubleArray(r.size) { PyFormat.parseCell(r[it]) } })
    }
}
