from onshape_assist.observation import LearnerObservationContext


def test_observation_context_keeps_only_three_recent_screenshots():
    context = LearnerObservationContext()

    for timestamp in (1_000, 2_000, 3_000, 4_000):
        context.add_screenshot(f"data:image/png;base64,{timestamp}", timestamp)

    assert context.recent_screenshots == [
        "data:image/png;base64,2000",
        "data:image/png;base64,3000",
        "data:image/png;base64,4000",
    ]
    assert context.historical_summaries == [
        "Earlier learner observation at 1000ms was retained as history."
    ]


def test_observation_prompt_keeps_historical_context_textual():
    context = LearnerObservationContext(
        historical_summaries=["Earlier learner observation at 1000ms was retained as history."]
    )

    prompt = context.observation_prompt(
        step_goal="Open Revolve", expected_end_state="The Revolve dialog is open."
    )

    assert "Onshape API validation is the final authority" in prompt
    assert "Earlier learner observation at 1000ms" in prompt
