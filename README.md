# OVMS Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/majorfrog/ovms-hass.svg)](https://github.com/majorfrog/ovms-hass/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A complete Home Assistant integration for [OVMS](https://www.openvehicles.com) (Open Vehicles Monitoring System) written in Python.

## Overview

This integration provides seamless Home Assistant support for OVMS-equipped vehicles by communicating with the OVMS Server using:

- **REST API** (HTTP/HTTPS on ports 6868/6869) - for data retrieval
- **Binary Protocol v2** (TCP on ports 6867/6870) - for real-time vehicle commands

## Features

### Vehicle Monitoring

- **Real-time Status** - Battery SOC, range, temperatures, door status, speed
- **Charging Information** - Current charging state, power, estimated time remaining
- **Location Tracking** - GPS coordinates, altitude, driving mode
- **Tire Pressure (TPMS)** - Individual tire pressures and temperatures
- **Connection Status** - Monitor OVMS module connectivity

### Vehicle Control

- **AC On** - Turn on AC via button (use `send_command` service to turn off)
- **Charging** - Set the charge current limit; read the charge limits
- **Door Locks** - Lock/unlock vehicle doors (Lock entity)
- **Cooldown** - Activate battery/cabin cooling (Switch entity)
- **Vehicle Wake** - Wake vehicle from sleep mode
- **HomeLink** - Activate garage door openers
- **Module Reset** - Restart OVMS module remotely

### Home Assistant Entities

#### Core Entities

| Entity Type      | Count | Examples                                                                                                        |
| ---------------- | ----- | --------------------------------------------------------------------------------------------------------------- |
| `lock`           | 1     | Door Locks (lock/unlock)                                                                                        |
| `device_tracker` | 1     | GPS Location with accuracy (SOC has its own sensor)                                                             |
| `switch`         | 2     | Cooldown, Valet Mode                                                                                            |
| `number`         | 1     | Charge Current (limit, A)                                                                                       |
| `binary_sensor`  | 14    | Doors, Bonnet, Trunk, Charge Port, Parking Brake, Pilot Present, Car On, Headlights, Alarm, GPS Lock, CAN Write |
| `sensor`         | 50+   | Battery, Charging, Temperature, Power, Location, Diagnostics                                                    |
| `button`         | 8     | Refresh, Wake Up, AC On, HomeLink 1-3, Module Reset, TPMS Reset                                                 |

#### Binary Sensors (14 total)

| Binary Sensor         | Default State | Purpose                       |
| --------------------- | ------------- | ----------------------------- |
| Front Left/Right Door | Enabled       | Security monitoring           |
| Rear Left/Right Door  | Disabled      | Less common usage             |
| Bonnet/Hood           | Enabled       | Security monitoring           |
| Trunk                 | Enabled       | Security monitoring           |
| Charge Port           | Enabled       | Charging workflows            |
| Parking Brake         | Disabled      | Technical monitoring          |
| Pilot Present         | Enabled       | Charger plugged in status     |
| Car On/Started        | Enabled       | Vehicle state for automations |
| Headlights            | Disabled      | Less common monitoring        |
| Alarm Sounding        | Enabled       | Security alert                |
| GPS Lock              | Disabled      | Technical diagnostics         |
| CAN Write Active      | Disabled      | Technical diagnostics         |

#### Sensors (50+ total)

**Battery & Range** (enabled by default):

- State of Charge (SOC), State of Health (SOH)
- Estimated Range, Battery Capacity (kWh)
- Battery Voltage, 12V Battery Voltage & Current
- CAC (Calculated Amp Capacity) - disabled

**Temperature** (enabled by default):

- Ambient, Cabin, Battery, Motor
- PEM Temperature - disabled (technical)
- Charger Temperature - disabled (technical)

**Charging** (enabled by default):

- Charging State, Power, Current
- Charger Power Input, Charge Type
- Time to Full, Charge Session Energy (kWh)
- Charge Limit SOC, Charge Limit Range - disabled
- Grid kWh (session & total) - disabled (technical)
- Charger Efficiency - disabled (technical)

**Driving & Power** (enabled by default):

- Odometer, Speed, Trip Meter
- Power (instantaneous), Energy Used/Recovered
- Drive Mode - disabled
- Inverter Power & Efficiency - disabled (technical)

**Location** (enabled by default):

- Latitude, Longitude, Altitude, Direction

**Connectivity & Diagnostics**:

- Last Seen, GSM Signal, WiFi Signal, Connection Status
- Firmware Version - disabled (diagnostic)
- Hardware Version - disabled (diagnostic)
- Modem Mode - disabled (diagnostic)
- Service Range/Time - disabled (diagnostic)

#### Buttons

- **Refresh Data** - Force immediate data update
- **Wake Up** - Wake sleeping vehicle
- **AC On** - Send AC ON command to vehicle (Command 26,1)
- **HomeLink 1-3** - Activate garage door openers
- **Module Reset** - Restart OVMS module
- **TPMS Reset** - Auto-learn tire pressure sensors (disabled by default)

#### Services

Seven advanced services for vehicle control:

- `ovms_hass.send_command` - Send generic OVMS commands
- `ovms_hass.send_sms` - Send SMS via vehicle modem
- `ovms_hass.set_charge_timer` - Configure charging schedule
- `ovms_hass.wakeup_subsystem` - Wake specific vehicle subsystem
- `ovms_hass.tpms_map_wheel` - Map TPMS sensor to wheel position
- `ovms_hass.set_feature` - Set a module feature (0-15), e.g. the GPS streaming interval
- `ovms_hass.set_parameter` - Set a module parameter (0-31)

## Installation

### HACS (Recommended)

1. Open HACS in your Home Assistant
2. Click on "Integrations"
3. Click the three dots menu in the top right
4. Select "Custom repositories"
5. Add `https://github.com/majorfrog/ovms-hass` with category "Integration"
6. Click "Add"
7. Search for "OVMS" and install it
8. Restart Home Assistant

### Manual Installation

1. Download the latest release from [GitHub Releases](https://github.com/majorfrog/ovms-hass/releases)
2. Extract the `ovms_hass` folder to your `custom_components` directory:
   ```
   custom_components/
   └── ovms_hass/
       ├── __init__.py
       ├── manifest.json
       └── ...
   ```
3. Restart Home Assistant

## Configuration

### Setup

Settings → Devices & Services → Add Integration → search for "OVMS", then
enter your OVMS server credentials:

- **Server Host**: `api.openvehicles.com` (default)
- **Port**: `6869` (HTTPS, default)
- **Username**: Your OVMS account username
- **Password**: Your OVMS REST API password
- **Vehicle ID**: Your vehicle ID (e.g., DEMO)
- **Vehicle Password**: Password configured in your OVMS module (required for commands)

Add one entry per vehicle.

### Changing the configuration later

- **Server host, port, username and passwords**: open the integration's
  entry and choose **Reconfigure**. The new settings are checked with a
  login before they are saved. The vehicle ID can't be changed; add another
  vehicle as a new entry.
- **Passwords**: when the OVMS server rejects the stored password, Home
  Assistant asks for a new one (Settings → Devices & Services shows the
  entry as needing attention).
- **Update interval**: the entry's **Options** (60-3600 seconds,
  default 300).

### Moving from YAML configuration

Configuring the integration with `ovms_hass:` in `configuration.yaml` is
deprecated and will be removed in a future release of this integration.

If you still have an `ovms_hass:` block, Home Assistant imports each vehicle
in it that doesn't have a UI entry yet, and shows a repair notice, "The OVMS
YAML configuration is being removed". Once a vehicle has an entry, the entry
is what counts: changes made in YAML are ignored. (If you delete the entry
while the YAML is still there, it is imported again at the next start.) To
finish the move:

1. Check that the integration works from its UI entry (Settings → Devices &
   Services → OVMS).
2. Remove the `ovms_hass:` block from `configuration.yaml`, and any
   `!secret` entries that only it used.
3. Restart Home Assistant. The repair notice disappears.

Entities, entity IDs and history stay as they are. Use **Reconfigure**,
the reauth prompt and **Options** (above) for later changes.

## Services

The integration provides seven advanced services for direct OVMS control:

### ovms_hass.send_command

Send a generic OVMS command to the vehicle.

```yaml
service: ovms_hass.send_command
data:
  vehicle_id: "DEMO"
  command: "stat" # Request status update
```

The command's output comes back as the service response. In a script or
automation, use `response_variable` to read it:

```yaml
- action: ovms_hass.send_command
  data:
    vehicle_id: "DEMO"
    command: "metrics get v.e.hvac"
  response_variable: reply
- if: "{{ reply.message == 'yes' }}"
  then:
    - action: notify.notify
      data:
        message: "Climate is running"
```

The call fails (raises an error) when the car doesn't acknowledge the
command or rejects it.

### ovms_hass.send_sms

Send an SMS message via the vehicle's modem.

```yaml
service: ovms_hass.send_sms
data:
  vehicle_id: "DEMO"
  phone_number: "+1234567890"
  message: "Hello from my vehicle!"
```

### ovms_hass.set_charge_timer

Configure the vehicle's charge timer.

```yaml
service: ovms_hass.set_charge_timer
data:
  vehicle_id: "DEMO"
  start_time: "23:00"
  enabled: true
```

### ovms_hass.wakeup_subsystem

Wake a specific vehicle subsystem.

```yaml
service: ovms_hass.wakeup_subsystem
data:
  vehicle_id: "DEMO"
  subsystem: 0
```

### ovms_hass.tpms_map_wheel

Map a TPMS sensor to a specific wheel position.

```yaml
service: ovms_hass.tpms_map_wheel
data:
  vehicle_id: "DEMO"
  wheel: "fl" # fl, fr, rl, rr
  sensor_id: "12345678"
```

### ovms_hass.set_feature

Set an OVMS module feature (0-15).

```yaml
service: ovms_hass.set_feature
data:
  vehicle_id: "DEMO"
  feature_number: 8 # GPS streaming interval
  value: "60"
```

#### GPS streaming

Feature 8 is the GPS streaming interval in seconds while driving (`0` turns
streaming off). Streaming sends a position update that often and uses mobile
data. Earlier versions had a "GPS Streaming Interval" number entity, but it
could never show the current value and was removed.

- **Set it** with `set_feature` as above, or with the module's shell
  command: `send_command` with `command: "config set vehicle stream 60"`
  (OVMS v3 modules).
- **Read it** with `send_command` and `command: "config list vehicle"`. The
  output, including `stream`, comes back as the service response (see
  `send_command` above).

### ovms_hass.set_parameter

Set an OVMS module parameter (0-31). To read parameters, use `send_command`
with the module's shell commands, e.g. `config list <param>` on OVMS v3.

```yaml
service: ovms_hass.set_parameter
data:
  vehicle_id: "DEMO"
  parameter_number: 0
  value: "custom_value"
```

## Code Quality Features

### Type Safety

- Full type hints on all functions and methods
- Dataclasses for structured data
- Enums for command codes

### Pythonic Design

- Async/await throughout for non-blocking I/O
- Context managers for resource cleanup
- Exception hierarchy for error handling
- Comprehensions and modern Python patterns

### Documentation

- Comprehensive docstrings (Google style)
- Module-level documentation
- Parameter descriptions
- Return value documentation

### Architecture

- Clear separation of concerns (API, commands, entities, coordination)
- No circular dependencies
- Extensible command and entity systems
- Reusable base classes

## API Usage Examples

### REST API (Reading Data)

```python
from ha_ovms.api import OVMSApiClient

async with OVMSApiClient(
    host="api.openvehicles.com",
    username="user",
    password="pass"
) as client:
    # Get vehicles
    vehicles = await client.list_vehicles()

    # Get vehicle data
    status = await client.get_status("DEMO")
    charge = await client.get_charge("DEMO")
    location = await client.get_location("DEMO")
    tpms = await client.get_tpms("DEMO")
```

### Commands (Sending Commands)

```python
from ha_ovms.commands import (
    OVMSCommandBuilder,
    ChargingCommand
)

# Build commands
ac_on = OVMSCommandBuilder.climate_on()  # "MP-0 C26,1"
ac_off = OVMSCommandBuilder.climate_off()  # "MP-0 C26,0"
cooldown = OVMSCommandBuilder.cooldown()  # "MP-0 C25"

# Charging commands
charging = ChargingCommand()
start = charging.start()  # "MP-0 C11"
stop = charging.stop()  # "MP-0 C12"
```

## Home Assistant Automations

### AC Control: Turn On AC When Hot

```yaml
automation:
  - trigger:
      platform: numeric_state
      entity_id: sensor.my_tesla_cabin_temperature
      above: 35
    action:
      service: button.press
      target:
        entity_id: button.my_tesla_ac_on
```

### AC Control: Turn Off AC via Send Command

```yaml
automation:
  - trigger:
      platform: state
      entity_id: input_boolean.ac_off_trigger
      to: "on"
    action:
      service: ovms_hass.send_command
      data:
        vehicle_id: "DEMO"
        command: "26,0" # AC OFF
```

### Security: Lock Car at Bedtime

```yaml
automation:
  - trigger:
      platform: time
      at: "22:00:00"
    action:
      service: lock.lock
      target:
        entity_id: lock.my_tesla_door_lock
```

### Charging: Set a Charge Limit (Nissan Leaf)

Protocol v2 has no command that sets a SOC limit, so the integration shows
the configured limit read-only (the "Charge Limit SOC" sensor). On a Nissan
Leaf, the module's "Charge to Limit" feature uses feature 10 for the SOC and
feature 11 for the range, which `set_feature` can write. Other vehicles use
these features differently or not at all; check your vehicle's OVMS docs
first.

```yaml
automation:
  - trigger:
      platform: state
      entity_id: sensor.my_leaf_charging_state
      to: "charging"
    action:
      service: ovms_hass.set_feature
      data:
        vehicle_id: "DEMO"
        feature_number: 10 # Leaf: charge to SOC limit
        value: "80"
```

### Security: Alert on Door Open While Away

```yaml
automation:
  - trigger:
      platform: state
      entity_id: binary_sensor.my_tesla_front_left_door
      to: "on"
    condition:
      - condition: state
        entity_id: person.owner
        state: "not_home"
    action:
      service: notify.mobile_app
      data:
        message: "Vehicle door opened while you're away!"
        title: "Security Alert"
```

### Valet Mode: Enable When Visitor Arrives

```yaml
automation:
  - trigger:
      platform: state
      entity_id: person.visitor
      to: "home"
    action:
      service: switch.turn_on
      target:
        entity_id: switch.my_tesla_valet_mode
```

### Garage: Open with HomeLink When Arriving

```yaml
automation:
  - trigger:
      platform: zone
      entity_id: device_tracker.my_tesla_location
      zone: zone.home
      event: enter
    action:
      service: button.press
      target:
        entity_id: button.my_tesla_homelink_1
```

### Monitoring: Alert on Connection Loss

```yaml
automation:
  - trigger:
      platform: state
      entity_id: sensor.my_tesla_connection_status
      to: "disconnected"
      for: "00:05:00"
    action:
      service: notify.mobile_app
      data:
        message: "Vehicle connection lost!"
        title: "OVMS Alert"
```

### Tracking: Increase GPS Updates When Away

```yaml
automation:
  - trigger:
      platform: state
      entity_id: device_tracker.my_tesla_location
      from: "home"
    action:
      service: ovms_hass.set_feature
      data:
        vehicle_id: "DEMO"
        feature_number: 8 # GPS streaming interval (see "GPS streaming")
        value: "60" # Update every 60 seconds while driving
```

### Advanced: Send Custom Command

```yaml
automation:
  - trigger:
      platform: state
      entity_id: input_boolean.custom_command_trigger
      to: "on"
    action:
      service: ovms_hass.send_command
      data:
        vehicle_id: "DEMO"
        command: "stat"
```

### Advanced: Configure Charge Timer

```yaml
automation:
  - trigger:
      platform: time
      at: "20:00:00"
    action:
      service: ovms_hass.set_charge_timer
      data:
        vehicle_id: "DEMO"
        start_time: "23:00"
        enabled: true
```

### Maintenance: Reset OVMS on Prolonged Inactivity

```yaml
automation:
  - trigger:
      platform: numeric_state
      entity_id: sensor.my_tesla_last_seen
      attribute: age_seconds
      above: 600 # 10 minutes
    action:
      - service: button.press
        target:
          entity_id: button.my_tesla_module_reset
      - service: notify.mobile_app
        data:
          message: "OVMS module reset due to inactivity"
```

## AC / Climate Control

The integration provides an **AC On** button to turn on the vehicle's air conditioning.
The climate entity was intentionally removed because the HVAC state reporting (`v.e.hvac`)
does not work reliably on all vehicle types, which caused the climate entity to show
incorrect state for many users.

### Why no climate entity?

- The HVAC status field is not available on all cars, so the climate entity often
  showed "OFF" even when AC was running
- A simple button is more reliable — it sends the command without depending on state feedback
- Users who need AC state can check the cabin temperature sensor or any available HVAC sensors

### Turning AC on

Simply press the **AC On** button entity, or use an automation:

```yaml
automation:
  - trigger:
      platform: numeric_state
      entity_id: sensor.my_vehicle_cabin_temperature
      above: 30
    action:
      service: button.press
      target:
        entity_id: button.my_vehicle_ac_on
```

### Turning AC off

Use the `ovms_hass.send_command` service with OVMS Command 26 (climate control), parameter 0 (off):

```yaml
service: ovms_hass.send_command
data:
  vehicle_id: "YOUR_VEHICLE_ID"
  command: "26,0"
```

Automation example:

```yaml
automation:
  - alias: "Turn off AC when cabin is cool"
    trigger:
      platform: numeric_state
      entity_id: sensor.my_vehicle_cabin_temperature
      below: 22
    action:
      service: ovms_hass.send_command
      data:
        vehicle_id: "YOUR_VEHICLE_ID"
        command: "26,0"
```

### Creating a custom AC on/off switch (template switch)

If you want a toggle switch for AC, you can create a template switch in your
`configuration.yaml`. This uses the AC On button for turning on, and the
`send_command` service for turning off:

```yaml
switch:
  - platform: template
    switches:
      vehicle_ac:
        friendly_name: "Vehicle AC"
        icon_template: mdi:air-conditioner
        turn_on:
          service: button.press
          target:
            entity_id: button.my_vehicle_ac_on
        turn_off:
          service: ovms_hass.send_command
          data:
            vehicle_id: "YOUR_VEHICLE_ID"
            command: "26,0"
```

> **Note:** This template switch does not track the actual AC state — it will
> appear as the last action you triggered. If you need real state tracking,
> you can add a `value_template` that reads from a sensor if your vehicle
> supports HVAC status reporting.

### Sending other custom commands

The `ovms_hass.send_command` service can send any OVMS command. Useful examples:

| Command    | Description          |
| ---------- | -------------------- |
| `26,1`     | AC on                |
| `26,0`     | AC off               |
| `25`       | Cooldown             |
| `11`       | Start charge         |
| `12`       | Stop charge          |
| `18`       | Wake up vehicle      |
| `stat`     | Request status       |
| `location` | Request GPS location |

```yaml
service: ovms_hass.send_command
data:
  vehicle_id: "YOUR_VEHICLE_ID"
  command: "stat"
```

## Known Limitations

### REST API Constraints

- **Polling-based updates**: The REST API requires periodic polling (default 5 minutes) rather than real-time push notifications
- **Rate limiting**: OVMS server implements rate limits (60 requests/minute, 120 burst)
- **Data availability**: Not all OVMS protocol v2 features are exposed via the REST API

### Vehicle-Specific Issues

#### State of Charge (SOC) Reporting

Some vehicles may report 0% SOC even when the battery is charged:

- **Nissan Leaf ZE0** (2018-2020): Requires specific OVMS firmware configuration
  - Set correct vehicle type: `config set vehicle type NL`
  - Configure model year: `config set auto leaf.modelyear 2018`
  - Set battery capacity: `config set auto leaf.soh.newcar 40000` (40kWh) or `62000` (e+)
  - Update firmware if running old version: `ota flash vfs`
- **Workaround**: Integration includes fallback logic checking `charge.soc` when `status.soc` is unavailable
- **Diagnostic**: Check SOC sensor attributes in HA for `status_soc_raw` and `charge_soc_raw` values

#### Command Support by Vehicle Type

Not all vehicles support all commands:

- **AC/Climate Control** (Command 26): Not all vehicles support HVAC state reporting. The AC On button sends the command but the HVAC state may not be available on all cars. Use `ovms_hass.send_command` with command `26,0` to turn AC off. Seres (SQ) uses Command 24
- **Cooldown** (Command 25): Support varies by vehicle model
- **Wake-up** (Command 18): May not work on all vehicle types
- **Charge Limits**: Protocol v2 has no SOC-limit command; the SOC limit is shown read-only. Vehicle-specific features may set it (e.g. Nissan Leaf feature 10, see the charge-limit example above)

### Device Information

Device details depend on OVMS firmware version and configuration:

- **Vehicle Type** (`car_type`): Requires OVMS firmware to provide this field
- **Firmware Version** (`m_firmware`, `m_version`): May not be available on older OVMS versions
- **Hardware Info** (`m_hardware`): Depends on OVMS configuration
- **VIN** (`car_vin`): Must be configured in OVMS module
- **GSM/WiFi Signal**: Only available if OVMS is connected via cellular or WiFi
- **Fallback**: Shows "Unknown" when data unavailable

### Connectivity Requirements

- **OVMS Module**: Must be powered and connected to OVMS server
- **Server Access**: Integration requires network access to OVMS server (default: api.openvehicles.com)
- **Vehicle State**: Some commands require vehicle to be awake and online
- **Command Timeout**: Protocol v2 commands have 30-second timeout (configurable)

### Data Freshness

- **Message Age**: Check `m_msgage_s` attribute to see data staleness in seconds
- **Stale Data Flags**: `staletemps`, `stalegps`, `staletpms` indicate outdated information
- **Last Seen**: Use the "Last Seen" sensor to monitor OVMS connectivity
- **GPS Accuracy**: Device tracker accuracy based on GPS lock status (`gpslock` field)

### Protocol v2 Binary Commands

- **Encryption**: Uses RC4 with HMAC-MD5 (implementation included)
- **Read-Only API**: This integration uses REST API for reading, binary protocol only for commands
- **No Push Updates**: Does not maintain persistent TCP connection for real-time updates
- **Server Relay**: Commands go through OVMS server, not directly to vehicle

### Integration Architecture

- **Single Vehicle Entry**: One config entry per vehicle (prevents duplicates)
- **No Historical Data UI**: Historical data endpoints implemented but not exposed in UI
- **Limited TPMS**: Basic tire pressure support, advanced TPMS features not implemented
- **No Valet Mode**: Valet mode endpoints exist but not implemented in entities

### Performance Considerations

- **Scan Interval**: Lower intervals increase server load and may hit rate limits
- **Parallel API Calls**: Integration fetches status/charge/location/tpms in parallel for efficiency
- **Error Handling**: Temporary API failures don't disable entities, will retry on next update
- **Connection Pooling**: Uses aiohttp session for connection reuse
- **Entity Defaults**: Technical/diagnostic sensors disabled by default to reduce UI clutter

## Diagnostic Tools

### Entity Attributes

Many sensors include diagnostic attributes:

- **SOC Sensor**: Shows `source`, `status_soc_raw`, `charge_soc_raw`, `battery_health`
- **Last Seen**: Shows `age_seconds` for data staleness
- **Connection Status**: Shows `car_connections`, `app_connections`, `batch_connections`

### Service Range/Time Sensors

Monitor when vehicle service is due:

- **Service Range**: Kilometers until service required
- **Service Time**: Days until service required
- Both disabled by default (enable via entity settings)

### Modem Mode Sensor

Shows cellular network type (2G/3G/4G):

- Useful for diagnosing connectivity issues
- Disabled by default (diagnostic category)

## Troubleshooting

### Connection Failed

- Check OVMS server is reachable: `ping api.openvehicles.com`
- Verify username/password in Home Assistant logs
- Ensure port 6869 is accessible (or 6868 for HTTP)
- Check OVMS server status at https://www.openvehicles.com

### Commands Not Working

- **Verify vehicle password**: Commands require the vehicle module password, not the REST API password
  - Check integration configuration has the correct vehicle_password set
  - This is the password configured in your OVMS module (Config → Server v2 → Password)
  - Look for "vehicle_password configured: YES" in Home Assistant logs
- Vehicle must be online and connected to OVMS server
- Some commands require vehicle to be awake (try wake-up button first)
- Check OVMS app to verify vehicle supports command
- Review Home Assistant logs for command errors (look for "Protocol v2 client" messages)
- Verify vehicle type supports the command (see Limitations section)

### Data Not Updating

- Default scan interval is 300 seconds (5 minutes)
- Check vehicle is actually connected to OVMS server
- Review Home Assistant logs for API errors
- Check "Last Seen" sensor for OVMS connectivity
- Verify message age (`m_msgage_s`) isn't excessively high

### SOC Shows 0% or Unavailable

- See "State of Charge (SOC) Reporting" in Limitations section
- Check SOC sensor attributes for diagnostic information
- Verify OVMS firmware configuration matches vehicle model
- Update OVMS firmware to latest version
- Check OVMS mobile app to confirm issue is integration vs. OVMS configuration

### Device Shows "Unknown"

- OVMS firmware may not provide device information fields
- Check if `car_type`, `m_firmware`, `m_hardware` fields are in API response
- Update OVMS firmware to latest version
- Configure vehicle type in OVMS module settings

## Development

### Project Structure

```
custom_components/ovms_hass/
├── __init__.py           # Integration setup & entry point
├── manifest.json         # Integration metadata
├── config_flow.py        # UI configuration flow
├── coordinator.py        # Data update coordinator
├── api.py               # REST API client
├── commands.py          # Binary protocol commands
├── entities.py          # Entity class definitions
├── services.py          # Service implementations
├── services.yaml        # Service schemas
├── strings.json         # UI strings
├── binary_sensor.py     # Binary sensor platform
├── sensor.py            # Sensor platform
├── button.py            # Button platform (includes AC On)
├── lock.py              # Lock platform
├── switch.py            # Switch platform
├── number.py            # Number platform
├── device_tracker.py    # Device tracker platform
├── diagnostics.py       # Diagnostic data export
└── translations/        # Localization files
    ├── en.json
    └── sv.json
```

### Adding New Binary Sensors

1. Create entity class in `entities.py`:

```python
class MyNewBinarySensor(OVMSEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.DOOR
    _attr_entity_registry_enabled_default = True  # or False

    def __init__(self, coordinator, vehicle_id):
        config = EntityConfig(
            unique_id="my_binary_sensor",
            name="My Binary Sensor",
            icon="mdi:my-icon",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def is_on(self):
        return self.coordinator.data.get("status", {}).get("my_field")
```

2. Add to `binary_sensor.py`:

```python
from .entities import MyNewBinarySensor

entities = [
    # ... existing entities
    MyNewBinarySensor(coordinator, coordinator.vehicle_id),
]
```

3. Add translations to `strings.json` and `translations/*.json`:

```json
"binary_sensor": {
  "my_binary_sensor": {
    "name": "My Binary Sensor"
  }
}
```

### Adding New Sensors

1. Create entity class in `entities.py`:

```python
class MyNewSensor(OVMSEntity, SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "unit"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_entity_registry_enabled_default = True  # or False

    def __init__(self, coordinator, vehicle_id):
        config = EntityConfig(
            unique_id="my_sensor",
            name="My Sensor",
            icon="mdi:my-icon",
        )
        super().__init__(coordinator, config, vehicle_id)

    @property
    def native_value(self):
        return self.coordinator.data.get("status", {}).get("my_field")
```

2. Add to `sensor.py` platform file

3. Add translations

### Adding New Services

1. Add service handler in `services.py`:

```python
async def async_my_service(hass: HomeAssistant, call: ServiceCall) -> None:
    """Handle my_service call."""
    vehicle_id = call.data["vehicle_id"]
    coordinator = _get_coordinator(hass, vehicle_id)

    if coordinator and coordinator.ovms_client:
        await coordinator.ovms_client.send_command("my_command")
```

2. Register service in `async_setup_services()`:

```python
hass.services.async_register(
    DOMAIN,
    "my_service",
    lambda call: async_my_service(hass, call),
    schema=MY_SERVICE_SCHEMA,
)
```

3. Add service schema to `services.yaml` for UI support

### Adding New Commands

1. Add to `CommandCode` enum in `commands.py`
2. Add static method to `OVMSCommandBuilder`
3. Optionally add convenience class

## License

MIT License

## Support & Contributing

- Issues: GitHub issue tracker
- Documentation: Inline code documentation and README
- Testing: Submit PR with tests

## Acknowledgments

- OVMS Project: https://www.openvehicles.com
- Home Assistant: https://www.home-assistant.io
