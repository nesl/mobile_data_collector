package com.surendramaran.yolov8tflite

import android.media.AudioFormat
import android.util.Log
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.google.mediapipe.tasks.audio.core.RunningMode
import com.google.mediapipe.tasks.components.containers.AudioData
import org.junit.Assert.assertNotNull
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder

@RunWith(AndroidJUnit4::class)
class YamnetAudioFileTest {
    @Test
    fun classifyPcmFixtures() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val files = FILES.map { File(context.filesDir, it) } +
            (File(context.filesDir, "yamnet_capture").listFiles { file ->
                file.extension == "f32le"
            }?.sortedBy { it.name } ?: emptyList())
        assumeTrue(
            "Copy converted *.f32le fixtures into the app files directory to run this diagnostic",
            files.any { it.exists() }
        )
        val classifier = AudioClassifierHelper(
            context = context,
            classificationThreshold = 0.0f,
            numOfResults = 521,
            runningMode = RunningMode.AUDIO_CLIPS,
            model_path = "yamnet.tflite"
        )
        val format = AudioFormat.Builder()
            .setEncoding(AudioFormat.ENCODING_PCM_FLOAT)
            .setSampleRate(SAMPLE_RATE)
            .setChannelMask(AudioFormat.CHANNEL_IN_MONO)
            .build()

        files.filter { it.exists() }.forEach { file ->
            val name = file.name
            val samples = readFloatPcm(file)
            val maxima = mutableMapOf<String, Float>()
            var offset = 0
            while (offset < samples.size) {
                val window = FloatArray(WINDOW_SAMPLES)
                val count = minOf(WINDOW_SAMPLES, samples.size - offset)
                samples.copyInto(window, endIndex = offset + count, destinationOffset = 0, startIndex = offset)
                val audioData = AudioData.create(
                    AudioData.AudioDataFormat.create(format),
                    WINDOW_SAMPLES
                )
                audioData.load(window)
                val result = classifier.classifyAudio(audioData)
                assertNotNull("No classification result for $name", result)
                result!!.results.first().classificationResults().forEach { head ->
                    head.classifications().forEach { classification ->
                        classification.categories().forEach { category ->
                            maxima.merge(category.categoryName(), category.score(), ::maxOf)
                        }
                    }
                }
                offset += HOP_SAMPLES
            }

            val top = maxima.entries.sortedByDescending { it.value }.take(12)
                .joinToString { "${it.key}=${"%.4f".format(it.value)}" }
            val gun = maxima.filterKeys { label ->
                val normalized = label.lowercase()
                normalized.contains("gun") || normalized.contains("firearm") ||
                    normalized.contains("artillery") || normalized.contains("fusillade")
            }.entries.sortedByDescending { it.value }
                .joinToString { "${it.key}=${"%.4f".format(it.value)}" }
            Log.i(TAG, "YAMNET_FILE $name TOP: $top")
            Log.i(TAG, "YAMNET_FILE $name GUN: $gun")
        }
        classifier.stopAudioClassification()
    }

    private fun readFloatPcm(file: File): FloatArray {
        require(file.exists()) { "Missing fixture ${file.absolutePath}" }
        val bytes = file.readBytes()
        val floats = FloatArray(bytes.size / Float.SIZE_BYTES)
        ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN).asFloatBuffer().get(floats)
        return floats
    }

    companion object {
        private const val TAG = "YamnetAudioFileTest"
        private const val SAMPLE_RATE = 16_000
        private const val WINDOW_SAMPLES = 15_600
        private const val HOP_SAMPLES = 7_800
        private val FILES = listOf("gun1.f32le", "gun2.f32le", "machine_gun1.f32le", "machine_gun2.f32le")
    }
}
