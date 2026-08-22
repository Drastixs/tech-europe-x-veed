import httpx
import pytest
from test_app import tutorial_plan

from onshape_assist.app import TutorialPlan
from onshape_assist.narration import (
    FalNarrationService,
    NarrationConfigurationError,
    NarrationProviderError,
    NarrationSettings,
    enrich_plan_narration,
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


def service(tmp_path, handler, *, api_key="fal-secret"):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = NarrationSettings(
        api_key=api_key,
        endpoint="https://fal.example/elevenlabs",
        cache_dir=tmp_path,
        timeout_seconds=3,
    )
    return FalNarrationService(settings, http_client=client), client


@pytest.mark.anyio
async def test_enriches_both_variants_and_uses_provider_duration(tmp_path):
    requests = []

    def handler(request):
        requests.append(request)
        body = __import__("json").loads(request.content)
        duration = 1.25 if body["text"].startswith("Let's") else 3.5
        return httpx.Response(
            200,
            json={
                "audio": {"url": f"https://fal.media/{len(requests)}.mp3"},
                "duration_seconds": duration,
            },
        )

    generator, client = service(tmp_path, handler)
    plan = TutorialPlan.model_validate(tutorial_plan())
    plan.output_language = "en-GB"
    for variant in (plan.steps[0].narration.concise, plan.steps[0].narration.detailed):
        variant.fal_elevenlabs_audio_url = "fal://pending"
        variant.duration_ms = 0

    enriched = await enrich_plan_narration(plan, generator)
    await client.aclose()

    assert len(requests) == 2
    assert requests[0].headers["authorization"] == "Key fal-secret"
    first_body = __import__("json").loads(requests[0].content)
    assert first_body["voice"] == "friendly-tutor"
    assert first_body["speed"] == 1.0
    assert first_body["language_code"] == "en"
    assert first_body["timestamps"] is True
    assert enriched.steps[0].narration.concise.duration_ms == 1250
    assert enriched.steps[0].narration.detailed.duration_ms == 3500
    assert plan.steps[0].narration.concise.fal_elevenlabs_audio_url == "fal://pending"


@pytest.mark.anyio
async def test_cached_assets_avoid_provider_and_do_not_need_api_key(tmp_path):
    provider_calls = 0

    def successful_handler(request):
        nonlocal provider_calls
        provider_calls += 1
        return httpx.Response(
            200,
            json={"audio": {"url": f"https://fal.media/{provider_calls}.mp3"}},
        )

    populated_service, populated_client = service(tmp_path, successful_handler)
    plan = tutorial_plan()
    for variant in plan["steps"][0]["narration"].values():
        variant["fal_elevenlabs_audio_url"] = "fal://pending"
        variant["duration_ms"] = 0
    first = await enrich_plan_narration(plan, populated_service)
    await populated_client.aclose()

    def forbidden_handler(request):
        raise AssertionError("cache hit must not call fal")

    cached_service, cached_client = service(tmp_path, forbidden_handler, api_key=None)
    second = await enrich_plan_narration(plan, cached_service)
    await cached_client.aclose()

    assert provider_calls == 2
    assert second == first


@pytest.mark.anyio
async def test_already_hosted_variants_are_not_regenerated(tmp_path):
    def forbidden_handler(request):
        raise AssertionError("hosted asset must not call fal")

    generator, client = service(tmp_path, forbidden_handler, api_key=None)
    plan = TutorialPlan.model_validate(tutorial_plan())
    plan.steps[0].narration.concise.fal_elevenlabs_audio_url = (
        "https://fal.media/concise.mp3"
    )
    plan.steps[0].narration.detailed.fal_elevenlabs_audio_url = (
        "https://fal.media/detailed.mp3"
    )

    enriched = await enrich_plan_narration(plan, generator)
    await client.aclose()

    assert enriched == plan
    assert enriched is not plan


@pytest.mark.anyio
async def test_timestamp_metadata_sets_duration(tmp_path):
    def handler(request):
        return httpx.Response(
            200,
            json={
                "audio": {"url": "https://fal.media/voice.mp3"},
                "timestamps": {"character_end_times_seconds": [0.1, 0.25, 0.789]},
            },
        )

    generator, client = service(tmp_path, handler)
    asset = await generator.synthesize(
        step_id="one",
        variant="concise",
        voice_id="Rachel",
        text="Hello",
        speaking_rate=1.0,
    )
    await client.aclose()

    assert asset.duration_ms == 789


@pytest.mark.anyio
async def test_missing_key_and_bad_provider_response_are_typed_errors(tmp_path):
    no_key_service, no_key_client = service(
        tmp_path / "missing-key", lambda request: httpx.Response(200), api_key=None
    )
    with pytest.raises(NarrationConfigurationError, match="FAL_KEY"):
        await no_key_service.synthesize(
            step_id="one",
            variant="concise",
            voice_id="Rachel",
            text="Hello",
            speaking_rate=1.0,
        )
    await no_key_client.aclose()

    bad_service, bad_client = service(
        tmp_path / "bad-response", lambda request: httpx.Response(200, json={})
    )
    with pytest.raises(NarrationProviderError, match="hosted audio URL"):
        await bad_service.synthesize(
            step_id="one",
            variant="concise",
            voice_id="Rachel",
            text="Hello",
            speaking_rate=1.0,
        )
    await bad_client.aclose()


@pytest.mark.anyio
async def test_http_failure_does_not_expose_secret(tmp_path):
    generator, client = service(
        tmp_path, lambda request: httpx.Response(503, text="upstream unavailable")
    )

    with pytest.raises(NarrationProviderError, match="HTTP 503") as failure:
        await generator.synthesize(
            step_id="one",
            variant="concise",
            voice_id="Rachel",
            text="Hello",
            speaking_rate=1.0,
        )
    await client.aclose()

    assert "fal-secret" not in str(failure.value)
