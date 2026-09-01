# Mobile Data Collector

This system detects complex events from camera and microphone observations
produced by Android phones. Each phone runs YOLO and YAMNet locally and publishes
its detection results over MQTT. A laptop-side detector parses and compiles one
YAML complex-event (CE) definition, consumes those observations, and reports CE
progress to a web visualization.

```text
Android phones ── observations ──> MQTT ──> detector process
Android phones <── start/stop ──── MQTT <── controller (optional)
                                      │
                                      └────> visualization
```

Docker runs the long-lived MQTT broker, device registry, and visualization. The
detector is a separate Python process, so each invocation can run a different
CE without rebuilding or restarting the Docker services.

## Repository layout

```text
android-app/             Android camera/audio collector
ce_definitions/          YAML complex-event definitions
event-detector/
  language/              YAML parser and compiler
  runtime/               observation model, FSM, and detector
  services/              device registry and visualization
  tools/                 recording controller and simulator
mosquitto.conf            development MQTT configuration
docker-compose.yml        persistent laptop services
```

## Requirements

- A laptop with Docker Compose and Python 3
- Android 8.0/API 26 or newer phones
- Android Studio or Android SDK tools and JDK 17 if building the APK
- The laptop and phones on the same LAN
- Inbound TCP ports `1883` (MQTT) and `5000` (visualization) allowed by the
  laptop firewall

The included Mosquitto configuration is unauthenticated and unencrypted. It is
intended only for a trusted development LAN and should not be exposed to the
internet.

## One-time setup

### 1. Prepare the detector environment

```bash
cd event-detector
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

### 2. Build and install the Android app

Create `android-app/local.properties` using Android Studio, then build the APK:

```bash
cd android-app
./gradlew assembleDebug
```

The resulting file is normally:

```text
android-app/app/build/outputs/apk/debug/app-debug.apk
```

The APK is a generated, Git-ignored artifact and may not exist in a fresh clone
until it is built. Tagged GitHub versions build it automatically and attach it
as `app-debug.apk` on the project's
[Releases page](https://github.com/nesl/mobile_data_collector/releases). A
manually dispatched **Build Android APK** workflow also provides it as a GitHub
Actions artifact. Install it using either method:

- Copy `app-debug.apk` to the phone using USB, file sharing, or cloud storage;
  open it on the phone and permit installation from that source when prompted.
- Enable USB debugging and install directly from the repository root:

  ```bash
  adb install -r android-app/app/build/outputs/apk/debug/app-debug.apk
  ```

Grant camera and microphone permissions when the app starts. Installation is a
one-time operation unless the app changes.

## Deploy and run a complex event

### 1. Define the CE and its phones

Create a YAML file under `ce_definitions/`. It names the complex event, declares
the logical phone names, defines atomic-event triggers, and describes the CE
sequence and temporal constraints.

See the [CE language guide](event-detector/language/README.md) for the grammar,
trigger fields, `AND`/`OR`, `within`, `holds`, and complete examples.

The names under `devices` are deployment identities. For example, if a CE
declares `outside_phone` and `building_phone`, decide which physical phone will
have each name before placing the phones.

### 2. Configure every phone

Open **Settings** in the Android app and enter:

- **MQTT server:** the laptop's LAN IP, such as `192.168.1.25`
- **MQTT port:** `1883`
- **Device ID:** the exact logical phone name declared in the CE YAML

Do not use `localhost` on a physical phone; it refers to the phone itself. Each
connected phone must use a unique device ID. Return to the main screen and wait
for `mqtt: on`.

### 3. Start the persistent services

From the repository root:

```bash
docker compose up --build
```

This starts MQTT, the device registry, and the visualization. Open
<http://localhost:5000> on the laptop. These services can remain running across
multiple CE runs.

Useful checks are:

```bash
docker compose ps
docker compose logs -f registry mqtt
```

### 4. Start one CE detector

In another terminal:

```bash
cd event-detector
. .venv/bin/activate
python -m runtime.detector ../ce_definitions/iobt_ce3.yaml
```

The detector parses, validates, and compiles the supplied YAML before connecting
to MQTT. A malformed definition or unsupported trigger fails immediately; no
separate definition-check command is required.

One detector process represents one CE instance. After completion, stop it with
Ctrl-C and run the command again—with the same or another YAML file—to start a
fresh instance. The Docker services do not need to be restarted.

### 5. Begin collecting observations

Press **toggle record** on each participating phone. Recording enables the phone
to publish its YOLO and YAMNet observations; the already-running detector uses
them to advance the CE. Press the button again to stop.

Alternatively, start and stop all connected phones from the laptop:

```bash
cd event-detector
python -m tools.controller start --host localhost --session demo
python -m tools.controller stop --host localhost
```

## Test without phones

With the Docker services and a matching detector running, publish a simulated
observation sequence from another activated terminal:

```bash
cd event-detector
python -m tools.simulate_event --event iobt_ce3
```

The detector should print the observations and completed CE, while the web page
shows device observations and FSM progress.

## Configuration notes

The phone settings persist across app restarts. If DHCP changes the laptop's IP,
update the MQTT server setting on every phone. Android build-time defaults are:

```properties
MQTT_HOST=
MQTT_PORT=1883
MQTT_PUBLISH_TOPIC=ucla/ce_mobile
MQTT_CONTROL_TOPIC=ucla/ce_controller
```

For an Android emulator, use `10.0.2.2` to reach the host computer. The detector
also accepts `--host`, `--port`, `--topic`, and `--visualization-url`; run
`python -m runtime.detector --help` for the complete CLI.

## Tests

```bash
cd event-detector
python -m unittest discover -s tests

cd ../android-app
./gradlew test
```

Python tests do not require an MQTT broker. Android builds may require network
access the first time Gradle downloads dependencies.
