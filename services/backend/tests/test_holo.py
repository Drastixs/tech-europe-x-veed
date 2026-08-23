from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from onshape_assist.holo import (
    HoloClient,
    HoloConfigurationError,
    HoloError,
    LocalizationContext,
)
from onshape_assist.observation import LearnerObservationContext


def test_holo_localizer_sends_structured_screenshot_request():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers["authorization"]
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"x":125,"y":750}'}}]},
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await HoloClient(
                api_key="h-secret",
                model="holo-test",
                base_url="https://holo.test/v1/",
                client=client,
            ).localize(
                "data:image/png;base64,c2NyZWVu",
                LocalizationContext(
                    target_description="Sketch 1 in the feature tree",
                    icon_description="A blue sketch glyph beside the Sketch 1 label",
                    target_label="Sketch 1",
                    ui_region="left feature tree",
                    semantic_action="Select Sketch 1",
                    step_goal="Open Revolve",
                ),
            )

    point = asyncio.run(run())

    assert point.model_dump() == {"x": 125, "y": 750}
    assert captured["authorization"] == "Bearer h-secret"
    assert captured["body"]["model"] == "holo-test"
    assert captured["body"]["temperature"] == 0.0
    assert captured["body"]["chat_template_kwargs"] == {"enable_thinking": False}
    assert captured["body"]["structured_outputs"]["json"]["additionalProperties"] is False
    content = captured["body"]["messages"][0]["content"]
    assert content[0]["image_url"]["url"].startswith("data:image/png;base64,")
    assert "Sketch 1" in content[1]["text"]
    assert "Icon appearance: A blue sketch glyph" in content[1]["text"]


def test_holo_localizer_requires_configuration_and_image_data():
    client = HoloClient(api_key="")
    with pytest.raises(HoloConfigurationError, match="HAI_API_KEY"):
        asyncio.run(
            client.localize(
                "data:image/png;base64,c2NyZWVu",
                LocalizationContext(target_description="Sketch 1"),
            )
        )

    client = HoloClient(api_key="secret")
    with pytest.raises(HoloError, match="image data URL"):
        asyncio.run(
            client.localize(
                "https://example.test/screen.png",
                LocalizationContext(target_description="Sketch 1"),
            )
        )


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, json={"choices": []}),
        httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"x":1200,"y":4}'}}]},
        ),
    ],
)
def test_holo_localizer_rejects_invalid_responses(response: httpx.Response):
    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: response)
        ) as client:
            await HoloClient(api_key="secret", client=client).localize(
                "data:image/png;base64,c2NyZWVu",
                LocalizationContext(target_description="Sketch 1"),
            )

    with pytest.raises(HoloError, match="invalid localization response"):
        asyncio.run(run())


def test_holo_localizer_reports_provider_status_without_leaking_body():
    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    401,
                    headers={"x-request-id": "req_123"},
                    json={"secret": "provider detail"},
                )
            )
        ) as client:
            await HoloClient(api_key="secret", client=client).localize(
                "data:image/png;base64,c2NyZWVu",
                LocalizationContext(target_description="Sketch 1"),
            )

    with pytest.raises(HoloError, match=r"401.*req_123") as error:
        asyncio.run(run())
    assert "provider detail" not in str(error.value)


def test_holo_observer_sends_no_more_than_three_images_and_requires_evidence():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "state": "progressing",
                                    "evidence": ["Sketch 1 is selected"],
                                    "suggested_next_action": "Open Revolve",
                                    "confidence": 0.8,
                                }
                            )
                        }
                    }
                ]
            },
        )

    async def run():
        context = LearnerObservationContext()
        for timestamp in (1_000, 2_000, 3_000, 4_000):
            context.add_screenshot(f"data:image/png;base64,{timestamp}", timestamp)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await HoloClient(api_key="h-secret", client=client).assess_learner_progress(
                context,
                step_goal="Open Revolve",
                expected_end_state="The Revolve dialog is open.",
            )

    assessment = asyncio.run(run())

    assert assessment.state == "progressing"
    content = captured["body"]["messages"][0]["content"]
    assert len([item for item in content if item["type"] == "image_url"]) == 3
    assert "Onshape API validation is the final authority" in content[-1]["text"]
