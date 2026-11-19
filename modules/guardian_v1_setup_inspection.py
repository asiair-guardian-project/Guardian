"""Read-only, redacted setup inspection; never activates configuration."""
from pathlib import Path
from modules.guardian_v1_setup_staging import configuration_sha256, stage_configuration
from modules.guardian_v1_setup_config import read_installation, redacted_overview, validate_changes, SetupValidationError
from modules.guardian_v1_setup_binding import compare_monitor_binding

def make_setup_provider(path, binding):
    config_path = Path(path).expanduser().resolve()
    def inspect():
        try:
            config = read_installation(config_path)
            comparison = compare_monitor_binding(config, binding)
            return {
                "available": True,
                "review_sha256": configuration_sha256(config_path),
                "sections": redacted_overview(config),
                "matches_active_monitor": comparison["matches_active_monitor"],
                "differences": comparison["differences"],
                "editable": False,
                "save_available": False,
                "commissioning_authorized": False,
            }
        except (OSError, ValueError, TypeError):
            return {"available": False, "reason": "Installation configuration unavailable or invalid",
                    "editable": False, "save_available": False, "commissioning_authorized": False}
    def preview(changes):
        # Validation is purely in-memory. Never return submitted endpoint values.
        try:
            current = read_installation(config_path)
            candidate = validate_changes(current, changes)
            comparison = compare_monitor_binding(candidate, binding)
            changed = sorted(f"{section}.{field}" for section, fields in changes.items()
                             for field in fields)
            return {"ok": True, "code": "SETUP_PREVIEW", "valid": True,
                    "changed_fields": changed,
                    "matches_active_monitor": comparison["matches_active_monitor"],
                    "differences": comparison["differences"],
                    "save_available": False, "applied": False,
                    "commissioning_authorized": False,
                    "message": "Validated in memory only; nothing saved or activated"}
        except (OSError, ValueError, TypeError, KeyError):
            # Deliberately do not echo exception strings: may contain user input.
            return {"ok": False, "code": "SETUP_PREVIEW_REJECTED", "valid": False,
                    "save_available": False, "applied": False,
                    "commissioning_authorized": False,
                    "message": "Proposed settings rejected or configuration unavailable"}
    def stage(changes, expected_sha256):
        # Explicitly creates a separate private candidate. Never activates it.
        try:
            if not isinstance(expected_sha256, str) or len(expected_sha256) != 64:
                raise ValueError("Missing review identity")
            if not isinstance(changes, dict):
                raise ValueError("Invalid changes")
            # Fixed, non-overwriting destination; no caller-controlled filesystem path.
            dest = config_path.with_name("config.guardian-candidate.yaml")
            result = stage_configuration(config_path, changes,
                expected_sha256=expected_sha256, destination=dest)
            return {"ok": True, "code": "SETUP_STAGED", "staged": True,
                    "activated": False, "commissioning_authorized": False,
                    "changed_fields": result["changed_fields"],
                    "message": "Candidate saved separately; active configuration unchanged"}
        except (OSError, ValueError, TypeError, KeyError):
            return {"ok": False, "code": "SETUP_STAGE_REJECTED", "staged": False,
                    "activated": False, "commissioning_authorized": False,
                    "message": "Staging rejected: configuration changed, invalid, or candidate already exists"}
    inspect.stage = stage
    inspect.preview = preview
    return inspect
