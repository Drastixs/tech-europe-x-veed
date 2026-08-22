import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { isRuntimeContractBundle } from "./runtime";

const fixturePath = fileURLToPath(
  new URL("../../../../contracts/fixtures/revolve-from-sketch-1.runtime-v1.json", import.meta.url)
);

describe("runtime contract", () => {
  it("accepts the canonical backend fixture", () => {
    const fixture: unknown = JSON.parse(readFileSync(fixturePath, "utf8"));

    expect(isRuntimeContractBundle(fixture)).toBe(true);
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
