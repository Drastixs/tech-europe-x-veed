import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { isRuntimeContractBundle } from "./runtime";
import { isDemoEnvelope, type RuntimeSession, type TutorialPlan } from "../overlay/protocol";

const fixturePath = fileURLToPath(
  new URL("../../../../contracts/fixtures/revolve-from-sketch-1.runtime-v1.json", import.meta.url)
);

describe("runtime contract", () => {
  it("accepts the canonical backend fixture", () => {
    const fixture: unknown = JSON.parse(readFileSync(fixturePath, "utf8"));

    expect(isRuntimeContractBundle(fixture)).toBe(true);
    const bundle = fixture as {
      contract_version: 1;
      tutorial_plan: unknown;
      state_snapshot: unknown;
      runtime_events: unknown;
      validation_outcome: unknown;
      error: unknown;
    };
    const runtimeSession = {
      contract_version: bundle.contract_version,
      session_id: (bundle.state_snapshot as { session_id: string }).session_id,
      state_snapshot: bundle.state_snapshot,
      runtime_events: bundle.runtime_events,
      validation_outcome: bundle.validation_outcome,
      error: bundle.error
    } as RuntimeSession;
    expect(isDemoEnvelope({
      version: 1,
      sequence: 1,
      sent_at: "2026-08-22T00:00:00Z",
      command: {
        type: "load_tutorial",
        plan: bundle.tutorial_plan as TutorialPlan,
        step: 1,
        runtime_session: runtimeSession
      }
    })).toBe(true);
  });

  it("rejects a bundle with an unknown validation outcome", () => {
    const fixture = JSON.parse(readFileSync(fixturePath, "utf8"));
    fixture.validation_outcome.outcome = "maybe_correct";

    expect(isRuntimeContractBundle(fixture)).toBe(false);
  });

  it("rejects an unknown runtime event", () => {
    const fixture = JSON.parse(readFileSync(fixturePath, "utf8"));
    fixture.runtime_events[0].event = "runtime.unrecognized";

    expect(isRuntimeContractBundle(fixture)).toBe(false);
  });
});
