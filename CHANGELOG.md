# Changelog

All notable changes to this project will be documented in this file following
the [Keep a Changelog](https://keepachangelog.com/) format.

## [Unreleased]

### Added
- Email sending functionality via `btx-lib-mail>=1.0.1` integration
- Two new CLI commands: `send-email` and `send-notification`
- Email configuration support via lib_layered_config with sensible defaults
- Comprehensive email wrapper with `EmailConfig` dataclass in `mail.py`
- Email configuration validation in `__post_init__` (timeout, from_address, SMTP host:port format)
- Real SMTP integration tests using .env configuration (TEST_SMTP_SERVER, TEST_EMAIL_ADDRESS)
- 48 new tests covering email functionality:
  - 18 EmailConfig validation tests
  - 4 configuration loading tests
  - 6 email sending tests (unit)
  - 2 notification tests (unit)
  - 5 error scenario tests
  - 5 edge case tests
  - 3 real SMTP integration tests
  - 10 CLI integration tests
- `.env.example` documentation for TEST_SMTP_SERVER and TEST_EMAIL_ADDRESS
- DotEnv loading in test suite for integration test configuration

### Changed
- Extracted `_load_and_validate_email_config()` helper function to eliminate code duplication between CLI email commands
- Updated test suite from 56 to 104 passing tests
- Increased code coverage from 79% to 87.50%
- Enhanced `conftest.py` with automatic .env loading for integration tests

### Dependencies
- Added `btx-lib-mail>=1.0.1` for SMTP email sending capabilities

## [0.0.1] - 2025-11-11
- Bootstrap 
