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
- **AC/HVAC Control** - Turn climate control on/off (Climate entity)
- **Charging** - Start/stop charging, set charge limits and current
- **Door Locks** - Lock/unlock vehicle doors (Lock entity)
- **Cooldown** - Activate battery/cabin cooling (Switch entity)
- **Vehicle Wake** - Wake vehicle from sleep mode
- **HomeLink** - Activate garage door openers
- **Module Reset** - Restart OVMS module remotely

### Home Assistant Entities

#### Core Entities
| Entity Type | Count | Examples |
|-------------|-------|----------|
| `climate` | 1 | AC/HVAC Control (COOL/OFF modes) |
| `lock` | 1 | Door Locks (lock/unlock) |
| `device_tracker` | 1 | GPS Location with battery & accuracy |
| `switch` | 2 | Cooldown, Valet Mode |
| `number` | 3 | Charge Limit (50-100%), Charge Current, GPS Interval |
| `binary_sensor` | 14 | Doors, Bonnet, Trunk, Charge Port, Parking Brake, Pilot Present, Car On, Headlights, Alarm, GPS Lock, CAN Write |
| `sensor` | 50+ | Battery, Charging, Temperature, Power, Location, Diagnostics |
| `button` | 7 | Refresh, Wake Up, HomeLink 1-3, Module Reset, TPMS Reset |

#### Binary Sensors (14 total)
| Binary Sensor | Default State | Purpose |
|---------------|---------------|---------|
| Front Left/Right Door | Enabled | Security monitoring |
| Rear Left/Right Door | Disabled | Less common usage |
| Bonnet/Hood | Enabled | Security monitoring |
| Trunk | Enabled | Security monitoring |
| Charge Port | Enabled | Charging workflows |
| Parking Brake | Disabled | Technical monitoring |
| Pilot Present | Enabled | Charger plugged in status |
| Car On/Started | Enabled | Vehicle state for automations |
| Headlights | Disabled | Less common monitoring |
| Alarm Sounding | Enabled | Security alert |
| GPS Lock | Disabled | Technical diagnostics |
| CAN Write Active | Disabled | Technical diagnostics |

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
- Charge Limit Range - disabled
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
- **HomeLink 1-3** - Activate garage door openers
- **Module Reset** - Restart OVMS module
- **TPMS Reset** - Auto-learn tire pressure sensors (disabled by default)

#### Services
Nine advanced services for vehicle control:
- `ovms_hass.send_command` - Send generic OVMS commands
- `ovms_hass.send_sms` - Send SMS via vehicle modem
- `ovms_hass.set_charge_timer` - Configure charging schedule
- `ovms_hass.wakeup_subsystem` - Wake specific vehicle subsystem
- `ovms_hass.tpms_map_wheel` - Map TPMS sensor to wheel position
- `ovms_hass.get_feature` / `ovms_hass.set_feature` - Module features (0-15)
- `ovms_hass.get_parameter` / `ovms_hass.set_parameter` - Module parameters (0-31)

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
2. Extract the `ovms-hass` folder to your `custom_components` directory:
   ```
   custom_components/
   └── ovms-hass/
       ├── __init__.py
       ├── manifest.json
       └── ...
   ```
3. Restart Home Assistant

## Configuration

### UI Configuration (Recommended)

1. Go to **Settings** → **Devices & Services**
2. Click **Add Integration**
3. Search for "OVMS"
4. Enter your OVMS server credentials:
   - **Server Host**: `api.openvehicles.com` (default)
   - **Port**: `6869` (HTTPS, default)
   - **Username**: Your OVMS account username
   - **Password**: Your OVMS account password
   - **Vehicle ID**: (Optional) Specific vehicle to monitor

### Options

After setup, you can configure additional options:
- **Update Interval**: How often to fetch data (60-3600 seconds, default: 300)

### YAML Configuration

For advanced users, YAML configuration is also supported:

```yaml
ovms-hass:
  host: api.openvehicles.com
  port: 6869  # 6869 for HTTPS, 6868 for HTTP
  username: your_ovms_username
  password: your_ovms_password
  vehicles:
    - vehicle_id: DEMO
      name: My Tesla
      scan_interval: 300  # seconds
    - vehicle_id: TEST
      name: Work Vehicle
      scan_interval: 600
```

### UI Configuration
Settings → Devices & Services → Add Integration → Search "OVMS"

## Services

The integration provides nine advanced services for direct OVMS control:

### ovms_hass.send_command
Send a generic OVMS command to the vehicle.
```yaml
service: ovms_hass.send_command
data:
  vehicle_id: "DEMO"
  command: "stat"  # Request status update
```

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
  wheel: "fl"  # fl, fr, rl, rr
  sensor_id: "12345678"
```

### ovms_hass.get_feature / ovms_hass.set_feature
Read or write OVMS module features (0-15).
```yaml
service: ovms_hass.set_feature
data:
  vehicle_id: "DEMO"
  feature_number: 8  # GPS streaming interval
  value: "60"
```

### ovms_hass.get_parameter / ovms_hass.set_parameter
Read or write OVMS module parameters (0-31).
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
    ClimateControlCommand,
    ChargingCommand
)

# Build commands
ac_on = OVMSCommandBuilder.climate_on()  # "MP-0 C26,1"
ac_off = OVMSCommandBuilder.climate_off()  # "MP-0 C26,0"
cooldown = OVMSCommandBuilder.cooldown()  # "MP-0 C25"

# Or use convenience classes
climate = ClimateControlCommand("standard")
ac_on = climate.turn_on()
ac_off = climate.turn_off()

charging = ChargingCommand()
start = charging.start()  # "MP-0 C11"
stop = charging.stop()  # "MP-0 C12"
```

## Home Assistant Automations

### Climate Control: Turn On AC When Hot
```yaml
automation:
  - trigger:
      platform: numeric_state
      entity_id: sensor.my_tesla_cabin_temperature
      above: 35
    action:
      service: climate.set_hvac_mode
      target:
        entity_id: climate.my_tesla_climate_control
      data:
        hvac_mode: cool
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

### Charging: Set Optimal Charge Limit
```yaml
automation:
  - trigger:
      platform: state
      entity_id: sensor.my_tesla_charging_state
      to: "charging"
    action:
      service: number.set_value
      target:
        entity_id: number.my_tesla_charge_limit
      data:
        value: 80
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
      service: number.set_value
      target:
        entity_id: number.my_tesla_gps_streaming_interval
      data:
        value: 60  # Update every 60 seconds
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
      above: 600  # 10 minutes
    action:
      - service: button.press
        target:
          entity_id: button.my_tesla_module_reset
      - service: notify.mobile_app
        data:
          message: "OVMS module reset due to inactivity"
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
- **AC/Climate Control** (Command 26): Standard vehicles only. Seres (SQ) uses Command 24
- **Cooldown** (Command 25): Support varies by vehicle model
- **Wake-up** (Command 18): May not work on all vehicle types
- **Charge Limits**: Some vehicles don't support setting charge limits via OVMS

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
- Vehicle must be online and connected to OVMS server
- Some commands require vehicle to be awake (try wake-up button first)
- Check OVMS app to verify vehicle supports command
- Review Home Assistant logs for command errors
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
custom_components/ovms-hass/
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
├── button.py            # Button platform
├── climate.py           # Climate platform
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

