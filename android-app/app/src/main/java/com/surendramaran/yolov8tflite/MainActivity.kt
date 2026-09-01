package com.surendramaran.yolov8tflite

import android.Manifest
import android.R
import android.annotation.SuppressLint
import android.content.ContentValues
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.Matrix
import android.os.Bundle
import android.provider.MediaStore
import android.util.Log
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.camera.core.AspectRatio
import androidx.camera.core.Camera
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.video.MediaStoreOutputOptions
import androidx.camera.video.Quality
import androidx.camera.video.QualitySelector
import androidx.camera.video.Recorder
import androidx.camera.video.Recording
import androidx.camera.video.VideoCapture
import androidx.camera.video.VideoRecordEvent
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import com.surendramaran.yolov8tflite.Constants.LABELS_PATH
import com.surendramaran.yolov8tflite.Constants.MODEL_PATH
import com.surendramaran.yolov8tflite.databinding.ActivityMainBinding
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledExecutorService
import java.util.concurrent.TimeUnit

// Imports for audio classifier
import com.google.mediapipe.tasks.audio.core.RunningMode
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import org.eclipse.paho.client.mqttv3.IMqttDeliveryToken
import org.eclipse.paho.client.mqttv3.MqttCallback
import org.eclipse.paho.client.mqttv3.MqttMessage


class MainActivity : AppCompatActivity(), ResultAggregator.BundledResultListener , Detector.DetectorListener, AudioClassifierHelper.ClassifierListener {
    private lateinit var binding: ActivityMainBinding
    private val isFrontCamera = true

    private var preview: Preview? = null
    private var imageAnalyzer: ImageAnalysis? = null
    private var camera: Camera? = null
    private var cameraProvider: ProcessCameraProvider? = null
    private var detector: Detector? = null
    private lateinit var audioClassifierHelper: AudioClassifierHelper
    private var sent_cam_data_flag: Boolean? = false
    private var record_data: Boolean? = false

    private lateinit var cameraExecutor: ExecutorService

    private val log_tag = "YOLOv8-MQTT-MAIN"
    private val mqtt_recv_topic = BuildConfig.MQTT_CONTROL_TOPIC
    private var controller_ts = 0L
    private var local_start_ts = 0L

    // Bundle parameters
    private val bundle_size = 3 // every X seconds, package up all data
    private val stride_sec = 2 // Audio will detect is in sliding windows of bundle_size seconds and every stride_sec

    // Adding video capture
    private lateinit var videoCapture: VideoCapture<Recorder>
    private lateinit var currRecording: Recording
    private var isRecording = false
    private var recordingSessionName = ""
    private var rectask: java.util.concurrent.ScheduledFuture<*>? = null
    private lateinit var recexecutor: ScheduledExecutorService

    // Bundling service
    private lateinit var aggregator: ResultAggregator
    private val detectionFilter = ConsecutiveDetectionFilter(YOLO_REQUIRED_FRAMES)

    //MQTT client
    var mymqttclient: MyMQTTClient? = null
    private val settingsLauncher = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) {
        if (it.resultCode == RESULT_OK) connectMqtt()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        cameraExecutor = Executors.newSingleThreadExecutor()
        cameraExecutor.execute {
            detector = Detector(baseContext, MODEL_PATH, LABELS_PATH, this)
        }

        // Set up result bundling
        val initialDeviceId = AppSettings.deviceId(this).ifBlank { "phone-${AppSettings.installId(this).take(8)}" }
        binding.idText.setText(initialDeviceId)
        aggregator = ResultAggregator(3000, this, initialDeviceId)

        // Also set up the audio classifier
        audioClassifierHelper = AudioClassifierHelper(
            context = this,
            // Keep low-ranked per-window candidates; the CE detector applies
            // its own gunshot threshold across the stream of overlapping windows.
            classificationThreshold = 0.01f,
            overlap = 2,
            numOfResults = 25,
            runningMode = RunningMode.AUDIO_STREAM,  // or AUDIO_CLIPS
            listener = this,  // implements ClassifierListener
            model_path = "yamnet.tflite", // your model file name (must be in assets)
        )
//        audioClassifierHelper = AudioClassifierHelper(
//            context = this,
//            classificationThreshold = 0.3f,
//            numOfResults = 10,
//            runningMode = RunningMode.AUDIO_STREAM,  // or AUDIO_CLIPS
//            listener = this,  // implements ClassifierListener
//            model_path = "yamnet.tflite", // your model file name (must be in assets)
//            windowSizeSec = bundle_size,
//            strideSec = stride_sec
//        )

        if (allPermissionsGranted()) {
            startCamera()
        } else {
            ActivityCompat.requestPermissions(this, REQUIRED_PERMISSIONS, REQUEST_CODE_PERMISSIONS)
        }

        // bindListeners()
        // Start the MQTT
        Log.d(log_tag, "Starting MQTT client")


        connectMqtt()

        binding.settingsButton.setOnClickListener {
            settingsLauncher.launch(Intent(this, SettingsActivity::class.java))
        }

        binding.sendbutton.setOnClickListener {
            val chosenId = binding.idText.text.toString().trim()
            if (chosenId.isNotEmpty() && chosenId != AppSettings.deviceId(this)) {
                AppSettings.save(this, AppSettings.host(this), AppSettings.port(this), chosenId)
                aggregator.setDeviceId(chosenId)
                registerDevice()
            }
            if(!record_data!!) {
                record_data = true
                startWindowedRecording()
            }
            else {
                stopRecording()
                record_data = false
                rectask?.cancel(false)
                if (::recexecutor.isInitialized) recexecutor.shutdown()
            }
        }
    }

    private fun connectMqtt() {
        val client = MyMQTTClient.getInstance()
        mymqttclient = client
        client.configure(AppSettings.host(this), AppSettings.port(this))
        val connected = client.connect_mqtt()
        binding.mqttStatus.text = if (connected) "mqtt: on" else "mqtt: off"
        val responseTopic = "ucla/ce_registry/response/${AppSettings.installId(this)}"
        client.subscribe(mqtt_recv_topic)
        client.subscribe(responseTopic)
        MyMQTTClient.mqttAndroidClient?.setCallback(object : MqttCallback {
            override fun connectionLost(cause: Throwable) {
                Log.d(log_tag, "Connection lost...")
                binding.mqttStatus.text = "mqtt: off"
                //Attempt reconnect
                mymqttclient?.connect_mqtt()
            }

            @Throws(java.lang.Exception::class)
            override fun messageArrived(topic: String, message: MqttMessage) {
                val payload = String(message.payload)
                Log.d(log_tag, "Received message: $payload")
                if (topic == responseTopic) {
                    val assignedId = Json.parseToJsonElement(payload).jsonObject["device_id"]?.jsonPrimitive?.content
                    if (!assignedId.isNullOrBlank()) {
                        AppSettings.saveAssignedId(this@MainActivity, assignedId)
                        aggregator.setDeviceId(assignedId)
                        runOnUiThread { binding.idText.setText(assignedId) }
                    }
                } else if (payload.contains("handshake")) {

                    // Get controller and local timestamp
                    controller_ts = payload.split(":")[1].toLong()
                    local_start_ts = System.currentTimeMillis()
                    recordingSessionName = payload.split(":")[2]

                    // Complete the handshake
                    val nodeDataJson = buildJsonObject {
                        put("node_id", binding.idText.text.toString())
                    }
                    mymqttclient?.publish("handshake::"+Json.encodeToString(nodeDataJson))

                } else if (payload == "start_record") {

                    Log.d(log_tag, "Received start recording signal")
                    record_data = true
                    startWindowedRecording()

                } else if (payload == "end_record") {
                    Log.d(log_tag, "Received End recording signal")
                    stopRecording()
                    record_data = false
                    rectask?.cancel(false)
                    if (::recexecutor.isInitialized) recexecutor.shutdown()
                }

            }

            override fun deliveryComplete(token: IMqttDeliveryToken) {
            }

        })
        if (connected) registerDevice()
    }

    private fun registerDevice() {
        val request = buildJsonObject {
            put("install_id", AppSettings.installId(this@MainActivity))
            put("preferred_id", AppSettings.deviceId(this@MainActivity))
        }
        mymqttclient?.publish("ucla/ce_registry/request", request.toString())
    }

//    private fun bindListeners() {
//        binding.apply {
//            isGpu.setOnCheckedChangeListener { buttonView, isChecked ->
//                cameraExecutor.submit {
//                    detector?.restart(isGpu = isChecked)
//                }
//                if (isChecked) {
//                    buttonView.setBackgroundColor(ContextCompat.getColor(baseContext, R.color.holo_orange_dark))
//                } else {
//                    buttonView.setBackgroundColor(ContextCompat.getColor(baseContext, R.color.darker_gray))
//                }
//            }
//        }

//    }

    private fun startCamera() {
        val cameraProviderFuture = ProcessCameraProvider.getInstance(this)
        cameraProviderFuture.addListener({
            cameraProvider  = cameraProviderFuture.get()
            bindCameraUseCases()
        }, ContextCompat.getMainExecutor(this))
    }

    private fun setupVideoCapture() {
        val recorder = Recorder.Builder()
            .setQualitySelector(QualitySelector.from(Quality.HD)) // Set desired quality
            .build()

        videoCapture = VideoCapture.withOutput(recorder)
    }

    private fun bindCameraUseCases() {
        val cameraProvider = cameraProvider ?: throw IllegalStateException("Camera initialization failed.")

        // val rotation = binding.viewFinder.display.rotation

        val cameraSelector = CameraSelector
            .Builder()
            .requireLensFacing(CameraSelector.LENS_FACING_FRONT) //Change to LENS_FACING_BACK for the back camera
            .build()

//        preview =  Preview.Builder()
//            .setTargetAspectRatio(AspectRatio.RATIO_4_3)
//            .setTargetRotation(rotation)
//            .build()
        preview =  Preview.Builder()
            .setTargetAspectRatio(AspectRatio.RATIO_4_3)
            .build()

//        imageAnalyzer = ImageAnalysis.Builder()
//            .setTargetAspectRatio(AspectRatio.RATIO_4_3)
//            .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
//            .setTargetRotation(binding.viewFinder.display.rotation)
//            .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_RGBA_8888)
//            .build()
        imageAnalyzer = ImageAnalysis.Builder()
            .setTargetAspectRatio(AspectRatio.RATIO_4_3)
            .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
            .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_RGBA_8888)
            .build()

        imageAnalyzer?.setAnalyzer(cameraExecutor) { imageProxy ->
            val bitmapBuffer =
                Bitmap.createBitmap(
                    imageProxy.width,
                    imageProxy.height,
                    Bitmap.Config.ARGB_8888
                )
            imageProxy.use { bitmapBuffer.copyPixelsFromBuffer(imageProxy.planes[0].buffer) }
            imageProxy.close()

            val matrix = Matrix().apply {
                postRotate(imageProxy.imageInfo.rotationDegrees.toFloat())

                if (isFrontCamera) {
                    postScale(
                        -1f,
                        1f,
                        imageProxy.width.toFloat(),
                        imageProxy.height.toFloat()
                    )
                }
            }

            val rotatedBitmap = Bitmap.createBitmap(
                bitmapBuffer, 0, 0, bitmapBuffer.width, bitmapBuffer.height,
                matrix, true
            )


            // Start our detection
            detector?.detect(rotatedBitmap)
        }

        cameraProvider.unbindAll()

        // Add video capture
        setupVideoCapture()

        try {
            camera = cameraProvider.bindToLifecycle(
                this,
                cameraSelector,
                preview,
                imageAnalyzer,
                videoCapture
            )

            preview?.setSurfaceProvider(binding.viewFinder.surfaceProvider)
        } catch(exc: Exception) {
            Log.e(TAG, "Use case binding failed", exc)
        }
    }

    private fun allPermissionsGranted() = REQUIRED_PERMISSIONS.all {
        ContextCompat.checkSelfPermission(baseContext, it) == PackageManager.PERMISSION_GRANTED
    }

    private val requestPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()) {
        if (it[Manifest.permission.CAMERA] == true && it[Manifest.permission.RECORD_AUDIO] == true) { startCamera() }
    }

    override fun onDestroy() {
        super.onDestroy()
        detector?.close()
        cameraExecutor.shutdown()
        audioClassifierHelper.stopAudioClassification()
    }

    override fun onResume() {
        super.onResume()
        if (allPermissionsGranted()){
            startCamera()
        } else {
            requestPermissionLauncher.launch(REQUIRED_PERMISSIONS)
        }
    }

    // FUnction from ResultAggregator when the bundle is completed for this time
    override fun onBundledResult(results: ResultAggregator.BundledResults) {
        Log.d(log_tag, "Bundled results: $results")
        // Handle combined results here

        // Convert to json string
        val out_message = Json.encodeToString(results)

        // Publish the data to MQTT
        if (record_data == true) {
            mymqttclient?.publish("detection::"+out_message)
        }
    }

    companion object {
        private const val TAG = "Camera"
        private const val REQUEST_CODE_PERMISSIONS = 10
        private const val YOLO_REQUIRED_FRAMES = 3
        private val REQUIRED_PERMISSIONS = mutableListOf (
            Manifest.permission.CAMERA,
            Manifest.permission.RECORD_AUDIO
        ).toTypedArray()
    }

    override fun onEmptyDetect() {
        runOnUiThread {
            binding.overlay.clear()
            detectionFilter.filter(emptyList())
            // Distinguish an empty frame from a disconnected or silent phone.
            aggregator.addDetectionResult(create_outmessage(emptyList()))
        }
    }

    override fun onDetect(boundingBoxes: List<BoundingBox>, inferenceTime: Long) {
        runOnUiThread {
            binding.inferenceTime.text = "${inferenceTime}ms"
            binding.overlay.apply {
                setResults(boundingBoxes)
                invalidate()
                // Also send the messages over mqtt, if we are recording...
//                if (record_data == true) {
//                    mymqttclient?.publish("detection::"+create_outmessage(boundingBoxes))
//                }

                val stableBoundingBoxes = detectionFilter.filter(boundingBoxes)
                val data_message = create_outmessage(stableBoundingBoxes)
                // Save to bundle
                aggregator.addDetectionResult(data_message)

            }
        }
    }

    // Audio classifier member functions
    override fun onError(error: String) {
        Log.e(log_tag, "Audio Classifier Error: $error")
    }

    override fun onAudioResult(resultBundle: AudioClassifierHelper.ResultBundle) {
        val topK = 3
        val iterator = resultBundle.results.listIterator()
        while (iterator.hasNext()) {
            val result = iterator.next()
            val ts = result.timestampMs()
            val info = result.classificationResults().get(0).classifications()

            var time_diff = System.currentTimeMillis() - local_start_ts
            var controller_ts = controller_ts + time_diff

            // For each classification item, just get the class and probability
            val resultsList = mutableListOf<Pair<String, Float>>()
            for (classification in info) {
                for (category in classification.categories()) {
                    val label = category.categoryName()     // or .label depending on your version
                    val score = category.score()
                    resultsList.add(label to score)
                }
            }
            val outMessage = AudWrapper(
                events = resultsList,
                timestamp = controller_ts
            )

//            val outMessage = DetWrapper(
//                bboxes = bboxes,
//                timestamp = controller_ts,
//                dev_id = binding.idText.text.toString()
//            )
            // Convert to message
            // val jsonString = Json.encodeToString(outMessage)

            aggregator.addAudioResult(outMessage)
        }
    }
    // Start/stop recording
    @SuppressLint("MissingPermission")
    private fun startNewRecording() {
        if (!record_data!!) return
        Log.d(log_tag, "Starting new recording...")
        // If we are already recording, ignore
        if (isRecording) return


        // Update our button
        binding.textView.text = "rec active"

        // Get the current ts in controller time
        var time_diff = System.currentTimeMillis() - local_start_ts
        var controller_ts = controller_ts + time_diff

        val name = "recording_"+recordingSessionName+"_"+ controller_ts.toString() + ".mp4"
        val contentValues = ContentValues().apply {
            put(MediaStore.Video.Media.DISPLAY_NAME, name)
        }

//        // Stop the current recording, if any
//        if(::currRecording.isInitialized) {
//            Log.d(log_tag, "Stopping current recording")
//            stopRecording()
//        }

        val mediaStoreOutput = MediaStoreOutputOptions.Builder(this.contentResolver,
            MediaStore.Video.Media.EXTERNAL_CONTENT_URI)
            .setContentValues(contentValues)
            .build()



        currRecording = videoCapture.output
            .prepareRecording(this, mediaStoreOutput)
            .withAudioEnabled()
            .start(ContextCompat.getMainExecutor(this)) { recordEvent ->
                when (recordEvent) {
                    is VideoRecordEvent.Start -> {
                        Log.d(log_tag, "Video recording started!")
                        isRecording = true
                    }
                    is VideoRecordEvent.Finalize -> {
                        isRecording = false
                        if (recordEvent.hasError()) {
                            Log.d(log_tag, "Video recording error!")
                        }
                    }
                }
            }
    }

    // Function for generating windows of recordings
    private fun startWindowedRecording() {
        if (rectask?.isDone == false) return

        // Initialize the ScheduledExecutorService
        recexecutor = Executors.newSingleThreadScheduledExecutor()

        // Schedule the task
        rectask = recexecutor.scheduleAtFixedRate({
            runOnUiThread {  // Has to touch views, must run on UI thread
                Log.d(log_tag, "Scheduled task executed")
                // Stop the current recording
                stopRecording()
                // Start up the next recording (it will handle stopping the old one)
                startNewRecording()
            }
        }, 0, 300, TimeUnit.SECONDS)  // Executes every X seconds
    }

    private fun stopRecording() {
        if (!record_data!!) return

        binding.textView.text = "rec inactive"
        if (!isRecording) return
        // Log.d(log_tag, "Stop recording - already not recording...")
        currRecording.stop()
        isRecording = false
        Log.d(log_tag, "Stopped current recording")
    }

    // Create a stringified version of our message
    private fun create_outmessage(bboxes: List<BoundingBox>): DetWrapper {

        // Get ts
        var time_diff = System.currentTimeMillis() - local_start_ts
        var controller_ts = controller_ts + time_diff

        val outMessage = DetWrapper(
            bboxes = bboxes,
            timestamp = controller_ts,
            dev_id = binding.idText.text.toString()
        )
        // Convert to message
        // val jsonString = Json.encodeToString(outMessage)


        return outMessage
    }
}
