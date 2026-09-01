package com.surendramaran.yolov8tflite

/** Only forwards classes that persist across consecutive detector frames. */
class ConsecutiveDetectionFilter(
    private val requiredFrames: Int = 3
) {
    private val streaks = mutableMapOf<String, Int>()

    init {
        require(requiredFrames > 0)
    }

    fun filter(boxes: List<BoundingBox>): List<BoundingBox> {
        val presentClasses = boxes.mapTo(mutableSetOf()) { it.clsName }
        streaks.keys.retainAll(presentClasses)
        presentClasses.forEach { className ->
            streaks[className] = (streaks[className] ?: 0) + 1
        }
        return boxes.filter { (streaks[it.clsName] ?: 0) >= requiredFrames }
    }
}
