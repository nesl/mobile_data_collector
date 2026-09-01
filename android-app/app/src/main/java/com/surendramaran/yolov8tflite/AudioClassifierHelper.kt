package com.surendramaran.yolov8tflite

/*
 * Copyright 2023 The TensorFlow Authors. All Rights Reserved.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *       http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

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
import com.google.mediapipe.tasks.core.Delegate
import java.io.File
import java.io.FileOutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.concurrent.ScheduledThreadPoolExecutor
import java.util.concurrent.TimeUnit

class AudioClassifierHelper(
    val context: Context,
    var classificationThreshold: Float = DISPLAY_THRESHOLD,
    var overlap: Int = DEFAULT_OVERLAP,
    var numOfResults: Int = DEFAULT_NUM_OF_RESULTS,
    var runningMode: RunningMode = RunningMode.AUDIO_CLIPS,
    var listener: ClassifierListener? = null,
    var model_path: String
) {

    private var recorder: AudioRecord? = null
    private var executor: ScheduledThreadPoolExecutor? = null
    private var audioClassifier: AudioClassifier? = null
    private val liveRingBuffer = FloatArray(REQUIRE_INPUT_BUFFER_SIZE)
    private var liveRingWritePosition = 0
    private var liveRingFillCount = 0
    private var captureSequence = 0L
    private val classifyRunnable = Runnable {
        recorder?.let { classifyAudioAsync(it) }
    }

    init {
        initClassifier()
    }

    @SuppressLint("MissingPermission")
    fun initClassifier() {
        // Set general detection options, e.g. number of used threads
        val baseOptionsBuilder = BaseOptions.builder()

        baseOptionsBuilder.setModelAssetPath(model_path)

        try {
            // Configures a set of parameters for the classifier and what results will be returned.
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

            // Create the classifier and required supporting objects
            audioClassifier =
                AudioClassifier.createFromOptions(context, options)
            if (runningMode == RunningMode.AUDIO_STREAM) {

                val minimumBufferSize = AudioRecord.getMinBufferSize(
                    SAMPLING_RATE_IN_HZ,
                    AudioFormat.CHANNEL_IN_MONO,
                    AudioFormat.ENCODING_PCM_FLOAT
                )
                recorder = AudioRecord(
                    MediaRecorder.AudioSource.DEFAULT,
                    SAMPLING_RATE_IN_HZ,
                    AudioFormat.CHANNEL_IN_MONO,
                    AudioFormat.ENCODING_PCM_FLOAT,
                    maxOf(minimumBufferSize, BUFFER_SIZE_IN_BYTES.toInt())
                )

                startAudioClassification()
            }
        } catch (e: IllegalStateException) {
            listener?.onError(
                "Audio Classifier failed to initialize. See error logs for details"
            )

            Log.e(
                TAG, "MP task failed to load with error: " + e.message
            )
        } catch (e: RuntimeException) {
            listener?.onError(
                "Audio Classifier failed to initialize. See error logs for details"
            )

            Log.e(
                TAG, "MP task failed to load with error: " + e.message
            )
        }
    }

    private fun startAudioClassification() {
        if (recorder?.recordingState == AudioRecord.RECORDSTATE_RECORDING) {
            return
        }

        recorder?.startRecording()
        executor = ScheduledThreadPoolExecutor(1)

        executor?.scheduleAtFixedRate(
            classifyRunnable,
            0,
            HOP_MILLISECONDS,
            TimeUnit.MILLISECONDS
        )
    }

    private fun classifyAudioAsync(audioRecord: AudioRecord) {
        val hop = FloatArray(HOP_INPUT_BUFFER_SIZE)
        val readSamples = audioRecord.read(hop, 0, hop.size, AudioRecord.READ_BLOCKING)
        if (readSamples <= 0) {
            Log.w(TAG, "AudioRecord returned $readSamples samples")
            return
        }

        for (index in 0 until readSamples) {
            liveRingBuffer[liveRingWritePosition] = hop[index]
            liveRingWritePosition = (liveRingWritePosition + 1) % liveRingBuffer.size
            if (liveRingFillCount < liveRingBuffer.size) liveRingFillCount++
        }
        if (liveRingFillCount < liveRingBuffer.size) return

        val window = FloatArray(REQUIRE_INPUT_BUFFER_SIZE)
        for (index in window.indices) {
            window[index] = liveRingBuffer[(liveRingWritePosition + index) % liveRingBuffer.size]
        }
        val audioData = AudioData.create(
            AudioDataFormat.create(audioRecord.format),
            REQUIRE_INPUT_BUFFER_SIZE
        )
        audioData.load(window)

        val timestamp = SystemClock.uptimeMillis()
        captureDebugWindow(window, timestamp)
        audioClassifier?.classifyAsync(audioData, timestamp)
    }

    private fun captureDebugWindow(samples: FloatArray, timestamp: Long) {
        if (!BuildConfig.DEBUG) return

        try {
            val captureDirectory = File(context.filesDir, CAPTURE_DIRECTORY).apply { mkdirs() }
            val slot = captureSequence % MAX_CAPTURE_WINDOWS
            val audioFile = File(captureDirectory, "window_%03d.f32le".format(slot))
            val bytes = ByteBuffer.allocate(samples.size * Float.SIZE_BYTES)
                .order(ByteOrder.LITTLE_ENDIAN)
            samples.forEach(bytes::putFloat)
            FileOutputStream(audioFile, false).use { it.write(bytes.array()) }

            val peak = samples.maxOf { kotlin.math.abs(it) }
            val rms = kotlin.math.sqrt(samples.sumOf { (it * it).toDouble() } / samples.size)
            File(captureDirectory, "window_%03d.txt".format(slot)).writeText(
                "sequence=$captureSequence\ntimestamp_ms=$timestamp\npeak=$peak\nrms=$rms\n"
            )
            if (captureSequence == 0L) {
                Log.i(TAG, "Capturing the latest $MAX_CAPTURE_WINDOWS YAMNet windows in ${captureDirectory.absolutePath}")
            }
            captureSequence++
        } catch (error: Exception) {
            Log.e(TAG, "Unable to capture YAMNet input window", error)
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

        // If audioClassifier?.classify() returns null, this is likely an error. Returning null
        // to indicate this.
        listener?.onError("Audio classifier failed to classify.")
        return null
    }

    fun stopAudioClassification() {
        executor?.shutdownNow()
        audioClassifier?.close()
        audioClassifier = null
        recorder?.stop()
    }

    fun isClosed(): Boolean {
        return audioClassifier == null
    }

    private fun streamAudioResultListener(resultListener: AudioClassifierResult) {
        listener?.onAudioResult(
            ResultBundle(listOf(resultListener), 0)
        )
    }

    private fun streamAudioErrorListener(e: RuntimeException) {
        listener?.onError(e.message.toString())
    }

    // Wraps results from inference, the time it takes for inference to be
    // performed.
    data class ResultBundle(
        val results: List<AudioClassifierResult>,
        val inferenceTime: Long,
    )

    companion object {
        private const val TAG = "AudioClassifierHelper"
        const val DISPLAY_THRESHOLD = 0.3f
        const val DEFAULT_NUM_OF_RESULTS = 2
        const val DEFAULT_OVERLAP = 2

        private const val SAMPLING_RATE_IN_HZ = 16000
        private const val BUFFER_SIZE_FACTOR: Int = 2
        const val EXPECTED_INPUT_LENGTH = 0.975F
        private const val REQUIRE_INPUT_BUFFER_SIZE = 15_600
        private const val HOP_INPUT_BUFFER_SIZE = REQUIRE_INPUT_BUFFER_SIZE / 2
        private const val HOP_MILLISECONDS = 488L
        private const val CAPTURE_DIRECTORY = "yamnet_capture"
        private const val MAX_CAPTURE_WINDOWS = 120

        /**
         * Size of the buffer where the audio data is stored by Android
         */
        private const val BUFFER_SIZE_IN_BYTES =
            REQUIRE_INPUT_BUFFER_SIZE * Float.SIZE_BYTES * BUFFER_SIZE_FACTOR
    }

    interface ClassifierListener {
        fun onError(error: String)
        fun onAudioResult(resultBundle: ResultBundle)
    }
}
