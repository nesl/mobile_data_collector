# Mobile Data Collector

An Android camera/audio collector and a laptop-side MQTT complex-event detector.
The two components can run together on one local network; MQTT is the only
service between them.

## How the pieces connect

```text
Android phone  -- detection results -->  MQTT broker  -->  detector.py
Android phone  <-- start/stop commands -- MQTT broker  <--  controller.py
```

The laptop can run the broker, detector, and controller. The phone and laptop
must be on the same LAN and the laptop firewall must allow inbound TCP port
1883. Do not expose the development broker to the public internet.

## 1. Run an MQTT broker on the laptop

Install Mosquitto using your operating system's package manager. For a
development-only broker reachable from other LAN devices, create a temporary
configuration outside this repository:

```conf
listener 1883 0.0.0.0
allow_anonymous true
```

Then start it with `mosquitto -c /path/to/mosquitto.conf -v`. Find the laptop's
LAN address (for example `192.168.1.25`); do not use `localhost` or `10.0.2.2`
on a physical phone. `10.0.2.2` is only the Android emulator's alias for its
host computer.

## 2. Build and install the Android collector

Requirements: Android Studio (or Android SDK command-line tools), JDK 17, and
an Android 8.0/API 26 or newer device.

Create `android-app/local.properties` through Android Studio, then build with
the laptop's LAN address:

```bash
cd android-app
./gradlew assembleDebug -PMQTT_HOST=192.168.1.25
./gradlew installDebug -PMQTT_HOST=192.168.1.25
```

The generated APK is under `android-app/app/build/outputs/apk/` and is ignored
by Git. Grant camera and microphone permissions when the app starts. The app
uses unauthenticated, clear-text MQTT for local development; use TLS and broker
authentication before using an untrusted network.

Build properties and defaults are:

```properties
MQTT_HOST=10.0.2.2
MQTT_PORT=1883
MQTT_PUBLISH_TOPIC=ucla/ce_mobile
MQTT_CONTROL_TOPIC=ucla/ce_controller
```

`10.0.2.2` makes the no-argument build suitable for an emulator. Properties can
also be placed in the user-level `~/.gradle/gradle.properties`. Do not commit
credentials or `local.properties`.

## 3. Run the laptop tools

```bash
cd event-detector
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python detector.py --host localhost --first person --second gunshot --within 30
```

In a second activated terminal, start a named recording session:

```bash
cd event-detector
python controller.py start --host localhost --session demo
# Later:
python controller.py stop --host localhost
```

The phone records video locally and publishes bundled camera/audio labels to
`ucla/ce_mobile`. The detector prints labels and reports when the second label
appears within the configured window after the first. Environment equivalents
are listed in `.env.example`; `.env` files are ignored.

## Tests

```bash
cd event-detector
python -m unittest discover -s tests

cd ../android-app
./gradlew test
```

The Python tests do not require a broker. Android builds need dependency access
the first time Gradle runs.

## Repository hygiene

Generated APK/AAB files, Gradle output, Python virtual environments and caches,
IDE state, local SDK paths, `.env` files, and signing keys are ignored. The
Gradle wrapper JAR and TensorFlow Lite files in `app/src/main/assets` are source
inputs and should remain versioned. The repository is about 20 MB, with roughly
19 MB of required model assets, so it is comfortably below GitHub's per-file
and repository-size limits.
