# Mobile Complex-Event Language

This directory contains the declarative language for describing complex events
recognized from mobile-device detections.

A complex-event definition states:

1. the event name,
2. its logical device roles,
3. the named atomic events that make up the event,
4. the order in which those atomic events must occur, and
5. any temporal constraints between them.

The language does not configure MQTT, choose physical phones, run detection
models, or introduce new detector classes. Those details belong to runtime
configuration and the label capability catalog.

---

## Quick start

A minimal event looks like this:

```yaml
version: 1
complex_event_name: person_then_gunshot

devices:
  OUTSIDE: outside
  BUILDING: building

atomic_events:
  - atomic_event_name: person_seen
    triggers:
      - device: OUTSIDE
        label: person

  - atomic_event_name: gunshot_heard
    triggers:
      - device: BUILDING
        label: gunshot
        confidence: ">= 0.05"

ce_sequence:
  - person_seen
  - gunshot_heard

constraints:
  - within:
      from_atomic_event: person_seen
      to_atomic_event: gunshot_heard
      duration: 2m
```

Run a definition (parsing and compilation happen before MQTT is connected):

```bash
cd event-detector
python -m runtime.detector ../ce_definitions/iobt_ce3.yaml
```

Successful startup begins with output like:

```text
Compiled iobt_ce3 from ../ce_definitions/iobt_ce3.yaml; listening on localhost:1883/ucla/ce_mobile
```

---

## Definitions

### Observation

An **observation** is an instantaneous detection emitted by one physical mobile
device. It describes what that phone's vision or audio model detected at one
timestamp; it is runtime input rather than a named item in the CE YAML.

For example, the detector may normalize one camera result to:

```json
{
  "device": "outside_phone",
  "timestamp": 1788307200.125,
  "modality": "vision",
  "labels": ["person", "car"],
  "scores": [0.93, 0.81],
  "colors": ["blue"]
}
```

All labels in this observation came from `outside_phone` at the same instant.
Another phone or timestamp produces another observation.

### Atomic event

An **atomic event** is a named, short-duration condition recognized from one or
more observations. Its triggers may refer to one device or to multiple devices.
For example, an atomic event can require a person observation from
`outside_phone` **AND** a vehicle observation from `road_phone`. The observations
must satisfy the atomic event within its `window` (two minutes by default), so
an `AND` cannot wait indefinitely.

Atomic events are the smallest named building blocks used in `ce_sequence`.
They are not additional sensor detections and do not introduce new detector
classes.

### Complex event

A **complex event** is the longer-running behavior formed by ordering named
atomic events and applying constraints such as `within` and `holds`. Because its
atomic events may use different device roles, a complex event can describe a
scenario unfolding over time and across multiple phones.

```text
single-device observations
          ↓ satisfy triggers
short atomic events (one or more devices)
          ↓ ordered by ce_sequence and constraints
longer complex event (potentially many devices)
```

---

## YAML punctuation and colons

Colons are YAML punctuation. They are not complex-event operators.

The rule is always:

```text
field_name: field_value
```

Examples:

```yaml
label: vehicle
count: ">= 1"
device: OUTSIDE
logic: AND
```

When the value is a nested object or list, the colon still has exactly the same
meaning:

```yaml
triggers:
  - label: vehicle
  - label: person
```

Here, `triggers:` introduces a field whose value is a list. Each hyphen starts
one item in that list.

Comparison operators belong inside their field values:

```yaml
count: ">= 1"
confidence: ">= 0.5"
color: "== white"
```

Do not combine a field name and comparison into a custom expression such as:

```text
label:vehicle >= 1
```

Quoting comparisons is recommended so YAML treats the whole comparison as a
string for the CE parser.

---

## Language grammar

At a high level, the version 1 grammar is:

```text
ComplexEvent :=
    version
    complex_event_name
    description?
    devices?
    atomic_events
    ce_sequence
    constraints?

Device :=
    DEVICE_ROLE: provisioned_phone_name

AtomicEvent :=
    atomic_event_name
    device?
    logic?               # AND by default
    window?              # 2m by default
    triggers

Trigger :=
    device?
    label
    count?
    confidence?
    color?

Constraint :=
      Holds
    | Within

Holds :=
    holds:
      atomic_event: AtomicEventName
      duration: Duration

Within :=
    within:
      from_atomic_event: AtomicEventName
      to_atomic_event: AtomicEventName
      duration: Duration
```

Fields marked with `?` are optional. Unknown fields are rejected rather than
silently ignored.

Durations must include units:

```text
500ms
4s
2m
1h
```

Bare durations such as `duration: 4` are rejected because their unit would be
ambiguous.

---

## Main concepts

The language and runtime use the following event hierarchy:

```text
Mobile detection payload
    -> Observation                 normalized evidence from one device/time
    -> Trigger                     test applied to observations
    -> AtomicEvent                 named AND/OR group of triggers
    -> ComplexEvent                ordered atomic events plus constraints
```

The corresponding authored and Python names are:

| Concept | YAML | Python |
| --- | --- | --- |
| Normalized device evidence | not authored | `Observation` |
| Evidence test | item under `triggers` | `TriggerDefinition` / `Trigger` |
| Named atomic event | item under `atomic_events` | `AtomicEventDefinition` / `AtomicEvent` |
| Complete complex event | entire document | `ComplexEventDefinition` / `ComplexEventFSM` |

An `Observation` is runtime data, not a YAML atomic event. One bundled MQTT
message may produce several observations because individual vision frames and
audio windows retain their own timestamps.

### Events

Every file defines one complex-event family:

```yaml
version: 1
complex_event_name: iobt_ce3
description: Vehicle arrival, building entry, gunshot, exit, and departure.
```

Complex-event and atomic-event names use lowercase `snake_case`. Language version 1 is
the only currently supported version.

### Logical device roles

Definitions give readable logical roles to the phone names selected before
deployment:

```yaml
devices:
  OUTSIDE: outside_phone
  BUILDING: building_phone
```

Device role names are uppercase. Their values are the exact phone names chosen
before deployment and entered in each phone's Settings screen:

```text
OUTSIDE  -> outside_phone
BUILDING -> building_phone
```

`ANY` is reserved and means that any physical device may satisfy a trigger. It
does not need to be declared under `devices`.

### Atomic events

An atomic event is a named state made from one or more triggers:

```yaml
- atomic_event_name: vehicle_arrives
  triggers:
    - device: OUTSIDE
      label: vehicle
      count: ">= 1"
```

An atomic event is satisfied when its trigger logic is satisfied. A single
trigger is an ordinary atomic event and needs no special operator.

### Triggers

A trigger describes evidence from one device:

```yaml
- device: OUTSIDE
  label: vehicle
  count: ">= 1"
  confidence: ">= 0.5"
```

Only `label` is required. Defaults are:

```text
device: inherited from the atomic event, otherwise ANY
count: >= 1
confidence: unrestricted
color: unrestricted
```

All fields in one trigger apply to the same qualifying detections. For example,
the trigger above counts vehicle detections whose confidence is at least 0.5.
It does not count every vehicle and independently look for any high-confidence
object.

### Modality inference

Definitions do not include a `modality` field. The compiler infers the input
source from `label_capabilities.yaml`:

```text
person, car, truck, vehicle -> vision
gunshot                    -> audio
```

The catalog also maps semantic labels to detector-native labels. For example,
`vehicle` currently includes `car`, `truck`, `bus`, and `motorcycle`, while
`gunshot` recognizes the supported related YAMNet labels.

An unknown semantic label fails compilation before the detector starts.

---

## Comparisons and optional data fields

`count`, `confidence`, and `color` use comparison strings.

### Count

Count accepts a non-negative integer with one of these operators:

```yaml
count: "== 0"
count: "!= 1"
count: ">= 4"
count: "> 1"
count: "<= 2"
count: "< 3"
```

The default is `">= 1"`.

### Confidence

Confidence accepts a number between zero and one:

```yaml
confidence: ">= 0.5"
confidence: "> 0.05"
confidence: "<= 0.9"
```

The comparison is applied to each candidate detection before `count` is
evaluated.

### Color

Color accepts equality or inequality comparisons:

```yaml
color: "== white"
color: "!= red"
```

Color syntax is parsed in version 1, but the current Android collector does not
publish aligned color values. Consequently, the compiler rejects definitions
that require color instead of accepting a condition the runtime cannot evaluate
correctly.

### Expressing absence

There is no separate `absent` operator. Absence uses the same trigger form:

```yaml
- label: vehicle
  count: "== 0"
```

This means that one relevant input sample contains no qualifying vehicles. Use
a `holds` constraint when the absence must persist over time.

---

## AND and OR trigger lists

### Default AND

Every trigger list defaults to `AND`, including lists with multiple triggers:

```yaml
- atomic_event_name: person_and_vehicle
  triggers:
    - device: OUTSIDE
      label: person
    - device: BUILDING
      label: vehicle
```

This is equivalent to writing `logic: AND` explicitly. Triggers may refer to
different devices and different inferred modalities.

The first satisfied trigger starts a join window. Every remaining trigger must
be satisfied within that window. The default is two minutes:

```yaml
- atomic_event_name: coordinated_activity
  logic: AND
  window: 2m
  triggers:
    - device: OUTSIDE
      label: person
    - device: BUILDING
      label: gunshot
```

If the second trigger does not arrive before the window expires, that event
instance fails. A custom duration may be supplied through `window`.

An AND atomic event's completion timestamp is the timestamp at which its final
required trigger becomes satisfied.

### Explicit OR

Use `logic: OR` when any trigger is sufficient:

```yaml
- atomic_event_name: threat_detected
  logic: OR
  triggers:
    - device: BUILDING
      label: gunshot
      confidence: ">= 0.05"
    - device: OUTSIDE
      label: gunshot
      confidence: ">= 0.08"
    - device: BUILDING
      label: person
      count: ">= 2"
```

The atomic event completes when its first qualifying trigger is satisfied. Its
completion timestamp is that trigger's timestamp.

### Atomic event-level device shorthand

When every trigger normally uses the same device, put `device` on the
atomic_event:

```yaml
- atomic_event_name: area_clear
  device: OUTSIDE
  triggers:
    - label: person
      count: "== 0"
    - label: vehicle
      count: "== 0"
```

A trigger-level device overrides the atomic event default. Device resolution is
always:

```text
trigger.device
    else atomic event.device
    else ANY
```

---

## Complex-event sequences

The `ce_sequence` field gives the required atomic-event order:

```yaml
ce_sequence:
  - vehicle_arrives
  - person_outside
  - gunshot
  - area_clear
```

Every declared atomic event must appear exactly once. Unknown, duplicated, and
unused atomic events are rejected. Version 1 intentionally supports a linear
sequence rather than nested patterns or branching graphs.

---

## Temporal constraints

Temporal constraints are separate from triggers and reference complete named
atomic events. They are not nested event patterns.

### HOLDS

`holds` requires an atomic event to remain true for a duration:

```yaml
constraints:
  - holds:
      atomic_event: area_clear
      duration: 4s
```

The timer starts when the complete atomic event becomes true. A relevant
contradictory sample resets the timer. Unrelated traffic from other devices or
modalities does not reset it.

For a multi-trigger AND atomic event, the runtime tracks the current truth of
the individual device triggers. The hold begins only when the complete AND is
true and resets when a required trigger becomes false.

### WITHIN

`within` places a maximum duration between two atomic events:

```yaml
constraints:
  - within:
      from_atomic_event: vehicle_arrives
      to_atomic_event: gunshot
      duration: 2m
```

The timer starts when `vehicle_arrives` completes. `gunshot` must complete no
later than two minutes afterward. Missing the deadline fails the event instance.

`within` uses atomic event completion times rather than inspecting their
individual fields:

- a regular atomic event completes when its trigger matches;
- an AND atomic event completes when its final required trigger matches; and
- an OR atomic event completes when its first trigger matches.

Multiple timing requirements are written as separate constraints:

```yaml
constraints:
  - within:
      from_atomic_event: vehicle_arrives
      to_atomic_event: person_enters
      duration: 30s
  - within:
      from_atomic_event: person_enters
      to_atomic_event: gunshot
      duration: 1m
  - holds:
      atomic_event: area_clear
      duration: 4s
```

The `from_atomic_event` must precede the `to_atomic_event` in `ce_sequence`.

---

## Parsing and compilation

Parsing and compilation answer different questions.

### Parsing

Parsing answers: "Is this valid version 1 CE syntax?"

It checks:

- YAML structure and allowed fields,
- identifiers and device-role names,
- trigger logic,
- comparison syntax and operand types,
- duration syntax,
- CE sequence references, and
- temporal-constraint references.

Errors identify the relevant path, for example:

```text
event.yaml.atomic_events[0].triggers[0].count:
count comparison requires a number
```

### Compilation

Compilation answers: "Can this mobile detector execute the definition?"

It checks:

- semantic labels against `label_capabilities.yaml`,
- optional fields against the data supplied for that label,
- inferred vision or audio sources, and
- logical device roles against the phone names declared in `devices`.

If these checks succeed, the compiler lowers the definition into the existing
`ComplexEventFSM`. YAML definitions therefore use the same event-time runtime,
AND deadline behavior, HOLDS resets, WITHIN failures, and status reporting.

---

## Complete example

The maintained example is `ce_definitions/iobt_ce3.yaml` at the repository root. It uses
regular triggers, atomic event-level device inheritance, a default-AND absence
check, and a HOLDS constraint while preserving the existing `iobt_ce3` event.

The live detector parses and compiles the YAML file passed on its command line.
There is no parallel Python complex-event definition registry or required
preflight command.
