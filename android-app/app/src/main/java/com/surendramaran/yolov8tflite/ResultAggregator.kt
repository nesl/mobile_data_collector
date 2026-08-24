package com.surendramaran.yolov8tflite

import kotlinx.serialization.Serializable


class ResultAggregator(
    private val windowMillis: Long,
    private val listener: BundledResultListener,
    private val dev_id: String
) {
    private val lock = Any()
    private val audioBuffer = mutableListOf<AudWrapper>()
    private val detectionBuffer = mutableListOf<DetWrapper>()
    private var lastFlushTime = System.currentTimeMillis()
    private var curr_dev_id = dev_id

    fun addAudioResult(result: AudWrapper) {
        synchronized(lock) {
            audioBuffer.add(result)
            checkFlush()
        }
    }

    fun addDetectionResult(result: DetWrapper) {
        synchronized(lock) {
            detectionBuffer.add(result)
            checkFlush()
        }
    }

    private fun checkFlush() {
        val currentTime = System.currentTimeMillis()
        if (currentTime - lastFlushTime >= windowMillis) {
            flush()
            lastFlushTime = currentTime
        }
    }

    fun flush() {
        synchronized(lock) {
            if (audioBuffer.isNotEmpty() || detectionBuffer.isNotEmpty()) {
                val bundle = BundledResults(
                    audioResults = audioBuffer.toList(),
                    detectionResults = detectionBuffer.toList(),
                    dev_id = curr_dev_id
                )
                listener.onBundledResult(bundle)
                audioBuffer.clear()
                detectionBuffer.clear()
            }
        }
    }

    @Serializable
    data class BundledResults(
        val audioResults: List<AudWrapper>,
        val detectionResults: List<DetWrapper>,
        val dev_id: String
    )

    interface BundledResultListener {
        fun onBundledResult(results: BundledResults)
    }
}
