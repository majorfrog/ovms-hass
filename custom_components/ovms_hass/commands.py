"""OVMS Vehicle Command Protocol v2.

This module provides command execution for the OVMS binary Protocol v2.
It handles command codes and parameters for vehicle control operations.

Protocol v2 uses TCP connections on ports 6867 (plaintext) and 6870 (TLS),
with RC4 encryption and HMAC-MD5 authentication for message integrity.
"""

from dataclasses import dataclass
from enum import IntEnum


class CommandCode(IntEnum):
    """OVMS Protocol v2 command codes."""

    # Information queries
    GET_FEATURES = 1
    SET_FEATURE = 2
    GET_PARAMETERS = 3
    SET_PARAMETER = 4

    # Vehicle control
    REBOOT = 5
    GET_STATUS = 6
    GENERIC_COMMAND = 7

    # Charging control
    SET_CHARGE_MODE = 10
    START_CHARGE = 11
    STOP_CHARGE = 12
    SET_CHARGE_CURRENT = 15
    SET_CHARGE_PARAMETERS = 16
    SET_CHARGE_TIMER = 17

    # Vehicle wakeup
    WAKEUP_CAR = 18
    WAKEUP_SUBSYSTEM = 19

    # Door/lock control
    LOCK_CAR = 20
    SET_VALET_MODE = 21
    UNLOCK_CAR = 22
    CLEAR_VALET_MODE = 23

    # Climate and garage door
    HOME_LINK = 24
    COOLDOWN = 25
    CLIMATE_CONTROL = 26

    # Data queries
    GET_USAGE = 30
    GET_DATA_SUMMARY = 31
    GET_DATA_RECORDS = 32

    # Communication
    SEND_SMS = 40
    SEND_MMI_USSD = 41
    MODEM_COMMAND = 49


@dataclass
class CommandResponse:
    """Response from a vehicle command."""

    code: int
    """Command code that was executed"""

    result_code: int
    """Result code: 0=success, 1=failed, 2=unsupported, 3=unimplemented"""

    message: str
    """Response message from vehicle"""

    is_success: bool
    """True if result code is 0 (success)"""

    @classmethod
    def parse(cls, response_str: str) -> "CommandResponse":
        """Parse command response string.

        Response format: "c<code>,<result_code>[,<message>]"

        Args:
            response_str: Raw response string from vehicle

        Returns:
            CommandResponse object
        """
        parts = response_str.lstrip("c").split(",", 2)
        code = int(parts[0]) if len(parts) > 0 else 0
        result_code = int(parts[1]) if len(parts) > 1 else -1
        message = parts[2] if len(parts) > 2 else ""

        return cls(
            code=code,
            result_code=result_code,
            message=message,
            is_success=result_code == 0,
        )


class OVMSCommandBuilder:
    """Builder for constructing OVMS Protocol v2 commands.

    Commands follow the format: "MP-0 C<code>[,<param1>[,<param2>...]]"
    """

    @staticmethod
    def build_command(code: int, *params: str | int) -> str:
        """Build a Protocol v2 command string.

        Args:
            code: Command code
            *params: Command parameters (converted to strings)

        Returns:
            Formatted command string ready for transmission
        """
        param_str = ",".join(str(p) for p in params) if params else ""
        command = f"MP-0 C{code}"
        if param_str:
            command += f",{param_str}"
        return command

    @staticmethod
    def climate_on(vehicle_type: str = "standard") -> str:
        """Build command to turn on AC/climate control.

        Args:
            vehicle_type: Type of vehicle ("standard" or "sq")

        Returns:
            Command string for AC ON
        """
        if vehicle_type.lower() == "sq":
            # SQ vehicles use command 24 with timing (0=5min, 1=10min, 2=15min)
            return OVMSCommandBuilder.build_command(CommandCode.HOME_LINK, 0)
        # Standard vehicles use command 26 with parameter 1
        return OVMSCommandBuilder.build_command(CommandCode.CLIMATE_CONTROL, 1)

    @staticmethod
    def climate_off(vehicle_type: str = "standard") -> str:
        """Build command to turn off AC/climate control.

        Args:
            vehicle_type: Type of vehicle ("standard" or "sq")

        Returns:
            Command string for AC OFF
        """
        if vehicle_type.lower() == "sq":
            # SQ vehicles use a different approach
            return OVMSCommandBuilder.build_command(CommandCode.GENERIC_COMMAND, "climate off")
        # Standard vehicles use command 26 with parameter 0
        return OVMSCommandBuilder.build_command(CommandCode.CLIMATE_CONTROL, 0)

    @staticmethod
    def cooldown() -> str:
        """Build command to activate battery/cabin cooldown.

        Returns:
            Command string for cooldown activation
        """
        return OVMSCommandBuilder.build_command(CommandCode.COOLDOWN)

    @staticmethod
    def start_charge() -> str:
        """Build command to start vehicle charging.

        Returns:
            Command string for start charge
        """
        return OVMSCommandBuilder.build_command(CommandCode.START_CHARGE)

    @staticmethod
    def stop_charge() -> str:
        """Build command to stop vehicle charging.

        Returns:
            Command string for stop charge
        """
        return OVMSCommandBuilder.build_command(CommandCode.STOP_CHARGE)

    @staticmethod
    def set_charge_limit(soc_percent: int) -> str:
        """Build command to set charge limit SOC.

        Args:
            soc_percent: State of charge limit (0-100)

        Returns:
            Command string for set charge limit
        """
        soc_percent = max(0, min(100, soc_percent))
        return OVMSCommandBuilder.build_command(CommandCode.SET_CHARGE_PARAMETERS, soc_percent)

    @staticmethod
    def set_charge_current(amps: int) -> str:
        """Build command to set charging current.

        Args:
            amps: Charging current in amperes

        Returns:
            Command string for set charge current
        """
        return OVMSCommandBuilder.build_command(CommandCode.SET_CHARGE_CURRENT, amps)

    @staticmethod
    def lock_car() -> str:
        """Build command to lock car doors and ignition.

        Returns:
            Command string for lock car
        """
        return OVMSCommandBuilder.build_command(CommandCode.LOCK_CAR)

    @staticmethod
    def unlock_car() -> str:
        """Build command to unlock car doors and ignition.

        Returns:
            Command string for unlock car
        """
        return OVMSCommandBuilder.build_command(CommandCode.UNLOCK_CAR)

    @staticmethod
    def enable_valet_mode() -> str:
        """Build command to enable valet mode restrictions.

        Returns:
            Command string for enable valet mode
        """
        return OVMSCommandBuilder.build_command(CommandCode.SET_VALET_MODE)

    @staticmethod
    def disable_valet_mode() -> str:
        """Build command to disable valet mode restrictions.

        Returns:
            Command string for disable valet mode
        """
        return OVMSCommandBuilder.build_command(CommandCode.CLEAR_VALET_MODE)

    @staticmethod
    def wakeup_car() -> str:
        """Build command to wake vehicle from sleep.

        Returns:
            Command string for wakeup car
        """
        return OVMSCommandBuilder.build_command(CommandCode.WAKEUP_CAR)

    @staticmethod
    def wakeup_subsystem(subsystem: str) -> str:
        """Build command to wake specific vehicle subsystem.

        Args:
            subsystem: Subsystem identifier

        Returns:
            Command string for wakeup subsystem
        """
        return OVMSCommandBuilder.build_command(CommandCode.WAKEUP_SUBSYSTEM, subsystem)

    @staticmethod
    def homelink(button: int = 0) -> str:
        """Build command to activate home link (garage door).

        Args:
            button: HomeLink button number (0, 1, or 2 for buttons 1-3)

        Returns:
            Command string for homelink activation
        """
        return OVMSCommandBuilder.build_command(CommandCode.HOME_LINK, button)

    @staticmethod
    def reboot_module() -> str:
        """Build command to reboot OVMS module.

        Returns:
            Command string for module reset
        """
        return OVMSCommandBuilder.build_command(CommandCode.REBOOT)

    @staticmethod
    def generic_command(command_text: str) -> str:
        """Build generic command.

        Args:
            command_text: Generic command text

        Returns:
            Command string for generic command
        """
        return OVMSCommandBuilder.build_command(CommandCode.GENERIC_COMMAND, command_text)


class ClimateControlCommand:
    """Convenience class for climate control commands.

    AC/HVAC control uses command code 26 for standard vehicles
    and command code 24 for SQ vehicles.
    """

    def __init__(self, vehicle_type: str = "standard"):
        """Initialize climate control for specific vehicle type.

        Args:
            vehicle_type: Type of vehicle ("standard", "nl", "se", "vwup", "rz2", "sq")
        """
        self.vehicle_type = vehicle_type.lower()
        self.is_sq = self.vehicle_type == "sq"

    def turn_on(self) -> str:
        """Command to turn on AC/climate control."""
        return OVMSCommandBuilder.climate_on(self.vehicle_type)

    def turn_off(self) -> str:
        """Command to turn off AC/climate control."""
        return OVMSCommandBuilder.climate_off(self.vehicle_type)

    def cooldown(self) -> str:
        """Command to activate battery/cabin cooldown."""
        return OVMSCommandBuilder.cooldown()

    def get_status_command(self) -> str:
        """Get status command for climate control.

        Returns:
            Command to query climate control status
        """
        if self.is_sq:
            return OVMSCommandBuilder.generic_command("schedule status")
        return OVMSCommandBuilder.build_command(CommandCode.GET_STATUS)


class ChargingCommand:
    """Convenience class for vehicle charging commands."""

    @staticmethod
    def start() -> str:
        """Command to start charging."""
        return OVMSCommandBuilder.start_charge()

    @staticmethod
    def stop() -> str:
        """Command to stop charging."""
        return OVMSCommandBuilder.stop_charge()

    @staticmethod
    def set_limit(soc_percent: int) -> str:
        """Command to set charge limit SOC.

        Args:
            soc_percent: Target state of charge (0-100)
        """
        return OVMSCommandBuilder.set_charge_limit(soc_percent)

    @staticmethod
    def set_current(amps: int) -> str:
        """Command to set charging current.

        Args:
            amps: Target amperage
        """
        return OVMSCommandBuilder.set_charge_current(amps)


class LockCommand:
    """Convenience class for door lock commands."""

    @staticmethod
    def lock() -> str:
        """Command to lock vehicle doors and ignition."""
        return OVMSCommandBuilder.lock_car()

    @staticmethod
    def unlock() -> str:
        """Command to unlock vehicle doors and ignition."""
        return OVMSCommandBuilder.unlock_car()


class ValetModeCommand:
    """Convenience class for valet mode commands."""

    @staticmethod
    def enable() -> str:
        """Command to enable valet mode restrictions."""
        return OVMSCommandBuilder.enable_valet_mode()

    @staticmethod
    def disable() -> str:
        """Command to disable valet mode restrictions."""
        return OVMSCommandBuilder.disable_valet_mode()
