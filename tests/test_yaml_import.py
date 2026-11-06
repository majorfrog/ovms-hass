"""Tests for the deprecated YAML import and its repair issue."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components import ovms_hass

YAML = {
    "host": "ovms.example",
    "port": 6869,
    "username": "user",
    "password": "pw",
    "vehicles": [{"vehicle_id": "APA123"}],
}
ISSUE_ID = "deprecated_yaml_ovms_hass"


async def _setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the integration; the patch covers the entry setup after import."""
    with patch.object(ovms_hass, "async_setup_entry", AsyncMock(return_value=True)):
        result = await async_setup_component(hass, "ovms_hass", config)
        await hass.async_block_till_done()
    return result


def _issue(hass: HomeAssistant) -> ir.IssueEntry | None:
    return ir.async_get(hass).async_get_issue("homeassistant", ISSUE_ID)


async def test_yaml_raises_deprecation_issue(hass: HomeAssistant) -> None:
    """YAML still present: HA's standard notice asks to remove it."""
    assert await _setup(hass, {"ovms_hass": YAML})

    issue = _issue(hass)
    assert issue is not None
    assert issue.severity is ir.IssueSeverity.WARNING
    assert issue.issue_domain == "ovms_hass"
    assert issue.translation_key == "deprecated_yaml"
    assert issue.translation_placeholders == {
        "domain": "ovms_hass",
        "integration_title": "OVMS",
    }


async def test_yaml_without_entry_still_imports(hass: HomeAssistant) -> None:
    """A YAML-only user still gets an entry during the deprecation period."""
    assert await _setup(hass, {"ovms_hass": YAML})

    entries = hass.config_entries.async_entries("ovms_hass")
    assert [(e.unique_id, e.source) for e in entries] == [("APA123", "import")]


async def test_yaml_import_does_not_overwrite_entry(hass: HomeAssistant) -> None:
    """The entry wins: a password fixed through reauth survives a restart."""
    entry = MockConfigEntry(
        domain="ovms_hass",
        unique_id="APA123",
        source="import",
        data={**YAML, "vehicle_id": "APA123", "password": "new-pw"},
    )
    entry.add_to_hass(hass)

    assert await _setup(hass, {"ovms_hass": YAML})

    assert entry.data["password"] == "new-pw"
    assert len(hass.config_entries.async_entries("ovms_hass")) == 1


async def test_issue_deleted_when_yaml_removed(hass: HomeAssistant) -> None:
    """Once the YAML is gone, the notice is removed."""
    ir.async_create_issue(
        hass,
        "homeassistant",
        ISSUE_ID,
        issue_domain="ovms_hass",
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="deprecated_yaml",
        translation_placeholders={"domain": "ovms_hass", "integration_title": "OVMS"},
    )

    assert await _setup(hass, {})

    assert _issue(hass) is None


async def test_no_yaml_no_issue(hass: HomeAssistant) -> None:
    """Without YAML nothing is raised and setup succeeds."""
    assert await _setup(hass, {})

    assert _issue(hass) is None
