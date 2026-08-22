from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from onshape_assist.analysis import fal
from onshape_assist.analysis.models import AnalysisRequest, AnalysisResult
from onshape_assist.analysis.pipeline import AnalysisError, analyze_video_async

Direction = Literal["left", "right"]
CommandType = Literal[
    "show",
    "hide",
    "move",
    "click",
    "navigate",
    "load_tutorial",
    "arm_takeover",
    "disarm_takeover",
]


class TutorialStep(BaseModel):
    step_id: str = Field(min_length=1)
    text: str = Field(min_length=1)


class DemoCommand(BaseModel):
    type: CommandType
    x: Annotated[int | None, Field(ge=0)] = None
    y: Annotated[int | None, Field(ge=0)] = None
    duration_ms: Annotated[int | None, Field(ge=0, le=10_000)] = None
    direction: Direction | None = None
    steps: list[TutorialStep] | None = None
    step: Annotated[int | None, Field(ge=1)] = None


class DemoEnvelope(BaseModel):
    version: Literal[1] = 1
    sequence: int
    sent_at: str
    command: DemoCommand


class Relay:
    def __init__(self) -> None:
        self._sequence = 0
        self._clients: set[WebSocket] = set()
        self.last_envelope: DemoEnvelope | None = None

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._clients.add(websocket)
        if self.last_envelope:
            await websocket.send_json(self.last_envelope.model_dump())

    def disconnect(self, websocket: WebSocket) -> None:
        self._clients.discard(websocket)

    async def publish(self, command: DemoCommand) -> DemoEnvelope:
        self._sequence += 1
        envelope = DemoEnvelope(
            sequence=self._sequence,
            sent_at=datetime.now(UTC).isoformat(),
            command=command,
        )
        self.last_envelope = envelope
        disconnected: list[WebSocket] = []
        for client in self._clients:
            try:
                await client.send_json(envelope.model_dump())
            except RuntimeError:
                disconnected.append(client)
        for client in disconnected:
            self.disconnect(client)
        return envelope

    @property
    def client_count(self) -> int:
        return len(self._clients)


relay = Relay()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.relay = relay
    yield


app = FastAPI(title="Onshape Assist Relay", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, int | str]:
    return {"status": "ok", "clients": relay.client_count}


@app.post("/commands", response_model=DemoEnvelope)
async def command(command: DemoCommand) -> DemoEnvelope:
    try:
        normalized = normalize_command(command)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return await relay.publish(normalized)


@app.post("/analyze", response_model=AnalysisResult)
async def analyze(
    request: AnalysisRequest,
    gemini_model: str = fal.DEFAULT_GEMINI_MODEL,
    enrichment: bool = True,
) -> AnalysisResult:
    if not os.environ.get("FAL_KEY"):
        raise HTTPException(status_code=503, detail="FAL_KEY is not configured on the server")
    try:
        return await analyze_video_async(
            request,
            gemini_model=gemini_model,
            with_enrichment=enrichment,
        )
    except AnalysisError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.websocket("/ws/extension")
async def extension_socket(websocket: WebSocket) -> None:
    origin = websocket.headers.get("origin")
    allowed_origin = (
        origin is None
        or origin == "https://cad.onshape.com"
        or origin.startswith("chrome-extension://")
    )
    if not allowed_origin:
        await websocket.close(code=1008, reason="Origin not allowed")
        return
    await relay.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        relay.disconnect(websocket)


def normalize_command(command: DemoCommand) -> DemoCommand:
    if command.type == "move" and (command.x is None or command.y is None):
        raise ValueError("move requires x and y")
    if command.type == "navigate" and command.direction is None:
        raise ValueError("navigate requires direction")
    if command.type == "load_tutorial":
        if not command.steps:
            raise ValueError("load_tutorial requires at least one step")
        if command.step is not None and command.step > len(command.steps):
            raise ValueError("load_tutorial step exceeds the number of steps")
    return command
