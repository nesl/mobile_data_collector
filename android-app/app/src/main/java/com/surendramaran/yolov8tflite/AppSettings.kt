package com.surendramaran.yolov8tflite

import android.content.Context
import java.util.UUID

object AppSettings {
    private const val NAME = "collector_settings"
    private const val HOST = "mqtt_host"
    private const val PORT = "mqtt_port"
    private const val DEVICE_ID = "device_id"
    private const val INSTALL_ID = "install_id"

    private fun prefs(context: Context) = context.getSharedPreferences(NAME, Context.MODE_PRIVATE)
    fun host(context: Context) = prefs(context).getString(HOST, BuildConfig.MQTT_HOST) ?: BuildConfig.MQTT_HOST
    fun port(context: Context) = prefs(context).getString(PORT, BuildConfig.MQTT_PORT) ?: BuildConfig.MQTT_PORT
    fun deviceId(context: Context) = prefs(context).getString(DEVICE_ID, "") ?: ""
    fun installId(context: Context): String {
        val preferences = prefs(context)
        return preferences.getString(INSTALL_ID, null) ?: UUID.randomUUID().toString().also {
            preferences.edit().putString(INSTALL_ID, it).apply()
        }
    }
    fun save(context: Context, host: String, port: String, deviceId: String) {
        prefs(context).edit().putString(HOST, host.trim()).putString(PORT, port.trim())
            .putString(DEVICE_ID, deviceId.trim()).apply()
    }
    fun saveAssignedId(context: Context, deviceId: String) {
        prefs(context).edit().putString(DEVICE_ID, deviceId).apply()
    }
}
