# Contributing to OVMS Home Assistant Integration

Thank you for your interest in contributing to the OVMS Home Assistant integration!

## How to Contribute

### Reporting Bugs

If you find a bug, please open an issue on GitHub with:

1. A clear description of the bug
2. Steps to reproduce the issue
3. Expected behavior vs actual behavior
4. Home Assistant version
5. Integration version
6. OVMS module firmware version
7. Relevant log entries (with sensitive information removed)

### Feature Requests

Feature requests are welcome! Please open an issue with:

1. A clear description of the feature
2. Use case explaining why this feature would be useful
3. Any technical considerations you're aware of
4. Which OVMS commands or metrics would be involved

### Pull Requests

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Test your changes with your Home Assistant installation
5. Commit your changes (`git commit -m 'Add some amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

### Code Style

- Follow Python PEP 8 style guidelines
- Use type hints where appropriate
- Add docstrings to functions and classes
- Keep lines under 100 characters where reasonable
- Use meaningful variable and function names

### Testing

Before submitting a pull request:

1. Test the integration in a Home Assistant instance
2. Verify that existing functionality still works
3. Check that the integration loads without errors
4. Test with your OVMS-equipped vehicle if possible

### OVMS-Specific Guidelines

- Consult the [OVMS documentation](https://docs.openvehicles.com/) for protocol details
- Test commands safely - avoid potentially dangerous operations
- Consider the impact on vehicle battery when adding new polling features
- Be mindful of rate limits on the OVMS server

## Development Setup

1. Clone the repository to your Home Assistant's `custom_components` folder
2. Enable debug logging in your Home Assistant configuration:
   ```yaml
   logger:
     logs:
       custom_components.ovms_hass: debug
   ```
3. Restart Home Assistant to load changes

## Questions?

Feel free to open an issue for questions or discussions about the integration.
