package com.surendramaran.yolov8tflite

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ConsecutiveDetectionFilterTest {
    @Test
    fun forwardsDetectionOnThirdConsecutiveFrame() {
        val filter = ConsecutiveDetectionFilter(requiredFrames = 3)
        val person = box("person")

        assertTrue(filter.filter(listOf(person)).isEmpty())
        assertTrue(filter.filter(listOf(person)).isEmpty())
        assertEquals(listOf(person), filter.filter(listOf(person)))
        assertEquals(listOf(person), filter.filter(listOf(person)))
    }

    @Test
    fun missingFrameResetsClassStreak() {
        val filter = ConsecutiveDetectionFilter(requiredFrames = 3)
        val person = box("person")

        filter.filter(listOf(person))
        filter.filter(listOf(person))
        filter.filter(emptyList())
        assertTrue(filter.filter(listOf(person)).isEmpty())
        assertTrue(filter.filter(listOf(person)).isEmpty())
        assertEquals(listOf(person), filter.filter(listOf(person)))
    }

    @Test
    fun tracksClassesIndependently() {
        val filter = ConsecutiveDetectionFilter(requiredFrames = 3)
        val person = box("person")
        val vehicle = box("vehicle")

        filter.filter(listOf(person))
        filter.filter(listOf(person, vehicle))
        val stable = filter.filter(listOf(person, vehicle))

        assertEquals(listOf(person), stable)
    }

    private fun box(className: String) = BoundingBox(
        x1 = 0f, y1 = 0f, x2 = 1f, y2 = 1f,
        cx = 0.5f, cy = 0.5f, w = 1f, h = 1f,
        cnf = 0.9f, cls = 0, clsName = className,
        topClasses = emptyList()
    )
}
