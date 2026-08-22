"""Server-side Onshape Part Studio state monitoring and rollback."""

from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field

from .config import load_backend_env


class OnshapeError(RuntimeError):
    """Raised when Onshape does not return a usable API response."""


class OnshapeTarget(BaseModel):
    document_id: str = Field(min_length=1)
    workspace_id: str = Field(min_length=1)
    element_id: str = Field(min_length=1)

    @classmethod
    def from_document_url(cls, document_url: str) -> OnshapeTarget:
        match = _DOCUMENT_URL_RE.match(document_url)
        if match is None:
            raise OnshapeError("expected an Onshape Part Studio workspace URL")
        return cls(**match.groupdict())


class FeatureState(BaseModel):
    rollback_index: int
    fingerprint: str
    feature_ids: tuple[str, ...]
    feature_types: tuple[str, ...]


class GeometryState(BaseModel):
    part_count: int
    fingerprint: str
    part_ids: tuple[str, ...]


class OnshapeSnapshot(BaseModel):
    target: OnshapeTarget
    microversion_id: str
    features: FeatureState
    geometry: GeometryState


class RestoreResult(BaseModel):
    outcome: Literal["restored", "concurrent_edit", "restore_mismatch"]
    snapshot: OnshapeSnapshot


class ValidationResult(BaseModel):
    outcome: Literal[
        "correct",
        "wrong_tool",
        "no_committed_change",
        "unexpected_geometry",
        "concurrent_edit",
    ]
    snapshot: OnshapeSnapshot
    added_feature_types: tuple[str, ...] = ()


class OnshapeClient:
    """Minimal authenticated client for the stable Part Studio state endpoints.

    API keys are used only by this backend process. Basic authentication is
    supported by Onshape for local integrations over HTTPS; callers can point
    ``ONSHAPE_BASE_URL`` at an enterprise host when needed.
    """

    def __init__(
        self,
        access_key: str,
        secret_key: str,
        *,
        base_url: str = "https://cad.onshape.com/api",
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(
            auth=(access_key, secret_key),
            headers={"Accept": "application/json;charset=UTF-8"},
            timeout=10.0,
            follow_redirects=True,
        )

    @classmethod
    def from_env(cls) -> OnshapeClient:
        load_backend_env()
        access_key = os.environ.get("ONSHAPE_ACCESS_KEY")
        secret_key = os.environ.get("ONSHAPE_SECRET_KEY")
        if not access_key or not secret_key:
            raise OnshapeError("ONSHAPE_ACCESS_KEY and ONSHAPE_SECRET_KEY must be configured")
        return cls(
            access_key,
            secret_key,
            base_url=os.environ.get("ONSHAPE_BASE_URL", "https://cad.onshape.com/api"),
        )

    def close(self) -> None:
        self._client.close()

    def snapshot(self, target: OnshapeTarget) -> OnshapeSnapshot:
        return OnshapeSnapshot(
            target=target,
            microversion_id=self._current_microversion(target),
            features=self._feature_state(target),
            geometry=self._geometry_state(target),
        )

    def restore_baseline(
        self,
        baseline: OnshapeSnapshot,
        *,
        expected_microversion_id: str,
    ) -> RestoreResult:
        current_microversion_id = self._current_microversion(baseline.target)
        if current_microversion_id != expected_microversion_id:
            return RestoreResult(
                outcome="concurrent_edit",
                snapshot=self.snapshot(baseline.target),
            )

        self._request(
            "POST",
            self._part_studio_path(baseline.target, "/features/rollback"),
            json={"rollbackIndex": baseline.features.rollback_index},
        )
        restored = self.snapshot(baseline.target)
        outcome: Literal["restored", "restore_mismatch"] = (
            "restored" if _matches_baseline(restored, baseline) else "restore_mismatch"
        )
        return RestoreResult(outcome=outcome, snapshot=restored)

    def validate_attempt(
        self,
        baseline: OnshapeSnapshot,
        *,
        expected_feature_type: str,
        expected_microversion_id: str | None = None,
    ) -> ValidationResult:
        current = self.snapshot(baseline.target)
        if expected_microversion_id and current.microversion_id != expected_microversion_id:
            return ValidationResult(outcome="concurrent_edit", snapshot=current)
        if current.microversion_id == baseline.microversion_id:
            return ValidationResult(outcome="no_committed_change", snapshot=current)

        added_feature_types = tuple(
            feature_type
            for feature_type in current.features.feature_types
            if feature_type not in baseline.features.feature_types
        )
        if expected_feature_type in added_feature_types:
            return ValidationResult(
                outcome="correct",
                snapshot=current,
                added_feature_types=added_feature_types,
            )
        if added_feature_types:
            return ValidationResult(
                outcome="wrong_tool",
                snapshot=current,
                added_feature_types=added_feature_types,
            )
        return ValidationResult(
            outcome="unexpected_geometry",
            snapshot=current,
            added_feature_types=added_feature_types,
        )

    def _current_microversion(self, target: OnshapeTarget) -> str:
        payload = self._request(
            "GET",
            f"/documents/d/{target.document_id}/w/{target.workspace_id}/currentmicroversion",
        )
        value = payload.get("microversionId") or payload.get("id")
        if not isinstance(value, str) or not value:
            raise OnshapeError("current microversion response did not include an id")
        return value

    def _feature_state(self, target: OnshapeTarget) -> FeatureState:
        payload = self._request("GET", self._part_studio_path(target, "/features"))
        features = payload.get("features")
        if not isinstance(features, list):
            raise OnshapeError("feature-list response did not include features")
        normalized = [
            {
                "featureId": str(feature.get("featureId", "")),
                "featureType": str(feature.get("featureType", "")),
                "name": str(feature.get("name", "")),
                "suppressed": bool(feature.get("suppressed", False)),
            }
            for feature in features
            if isinstance(feature, dict)
        ]
        return FeatureState(
            rollback_index=int(payload.get("rollbackIndex", -1)),
            fingerprint=_fingerprint(normalized),
            feature_ids=tuple(item["featureId"] for item in normalized),
            feature_types=tuple(item["featureType"] for item in normalized),
        )

    def _geometry_state(self, target: OnshapeTarget) -> GeometryState:
        payload = self._request("GET", self._part_studio_path(target, "", endpoint="parts"))
        parts = payload if isinstance(payload, list) else payload.get("parts")
        if not isinstance(parts, list):
            raise OnshapeError("parts response did not include a part list")
        normalized = [
            {
                "partId": str(part.get("partId", "")),
                "name": str(part.get("name", "")),
                "bodyType": str(part.get("bodyType", "")),
                "isClosed": bool(part.get("isClosed", False)),
            }
            for part in parts
            if isinstance(part, dict)
        ]
        return GeometryState(
            part_count=len(normalized),
            fingerprint=_fingerprint(normalized),
            part_ids=tuple(item["partId"] for item in normalized),
        )

    def _part_studio_path(
        self,
        target: OnshapeTarget,
        suffix: str,
        *,
        endpoint: str = "partstudios",
    ) -> str:
        return (
            f"/{endpoint}/d/{target.document_id}/w/{target.workspace_id}/e/{target.element_id}{suffix}"
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any] | list[Any]:
        try:
            response = self._client.request(method, f"{self._base_url}{path}", **kwargs)
        except httpx.RequestError as exc:
            raise OnshapeError(f"Onshape {method} {path} could not be reached") from exc
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OnshapeError(f"Onshape {method} {path} failed: {exc.response.status_code}") from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise OnshapeError(f"Onshape {method} {path} returned invalid JSON") from exc
        if not isinstance(payload, (dict, list)):
            raise OnshapeError(f"Onshape {method} {path} returned an unexpected JSON type")
        return payload


def _fingerprint(value: list[dict[str, Any]]) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _matches_baseline(current: OnshapeSnapshot, baseline: OnshapeSnapshot) -> bool:
    return (
        current.features.fingerprint == baseline.features.fingerprint
        and current.geometry.fingerprint == baseline.geometry.fingerprint
    )


_DOCUMENT_URL_RE = re.compile(
    r"^https://[^/]+/documents/(?P<document_id>[^/]+)/w/(?P<workspace_id>[^/]+)/e/(?P<element_id>[^/?#]+)"
)
