package com.surendramaran.yolov8tflite;

import android.content.Context;

import org.eclipse.paho.client.mqttv3.IMqttActionListener;
import org.eclipse.paho.client.mqttv3.IMqttDeliveryToken;
import org.eclipse.paho.client.mqttv3.IMqttMessageListener;
import org.eclipse.paho.client.mqttv3.IMqttToken;
import org.eclipse.paho.client.mqttv3.MqttClient;
import org.eclipse.paho.client.mqttv3.MqttConnectOptions;
import org.eclipse.paho.client.mqttv3.MqttException;
import org.eclipse.paho.client.mqttv3.MqttMessage;
import org.eclipse.paho.client.mqttv3.persist.MemoryPersistence;

import android.util.Log;
import java.util.HashSet;
import java.util.Set;

/**
 * Created by clemens on 10.05.17.
 */

public class MyMQTTClient{

    protected final String name = "MQTT";
    Context context;
    public static volatile boolean mqtt_connecting=false;
    public static IMqttToken token;

    public static MqttClient mqttAndroidClient;
    public static  MqttConnectOptions mqttConnectOptions;
    public static  String clientId;
    private static long last_mqtt_connection_attempt;
    private static final long RECONNECT_INTERVAL_MS = 5000L;
    private final Set<String> subscriptions = new HashSet<>();

    private static volatile MyMQTTClient INSTANCE = null;

    private final String log_tag = "YOLOv8-MQTT-CLIENT";
    private final String mqtt_publish_topic = BuildConfig.MQTT_PUBLISH_TOPIC;
    public static String port = BuildConfig.MQTT_PORT;
    public static String server = BuildConfig.MQTT_HOST;
    public static String con_str = "tcp://" + server +":" + port;

    // public static method to retrieve the singleton instance
    public static MyMQTTClient getInstance() {
        // Check if the instance is already created
        if(INSTANCE == null) {
            // synchronize the block to ensure only one thread can execute at a time
            synchronized (MyMQTTClient.class) {
                // check again if the instance is already created
                if (INSTANCE == null) {
                    // create the singleton instance
                    INSTANCE = new MyMQTTClient();
                }
            }
        }
        // return the singleton instance
        return INSTANCE;
    }

    private MyMQTTClient() {
        mqtt_connecting = false;
        clientId        = MqttClient.generateClientId();
        mqttConnectOptions = new MqttConnectOptions();
        mqttConnectOptions.setConnectionTimeout(3); //Timeout in seconds
        // Reconnects are serialized below so bundle callbacks cannot race each other.
        mqttConnectOptions.setAutomaticReconnect(false);
        connect_mqtt();
    }

    public synchronized void configure(String newServer, String newPort) {
        String newConnection = "tcp://" + newServer + ":" + newPort;
        if (newConnection.equals(con_str)) return;
        try {
            if (mqttAndroidClient != null && mqttAndroidClient.isConnected()) mqttAndroidClient.disconnect();
            if (mqttAndroidClient != null) mqttAndroidClient.close();
        } catch (MqttException ignored) { }
        server = newServer;
        port = newPort;
        con_str = newConnection;
        mqttAndroidClient = null;
        last_mqtt_connection_attempt = 0;
    }


    public synchronized Boolean connect_mqtt(){

        if (mqttAndroidClient != null && mqttAndroidClient.isConnected()) {
            return true;
        }

        //Already connecting
        if(mqtt_connecting){
            Log.d(log_tag,"MQTT Still connecting...");
            return false;
        }

        //Not long enough since last connection
        // if(System.currentTimeMillis()-last_mqtt_connection_attempt<60*1000L) return false;

        mqtt_connecting=true;
        last_mqtt_connection_attempt=System.currentTimeMillis();

        try {


            Log.d(log_tag, "Building client " + con_str);
            Log.d(log_tag,"Attempting to connect");

            if (mqttAndroidClient == null) {
                mqttAndroidClient = new MqttClient(con_str, clientId,new MemoryPersistence());
            }

            mqttAndroidClient.connect(mqttConnectOptions);
            mqtt_connecting=false;
            if(mqttAndroidClient.isConnected()){
                // Toast.makeText(GpsMainActivity.gpsAppContext,"MQTT connected",Toast.LENGTH_SHORT).show();
                Log.d(log_tag, "MQTT Connected!");
                for (String topic : subscriptions) {
                    mqttAndroidClient.subscribe(topic, 1);
                }
                return true;
            }
            // mqttAndroidClient.setTimeToWait(10);
//            else{
//                Toast.makeText(GpsMainActivity.gpsAppContext,"MQTT not connected. Check settings.",Toast.LENGTH_SHORT).show();
//            }
        } catch (MqttException e) {
            mqtt_connecting=false;
            //e.printStackTrace();
            // Toast.makeText(GpsMainActivity.gpsAppContext,"MQTT Connection failed.",Toast.LENGTH_SHORT).show();
            Log.d(log_tag, "Failed to connect...");
        }
        last_mqtt_connection_attempt=System.currentTimeMillis();
        return false;
    }

    public void subscribe(String topic) {
        synchronized (this) {
            subscriptions.add(topic);
        }
        try {
            if (mqttAndroidClient != null && mqttAndroidClient.isConnected()) {
                mqttAndroidClient.subscribe(topic, 1);
            } else {
                Log.w(log_tag, "Cannot subscribe while MQTT is disconnected");
            }
        } catch (MqttException e) {
            e.printStackTrace();
        }
    }

    void publish(String msg){
        publish(mqtt_publish_topic, msg);
    }

    void publish(String topic, String msg){
        //Try re-connect if needed
        if( mqttAndroidClient ==null || !mqttAndroidClient.isConnected()){
            if(System.currentTimeMillis()-last_mqtt_connection_attempt>=RECONNECT_INTERVAL_MS) {
                Log.d(log_tag, "Retrying connection for publish");
                connect_mqtt();
            }
        }

        //Send message if able
        if( mqttAndroidClient !=null && mqttAndroidClient.isConnected()){

            Thread thread = new Thread() {
                public void run() {
                    try {

                        // Send in a new thread:
                        mqttAndroidClient.publish(topic, msg.getBytes(), 0, false);
                    } catch (MqttException e) {
                        Log.d(log_tag, "Error!");
                        Log.d(log_tag, e.toString());
                        e.printStackTrace();
                    }
                    // Log.d(log_tag, "SENT on MQTT: " + msg);
                }
            };
            thread.start();
        }
    }


}
