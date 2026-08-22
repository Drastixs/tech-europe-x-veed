from __future__ import annotations

import hashlib
import json
import os
from asyncio import gather
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, TypeVar

import httpx

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
        dotenv_path = Path(__file__).resolve().parent.parent / ".env"
        return cls(
            api_key=_environment_value("FAL_KEY", dotenv_path),
            endpoint=_environment_value(
                "FAL_ELEVENLABS_ENDPOINT", dotenv_path
            )
            or "https://fal.run/fal-ai/elevenlabs/tts/eleven-v3",
            cache_dir=Path(
                _environment_value("NARRATION_CACHE_DIR", dotenv_path)
                or ".cache/onshape-assist/narration"
            ),
            timeout_seconds=float(
                _environment_value("FAL_TIMEOUT_SECONDS", dotenv_path) or "60"
            ),
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


class FalNarrationService:
    """Generate and cache playable narration assets through fal ElevenLabs."""

    def __init__(
        self,
        settings: NarrationSettings | None = None,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings or NarrationSettings.from_env()
        self.cache = NarrationMetadataCache(self.settings.cache_dir)
        self.http_client = http_client

    async def synthesize(
        self,
        *,
        step_id: str,
        variant: NarrationVariantName,
        voice_id: str,
        text: str,
        speaking_rate: float,
        language_code: str | None = None,
    ) -> NarrationAsset:
        if not 0.7 <= speaking_rate <= 1.2:
            raise NarrationConfigurationError(
                "fal ElevenLabs speaking_rate must be between 0.7 and 1.2"
            )
        key = NarrationCacheKey.create(
            step_id=step_id,
            variant=variant,
            voice_id=voice_id,
            text=text,
            speaking_rate=speaking_rate,
        )
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        if not self.settings.api_key:
            raise NarrationConfigurationError(
                "FAL_KEY is required to generate uncached narration"
            )

        request_body: dict[str, object] = {
            "text": text,
            "voice": voice_id,
            "speed": speaking_rate,
            "timestamps": True,
            "output_format": "mp3_44100_128",
        }
        if language_code:
            request_body["language_code"] = language_code

        try:
            if self.http_client is None:
                async with httpx.AsyncClient(timeout=self.settings.timeout_seconds) as client:
                    response = await self._post(client, request_body)
            else:
                response = await self._post(self.http_client, request_body)
        except httpx.RequestError as exc:
            raise NarrationProviderError(f"fal ElevenLabs request failed: {exc}") from exc

        asset = _asset_from_response(response)
        self.cache.put(key, asset)
        return asset

    async def _post(
        self, client: httpx.AsyncClient, request_body: dict[str, object]
    ) -> httpx.Response:
        response = await client.post(
            self.settings.endpoint,
            headers={"Authorization": f"Key {self.settings.api_key}"},
            json=request_body,
            timeout=self.settings.timeout_seconds,
        )
        if response.is_error:
            raise NarrationProviderError(
                f"fal ElevenLabs returned HTTP {response.status_code}"
            )
        return response


PlanT = TypeVar("PlanT")


async def enrich_plan_narration(
    plan: PlanT, service: FalNarrationService | None = None
) -> PlanT:
    """Return a deep copy of a tutorial plan with both voice variants hosted."""
    enriched = _deep_copy_plan(plan)
    voice = _read(enriched, "voice")
    if _read(voice, "provider") != "fal_elevenlabs":
        raise NarrationConfigurationError("Tutorial plan voice provider must be fal_elevenlabs")
    generator = service or FalNarrationService()
    voice_id = _read(voice, "voice_id")
    speaking_rate = _read(voice, "speaking_rate")
    language_code = _read(enriched, "output_language")

    pending: list[tuple[object, Any]] = []
    for step in _read(enriched, "steps"):
        narration = _read(step, "narration")
        for variant_name in ("concise", "detailed"):
            variant = _read(narration, variant_name)
            if _is_hosted_url(_read(variant, "fal_elevenlabs_audio_url")):
                continue
            pending.append(
                (
                    variant,
                    generator.synthesize(
                        step_id=_read(step, "step_id"),
                        variant=variant_name,
                        voice_id=voice_id,
                        text=_read(variant, "text"),
                        speaking_rate=speaking_rate,
                        language_code=language_code,
                    ),
                )
            )

    if pending:
        assets = await gather(*(operation for _, operation in pending))
        for (variant, _), asset in zip(pending, assets, strict=True):
            _write(variant, "fal_elevenlabs_audio_url", asset.url)
            _write(variant, "duration_ms", asset.duration_ms)
    return enriched


def _asset_from_response(response: httpx.Response) -> NarrationAsset:
    try:
        payload = response.json()
        audio = payload["audio"]
        url = _required_url(audio["url"])
    except (KeyError, TypeError, ValueError) as exc:
        raise NarrationProviderError(
            "fal ElevenLabs response did not contain a hosted audio URL"
        ) from exc
    return NarrationAsset(url=url, duration_ms=_provider_duration_ms(payload))


def _provider_duration_ms(payload: dict[str, Any]) -> int:
    containers = [payload]
    if isinstance(payload.get("audio"), dict):
        containers.append(payload["audio"])
    for container in containers:
        if _is_number(container.get("duration_ms")):
            return max(0, round(container["duration_ms"]))
        if _is_number(container.get("duration_seconds")):
            return max(0, round(container["duration_seconds"] * 1000))

    timestamps = payload.get("timestamps")
    candidates: list[float] = []
    if isinstance(timestamps, list):
        for timestamp in timestamps:
            if isinstance(timestamp, dict):
                for field in ("end", "end_time", "end_seconds"):
                    if _is_number(timestamp.get(field)):
                        candidates.append(timestamp[field])
    elif isinstance(timestamps, dict):
        for field in (
            "character_end_times_seconds",
            "word_end_times_seconds",
            "end_times_seconds",
        ):
            values = timestamps.get(field)
            if isinstance(values, list):
                candidates.extend(value for value in values if _is_number(value))
    return max(0, round(max(candidates) * 1000)) if candidates else 0


def _environment_value(name: str, dotenv_path: Path) -> str | None:
    process_value = os.getenv(name)
    if process_value is not None:
        return process_value
    try:
        lines = dotenv_path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise NarrationConfigurationError(f"Could not read backend env file: {dotenv_path}") from exc
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.strip().removeprefix("export ").strip() == name:
            parsed = value.strip()
            if len(parsed) >= 2 and parsed[0] == parsed[-1] and parsed[0] in "\"'":
                parsed = parsed[1:-1]
            return parsed
    return None


def _deep_copy_plan(plan: PlanT) -> PlanT:
    model_copy = getattr(plan, "model_copy", None)
    if callable(model_copy):
        return model_copy(deep=True)
    if isinstance(plan, dict):
        import copy

        return copy.deepcopy(plan)
    raise TypeError("plan must be a Pydantic model or dictionary")


def _read(value: object, field: str) -> Any:
    if isinstance(value, dict):
        return value[field]
    return getattr(value, field)


def _write(value: object, field: str, replacement: object) -> None:
    if isinstance(value, dict):
        value[field] = replacement
    else:
        setattr(value, field, replacement)


def _is_hosted_url(value: object) -> bool:
    return isinstance(value, str) and value.startswith(("https://", "http://"))


def _is_number(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float))


def _required_url(value: object) -> str:
    if not isinstance(value, str) or not value.startswith(("https://", "http://")):
        raise ValueError("audio URL must be an HTTP(S) URL")
    return value


def _duration_ms(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError("duration_ms must be a non-negative number")
    return round(value)
