import json

import pytest

from onshape_assist.narration import (
    NarrationAsset,
    NarrationCacheError,
    NarrationCacheKey,
    NarrationConfigurationError,
    NarrationMetadataCache,
    NarrationSettings,
)


def make_key(**overrides) -> NarrationCacheKey:
    values = {
        "step_id": "open-revolve",
        "variant": "concise",
        "voice_id": "Rachel",
        "text": "Let's revolve Sketch 1.",
        "speaking_rate": 1.0,
    }
    values.update(overrides)
    return NarrationCacheKey.create(**values)


def test_cache_key_is_deterministic_and_covers_required_inputs():
    original = make_key()

    assert original.digest == make_key().digest
    assert original.digest != make_key(step_id="confirm-revolve").digest
    assert original.digest != make_key(variant="detailed").digest
    assert original.digest != make_key(voice_id="Aria").digest
    assert original.digest != make_key(text="Open Revolve.").digest
    assert original.digest != make_key(speaking_rate=1.1).digest


def test_metadata_cache_round_trip(tmp_path):
    cache = NarrationMetadataCache(tmp_path)
    key = make_key()
    asset = NarrationAsset("https://fal.media/audio.mp3", 1234)

    assert cache.get(key) is None
    cache.put(key, asset)

    assert cache.get(key) == asset
    payload = json.loads(next(tmp_path.iterdir()).read_text())
    assert payload["cache_key"]["step_id"] == "open-revolve"
    assert payload["cache_key"]["text_sha256"] == key.text_sha256


def test_invalid_cache_entry_raises_typed_error(tmp_path):
    cache = NarrationMetadataCache(tmp_path)
    key = make_key()
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / f"{key.digest}.json").write_text("not-json")

    with pytest.raises(NarrationCacheError):
        cache.get(key)


def test_settings_are_configurable_from_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("FAL_KEY", "server-secret")
    monkeypatch.setenv("FAL_ELEVENLABS_ENDPOINT", "https://fal.example/tts")
    monkeypatch.setenv("NARRATION_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("FAL_TIMEOUT_SECONDS", "12.5")

    settings = NarrationSettings.from_env()

    assert settings.api_key == "server-secret"
    assert settings.endpoint == "https://fal.example/tts"
    assert settings.cache_dir == tmp_path
    assert settings.timeout_seconds == 12.5


def test_invalid_timeout_has_a_typed_configuration_error(monkeypatch):
    monkeypatch.setenv("FAL_TIMEOUT_SECONDS", "eventually")

    with pytest.raises(NarrationConfigurationError, match="must be a number"):
        NarrationSettings.from_env()
