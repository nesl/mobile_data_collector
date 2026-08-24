package com.surendramaran.yolov8tflite

import android.annotation.SuppressLint
import android.content.Context
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.SystemClock
import android.util.Log
import com.google.mediapipe.tasks.audio.audioclassifier.AudioClassifier
import com.google.mediapipe.tasks.audio.audioclassifier.AudioClassifierResult
import com.google.mediapipe.tasks.audio.core.RunningMode
import com.google.mediapipe.tasks.components.containers.AudioData
import com.google.mediapipe.tasks.components.containers.AudioData.AudioDataFormat
import com.google.mediapipe.tasks.core.BaseOptions
import java.util.concurrent.ScheduledThreadPoolExecutor
import java.util.concurrent.TimeUnit

class AudioClassifierHelperWithStride(
    val context: Context,
    var classificationThreshold: Float = DISPLAY_THRESHOLD,
    var numOfResults: Int = DEFAULT_NUM_OF_RESULTS,
    var runningMode: RunningMode = RunningMode.AUDIO_CLIPS,
    var listener: ClassifierListener? = null,
    var model_path: String,
    var windowSizeSec: Int = DEFAULT_WINDOW_SIZE_SEC,   // Window size in seconds
    var strideSec: Int = DEFAULT_STRIDE_SEC             // Stride in seconds
) {

    private var recorder: AudioRecord? = null
    private var executor: ScheduledThreadPoolExecutor? = null
    private var audioClassifier: AudioClassifier? = null

    // Ring buffer size based on windowSizeSec
    private var ringBuffer = FloatArray((SAMPLING_RATE_IN_HZ * windowSizeSec).toInt())
    private var bufferWritePos = 0
    private var bufferFillCount = 0

    private var TAG = "yolov8-mqtt-audio"

    private val classifyRunnable = Runnable {
        recorder?.let { classifyAudioAsync(it) }
    }

    init {
        initClassifier()
    }

    @SuppressLint("MissingPermission")
    fun initClassifier() {
        val baseOptionsBuilder = BaseOptions.builder()
        baseOptionsBuilder.setModelAssetPath(model_path)

        Log.d(TAG, "Initializing audio classifier!")

        try {
            val baseOptions = baseOptionsBuilder.build()
            val optionsBuilder =
                AudioClassifier.AudioClassifierOptions.builder()
                    .setScoreThreshold(classificationThreshold)
                    .setMaxResults(numOfResults)
                    .setBaseOptions(baseOptions)
                    .setRunningMode(runningMode)

            if (runningMode == RunningMode.AUDIO_STREAM) {
                optionsBuilder
                    .setResultListener(this::streamAudioResultListener)
                    .setErrorListener(this::streamAudioErrorListener)
            }

            val options = optionsBuilder.build()
            audioClassifier = AudioClassifier.createFromOptions(context, options)

            val supported = AudioRecord.getMinBufferSize(16000, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)

            if (runningMode == RunningMode.AUDIO_STREAM) {
//                recorder = audioClassifier!!.createAudioRecord(
//                    AudioFormat.CHANNEL_IN_DEFAULT,
//                    SAMPLING_RATE_IN_HZ,
//                    BUFFER_SIZE_IN_BYTES.toInt()
//                )
                val minBufferSize = AudioRecord.getMinBufferSize(
                    SAMPLING_RATE_IN_HZ,
                    AudioFormat.CHANNEL_IN_MONO,
                    AudioFormat.ENCODING_PCM_16BIT
                )

                if (minBufferSize == AudioRecord.ERROR_BAD_VALUE) {
                    listener?.onError("Invalid AudioRecord configuration.")
                    return
                }

                recorder = AudioRecord(
                    MediaRecorder.AudioSource.MIC,
                    SAMPLING_RATE_IN_HZ,
                    AudioFormat.CHANNEL_IN_MONO,
                    AudioFormat.ENCODING_PCM_16BIT,
                    minBufferSize
                )

                if (recorder?.state != AudioRecord.STATE_INITIALIZED) {
                    listener?.onError("AudioRecord failed to initialize.")
                    return
                }

                startAudioClassification()
            }
        } catch (e: Exception) {
            listener?.onError("Audio Classifier failed to initialize: ${e.message}")
            Log.e(TAG, "MP task failed to load with error: ${e.message}")
        }
    }

    private fun startAudioClassification() {
        if (recorder?.recordingState == AudioRecord.RECORDSTATE_RECORDING) return

        recorder?.startRecording()
        executor = ScheduledThreadPoolExecutor(1)

        val strideMillis = (strideSec * 1000).toLong()

        Log.d(TAG, "Recorder state = ${recorder?.state}")
        Log.d(TAG, "Recording state = ${recorder?.recordingState}")

        executor?.scheduleWithFixedDelay(
            classifyRunnable,
            0,
            strideMillis,
            TimeUnit.MILLISECONDS
        )
    }

    private fun classifyAudioAsync(audioRecord: AudioRecord) {

        Log.d(TAG, "Classifying right now!")

        val samplesPerStride = (strideSec * SAMPLING_RATE_IN_HZ).toInt()
        val tempBuffer = ShortArray(samplesPerStride)
        val readSamples = audioRecord.read(tempBuffer, 0, tempBuffer.size)

        Log.d(TAG, "readSamples = $readSamples")

        // Convert to float and store in ring buffer
        for (i in 0 until readSamples) {
            ringBuffer[bufferWritePos] = tempBuffer[i] / 32767.0f
            bufferWritePos = (bufferWritePos + 1) % ringBuffer.size
            if (bufferFillCount < ringBuffer.size) bufferFillCount++
        }

        Log.d(TAG, "bufferfillcount = $bufferFillCount")
        Log.d(TAG, "ringbuffer size = ${ringBuffer.size}")

        // Only classify when we have a full window
        if (bufferFillCount == ringBuffer.size) {
            val windowData = FloatArray(ringBuffer.size)
            for (i in windowData.indices) {
                windowData[i] = ringBuffer[(bufferWritePos + i) % ringBuffer.size]
            }

            val audioData = AudioData.create(
                AudioDataFormat.create(recorder!!.getFormat()),
                SAMPLING_RATE_IN_HZ
            )
            audioData.load(windowData)

            Log.d(TAG, "Audio loaded")

            // audioClassifier?.classifyAsync(audioData, SystemClock.uptimeMillis())
            // Perform synchronous classification (blocking call)
            val resultBundle = classifyAudio(audioData)
            if (resultBundle != null) {
                listener?.onAudioResult(resultBundle)
            } else {
                Log.e(TAG, "Failed to classify audio.")
            }
        }
    }

    fun classifyAudio(audioData: AudioData): ResultBundle? {
        val startTime = SystemClock.uptimeMillis()
        audioClassifier?.classify(audioData)
            ?.also { audioClassificationResult ->
                val inferenceTime = SystemClock.uptimeMillis() - startTime
                return ResultBundle(
                    listOf(audioClassificationResult),
                    inferenceTime
                )
            }

        listener?.onError("Audio classifier failed to classify.")
        return null
    }

    fun stopAudioClassification() {
        executor?.shutdownNow()
        audioClassifier?.close()
        audioClassifier = null
        recorder?.stop()
    }

    fun isClosed(): Boolean = audioClassifier == null

    private fun streamAudioResultListener(resultListener: AudioClassifierResult) {
        Log.d(TAG, "Result received with ${resultListener.classificationResults().size} categories")
        listener?.onAudioResult(ResultBundle(listOf(resultListener), 0))
    }

    private fun streamAudioErrorListener(e: RuntimeException) {
        listener?.onError(e.message.toString())
    }

    data class ResultBundle(
        val results: List<AudioClassifierResult>,
        val inferenceTime: Long,
    )

    companion object {
        private const val TAG = "AudioClassifierHelper"
        const val DISPLAY_THRESHOLD = 0.3f
        const val DEFAULT_NUM_OF_RESULTS = 2

        private const val SAMPLING_RATE_IN_HZ = 16000
        private const val BUFFER_SIZE_FACTOR: Int = 2

        // Sliding window defaults
        const val DEFAULT_WINDOW_SIZE_SEC = 3  //
        const val DEFAULT_STRIDE_SEC = 2      //

        private const val BUFFER_SIZE_IN_BYTES =
            SAMPLING_RATE_IN_HZ * Float.SIZE_BYTES * BUFFER_SIZE_FACTOR
    }

    interface ClassifierListener {
        fun onError(error: String)
        fun onAudioResult(resultBundle: ResultBundle)
    }
}
