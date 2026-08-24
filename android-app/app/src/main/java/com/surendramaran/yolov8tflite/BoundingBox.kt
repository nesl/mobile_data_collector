package com.surendramaran.yolov8tflite
import kotlinx.serialization.Serializable

@Serializable
data class BoundingBox(
    val x1: Float,
    val y1: Float,
    val x2: Float,
    val y2: Float,
    val cx: Float,
    val cy: Float,
    val w: Float,
    val h: Float,
    val cnf: Float,
    val cls: Int,
    val clsName: String,
    val topClasses: List<Pair<String, Float>> // Class name + probability
)

@Serializable
data class DetWrapper(
    val bboxes: List<BoundingBox>,
    val timestamp: Long,
    val dev_id: String
)

@Serializable
data class AudWrapper(
    val events: List<Pair<String, Float>>,
    val timestamp: Long
)