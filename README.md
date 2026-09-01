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

## Quick start (physical phone)

1. On the laptop, find its LAN IP address (for example, `192.168.1.25`). The
   phone and laptop must be connected to the same Wi-Fi/LAN.
2. From the repository root, start the complete laptop-side stack:

   ```bash
   docker compose up --build
   ```

   This starts Mosquitto on port 1883, the device registry, the complex-event
   detector, and the web visualization on port 5000.
3. Open <http://localhost:5000> on the laptop.
4. Install the Android app once using Android Studio, or with USB debugging:

   ```bash
   cd android-app
   ./gradlew installDebug
   ```

5. On the phone, grant camera and microphone permissions. Open **Settings** in
   the app, enter the laptop's LAN IP and port `1883`, and save. Do not enter
   `localhost`: on the phone that means the phone itself.
6. Leave the device ID blank for automatic assignment, or enter a short name.
   Return to the main screen and wait for `mqtt: on`.
7. Press **toggle record**. Camera and audio detections should appear on the
   visualization page. Press the button again to stop.

To confirm the laptop services are healthy and watch detector/registry output:

```bash
docker compose ps
docker compose logs -f detector registry mqtt
```

The default Docker event is `car_gunshot_person`, using `phone-1` for all three
steps. It waits for a car, then a gunshot, then a person. Once completed, the
detector stays completed; restart the detector container to start a fresh
instance:

```bash
docker compose restart detector
```

To select another event or device roles, copy `.env.example` to `.env`, edit
the `CE_*` values, then restart the stack. For a single-phone
`car_gunshot_person` test, set both role IDs to that phone's assigned ID.

## 1. Run an MQTT broker on the laptop

The easiest deployment starts the broker, device registry, visualization, and
detector together:

```bash
docker compose up --build
```

Open <http://localhost:5000>. Set `CE_EVENT`, `CE_OUTSIDE_DEVICE`, and
`CE_BUILDING_DEVICE` in a `.env` file to select another CE or device roles.
Assigned device IDs persist in the `registry-data` volume.

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

Create `android-app/local.properties` through Android Studio, then build and
install:

```bash
cd android-app
./gradlew assembleDebug
./gradlew installDebug
```

The generated APK is under `android-app/app/build/outputs/apk/` and is ignored
by Git. Grant camera and microphone permissions when the app starts. The app
uses unauthenticated, clear-text MQTT for local development; use TLS and broker
authentication before using an untrusted network.

After this one-time USB installation, the cable and `adb reverse` are not
needed. Keep the phone and laptop on the same LAN, start the broker, detector,
and visualization on the laptop, open the app, confirm it shows `mqtt: on`,
then press **toggle record** to begin publishing. Press it again to stop.

Use the app's **settings** button to enter the MQTT server IP/hostname and port.
The values persist across restarts. A blank preferred device ID is assigned by
the registry (`phone-1`, `phone-2`, ...); a requested name is used when it is
available and made unique otherwise.

The host and port entered in **Settings** are saved across app restarts. If
DHCP changes the laptop's address, update it in the app; rebuilding is not
required. `-PMQTT_HOST=192.168.1.25` can still set an optional build-time
default for preconfigured APKs.

Build properties and defaults are:

```properties
MQTT_HOST=
MQTT_PORT=1883
MQTT_PUBLISH_TOPIC=ucla/ce_mobile
MQTT_CONTROL_TOPIC=ucla/ce_controller
```

The no-argument build intentionally leaves the server blank so the user enters
it in Settings. For an emulator, use `10.0.2.2` as the host. Properties can
also be placed in the user-level `~/.gradle/gradle.properties`. Do not commit
credentials or `local.properties`.

## 3. Run the laptop tools

Docker Compose is the recommended path above. To run the Python services
directly instead, first run a Mosquitto broker on port 1883, then create the
project virtual environment once:

```bash
cd event-detector
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

Start the visualization, registry, and detector in three activated terminals:

```bash
python visualization.py
python registry.py
python detector.py --host localhost --event car_gunshot_person \
  --outside-device phone-1 --building-device phone-1
```

Open <http://localhost:5000>. The registry automatically assigns stable phone
IDs and reports them to the visualization. The detector sends status and MQTT
observations to the same page. If the visualization is not running, detection
continues normally. Set `CE_VISUALIZATION_URL` to an empty string or pass
`--visualization-url ''` to disable updates.

### Test without a phone

With Mosquitto, the visualization, and the detector running, publish a complete
test sequence from a third activated terminal:

```bash
python simulate_event.py --event iobt_ce3 \
  --outside-device phone-1 --building-device phone-2
```

The detector should print the observations and a completed `iobt_ce3` event.
The webpage badge should turn green, both devices should appear, the graph
should advance, and the MQTT message count should increase. Use the same event
and device arguments for the detector and simulator.

Complex-event definitions are separate modules under `event-detector/definitions`.
For example, run the car → gunshot → person event with:

```bash
python detector.py --event car_gunshot_person \
  --outside-device phone-1 --building-device phone-2
```

One detector process represents one complex-event instance. After an event
completes it remains completed and does not rearm; restart `detector.py` to
begin a new incomplete instance.

In a second activated terminal, start a named recording session:

```bash
cd event-detector
python controller.py start --host localhost --session demo
# Later:
python controller.py stop --host localhost
```

The phone records video locally and publishes bundled camera/audio labels to
`ucla/ce_mobile`. The detector evaluates the selected complex event using the
timestamps in those bundles. Available events are `car_gunshot_person`,
`gunshot`, `iobt_ce1`, `iobt_ce2`, and `iobt_ce3`. The IoBT events use device
roles instead of fixed node names; the first two currently use YOLO vehicle
classes without the original color requirements. Environment equivalents are
listed in `.env.example`; `.env` files are ignored.

## Tests

```bash
cd event-detector
python -m unittest discover -s tests

cd ../android-app
./gradlew test
```

The Python tests do not require a broker. Android builds need dependency access
the first time Gradle runs.

### Note to self:
https://www.youtube.com/watch?v=zJM7knkHRwc is a good gunshot example, but requires repeated replay, and the speaker type seems to matter.
