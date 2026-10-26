# Open work

Standing backlog. Edit line by line, never rewrite wholesale. When an item is finished, delete
its line; the reason it closed belongs in the commit message, CHANGELOG or git history.


- [ ] (2026-10-26) [10] FOUND: src/check_zpools/defaultconfig.toml documents list settings' environment overrides as "(comma-separated)" (lines 90, 131, 167, 182, 211), but CHECK_ZPOOLS___ALERTS__ALERT_ON_SEVERITIES takes a JSON list: a comma-separated value fails the config load (checked in the repo .venv by the bitranox-skills [23] fold, 2026-10-26) | size: 5 comment lines, 4 of them unverified | open: first seen here | next: set each variable comma-separated and as a JSON list in a test, then correct every comment to what the loader accepts
- [ ] (2026-10-26) [20] FOUND: daemon.py:483 logs a DELIBERATE skip (an issue below alert_on_severities) as "Failed to send alert", so the journal reports a failure that is configured behaviour | size: one log call + a test | open: first seen here; the bitranox infra-storage-check-zpools skill now explains the message and goes stale once this is fixed | next: log the skip at debug/info with its reason, RED test on the message, then update the skill paragraph and its twin
