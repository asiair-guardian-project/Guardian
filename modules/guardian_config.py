"""Guardian 1.0 safety-relevant configuration identity."""

from dataclasses import asdict, dataclass, is_dataclass
from enum import Enum
import hashlib
import json
from typing import Any, Mapping


@dataclass(frozen=True)
class SafetyConfiguration:
    """Safety-relevant installation configuration used for commissioning."""

    asiair: Mapping[str, Any]
    observatory_safety: Mapping[str, Any]
    mount: Mapping[str, Any]
    safety_power: Mapping[str, Any]
    guardian: Mapping[str, Any]


def _canonicalize(value: Any) -> Any:
    """Convert supported configuration values to deterministic JSON data."""

    if is_dataclass(value) and not isinstance(value, type):
        return _canonicalize(asdict(value))

    if isinstance(value, Enum):
        return value.name

    if isinstance(value, Mapping):
        return {
            str(key): _canonicalize(item)
            for key, item in sorted(
                value.items(),
                key=lambda pair: str(pair[0]),
            )
        }

    if isinstance(value, (set, frozenset)):
        canonical_items = [_canonicalize(item) for item in value]
        return sorted(
            canonical_items,
            key=lambda item: json.dumps(
                item,
                sort_keys=True,
                separators=(",", ":"),
            ),
        )

    if isinstance(value, (list, tuple)):
        return [_canonicalize(item) for item in value]

    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    raise TypeError(
        f"unsupported safety configuration value: {type(value).__name__}"
    )


def safety_configuration_fingerprint(
    configuration: SafetyConfiguration,
) -> str:
    """Return a stable SHA-256 fingerprint of safety-relevant configuration."""

    canonical = _canonicalize(configuration)
    encoded = json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")

    return hashlib.sha256(encoded).hexdigest()
