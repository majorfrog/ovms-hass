# Changelog

All notable changes to the OVMS Home Assistant integration will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-01-23

### Added
- Initial release of the OVMS Home Assistant integration
- Configuration flow for easy setup via UI
- Support for multiple vehicles per account
- REST API integration for data retrieval (ports 6868/6869)
- Binary Protocol v2 support for real-time commands (ports 6867/6870)

#### Entities
- **Climate entity** for AC/HVAC control
- **Lock entity** for door lock/unlock
- **Device tracker** for GPS location with battery level and accuracy

#### Switch Entities
- Cooldown mode (battery/cabin cooling)
- Valet mode

#### Number Entities
- Charge limit (50-100% SOC)
- Charge current (amperage control)
- GPS streaming interval

#### Binary Sensors (14 total)
- Door sensors (front left/right, rear left/right)
- Bonnet/hood status
- Trunk status
- Charge port status
- Parking brake status
- Pilot present (charger plugged in)
- Car started/on status
- Headlights status
- Alarm sounding status
- GPS lock status
- CAN write active status

#### Sensors (50+ total)
**Battery & Range:**
- State of Charge (SOC)
- State of Health (SOH)
- Estimated range
- Battery capacity (kWh)
- Battery voltage
- CAC (Calculated Amp Capacity)
- 12V battery voltage and current

**Temperature:**
- Ambient temperature
- Cabin temperature
- Battery temperature
- Motor temperature
- PEM (Power Electronics Module) temperature
- Charger temperature

**Charging:**
- Charging state
- Charging power
- Charging current
- Charger power input
- Charge type (AC/DC, connector type)
- Time to full charge
- Charge session energy (kWh)
- Charge limit range
- Grid energy used (session and total)
- Charger efficiency

**Driving & Power:**
- Odometer
- Speed
- Trip meter
- Power (instantaneous)
- Inverter power
- Inverter efficiency
- Drive mode
- Energy used
- Energy recovered

**Location:**
- Latitude
- Longitude
- Altitude
- Direction/heading

**Connectivity & Diagnostics:**
- Last seen timestamp
- GSM signal strength
- WiFi signal strength
- Connection status
- Firmware version
- Hardware version
- Modem mode (2G/3G/4G)
- Service range (km until service)
- Service time (days until service)

#### Buttons
- Refresh data
- Wake vehicle
- HomeLink 1-3 (garage door activation)
- Module reset
- TPMS auto-learn/reset

#### Services
- `send_command` - Send generic OVMS commands
- `send_sms` - Send SMS via vehicle modem
- `set_charge_timer` - Configure charge timer
- `wakeup_subsystem` - Wake specific vehicle subsystem
- `tpms_map_wheel` - Map TPMS sensor to wheel position
- `get_feature` / `set_feature` - Read/write module features (0-15)
- `get_parameter` / `set_parameter` - Read/write module parameters (0-31)

#### Other Features
- TPMS (Tire Pressure Monitoring System) sensors with per-wheel data
- Multi-language support (English, Swedish)
- Automatic vehicle discovery
- Configurable polling interval (60-3600 seconds)
- Secure credential storage via Home Assistant config entries
- Smart entity defaults (security-relevant entities enabled, technical/diagnostic disabled)
- Comprehensive service schemas with validation

### Changed
- N/A (initial release)

### Deprecated
- N/A (initial release)

### Removed
- N/A (initial release)

### Fixed
- N/A (initial release)

### Security
- Secure password handling with OVMS server authentication
- Support for both HTTP (6868) and HTTPS (6869) connections
- Encrypted Protocol v2 command communication
