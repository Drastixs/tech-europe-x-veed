from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

NarrationVariantName = Literal["concise", "detailed"]


class NarrationError(RuntimeError):
    """Base class for narration generation failures."""


class NarrationConfigurationError(NarrationError):
    """Raised when narration generation is not configured correctly."""


class NarrationCacheError(NarrationError):
    """Raised when cached narration metadata cannot be read or written."""


class NarrationProviderError(NarrationError):
    """Raised when fal does not return a usable narration asset."""


@dataclass(frozen=True)
class NarrationSettings:
    api_key: str | None
    endpoint: str = "https://fal.run/fal-ai/elevenlabs/tts/eleven-v3"
    cache_dir: Path = Path(".cache/onshape-assist/narration")
    timeout_seconds: float = 60.0

    @classmethod
    def from_env(cls) -> NarrationSettings:
        return cls(
            api_key=os.getenv("FAL_KEY"),
            endpoint=os.getenv(
                "FAL_ELEVENLABS_ENDPOINT",
                "https://fal.run/fal-ai/elevenlabs/tts/eleven-v3",
            ),
            cache_dir=Path(
                os.getenv("NARRATION_CACHE_DIR", ".cache/onshape-assist/narration")
            ),
            timeout_seconds=float(os.getenv("FAL_TIMEOUT_SECONDS", "60")),
        )


@dataclass(frozen=True)
class NarrationAsset:
    url: str
    duration_ms: int


@dataclass(frozen=True)
class NarrationCacheKey:
    step_id: str
    variant: NarrationVariantName
    voice_id: str
    text_sha256: str
    speaking_rate: float

    @classmethod
    def create(
        cls,
        *,
        step_id: str,
        variant: NarrationVariantName,
        voice_id: str,
        text: str,
        speaking_rate: float,
    ) -> NarrationCacheKey:
        return cls(
            step_id=step_id,
            variant=variant,
            voice_id=voice_id,
            text_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            speaking_rate=speaking_rate,
        )

    @property
    def digest(self) -> str:
        canonical = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class NarrationMetadataCache:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def get(self, key: NarrationCacheKey) -> NarrationAsset | None:
        path = self._path(key)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("cache_key") != asdict(key):
                raise ValueError("cache key does not match its filename")
            return NarrationAsset(
                url=_required_url(payload.get("url")),
                duration_ms=_duration_ms(payload.get("duration_ms")),
            )
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise NarrationCacheError(f"Invalid narration cache entry: {path}") from exc

    def put(self, key: NarrationCacheKey, asset: NarrationAsset) -> None:
        path = self._path(key)
        temporary_path = path.with_suffix(".tmp")
        payload: dict[str, Any] = {
            "cache_key": asdict(key),
            "url": asset.url,
            "duration_ms": asset.duration_ms,
        }
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            temporary_path.write_text(
                json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8"
            )
            temporary_path.replace(path)
        except OSError as exc:
            raise NarrationCacheError(f"Could not write narration cache entry: {path}") from exc

    def _path(self, key: NarrationCacheKey) -> Path:
        return self.directory / f"{key.digest}.json"


def _required_url(value: object) -> str:
    if not isinstance(value, str) or not value.startswith(("https://", "http://")):
        raise ValueError("audio URL must be an HTTP(S) URL")
    return value


def _duration_ms(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError("duration_ms must be a non-negative number")
    return round(value)
