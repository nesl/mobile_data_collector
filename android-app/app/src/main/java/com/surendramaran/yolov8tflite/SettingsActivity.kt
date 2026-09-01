package com.surendramaran.yolov8tflite

import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import com.surendramaran.yolov8tflite.databinding.ActivitySettingsBinding

class SettingsActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val binding = ActivitySettingsBinding.inflate(layoutInflater)
        setContentView(binding.root)
        binding.mqttHost.setText(AppSettings.host(this))
        binding.mqttPort.setText(AppSettings.port(this))
        binding.deviceId.setText(AppSettings.deviceId(this))
        binding.installId.text = "Installation: ${AppSettings.installId(this)}"
        binding.saveSettings.setOnClickListener {
            if (binding.mqttHost.text.isNullOrBlank()) {
                binding.mqttHost.error = "Server address is required"
                return@setOnClickListener
            }
            AppSettings.save(this, binding.mqttHost.text.toString(), binding.mqttPort.text.toString().ifBlank { "1883" }, binding.deviceId.text.toString())
            setResult(RESULT_OK)
            finish()
        }
    }
}
