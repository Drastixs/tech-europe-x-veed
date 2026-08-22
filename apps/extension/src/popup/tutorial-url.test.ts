import { describe, expect, it } from "vitest";
import { isOnshapeDocumentUrl, validateTutorialUrl } from "./tutorial-url";

describe("popup tutorial URL helpers", () => {
  it("only enables tutorial upload on an Onshape document", () => {
    expect(isOnshapeDocumentUrl("https://cad.onshape.com/documents/abc/w/def/e/ghi")).toBe(true);
    expect(isOnshapeDocumentUrl("https://cad.onshape.com/documents")).toBe(false);
    expect(isOnshapeDocumentUrl("https://cad.onshape.com/help/Content/introduction.htm")).toBe(false);
    expect(isOnshapeDocumentUrl("https://example.com/documents/abc")).toBe(false);
  });

  it("normalizes valid tutorial URLs", () => {
    expect(validateTutorialUrl("  https://www.youtube.com/watch?v=abc  ")).toEqual({
      ok: true,
      url: "https://www.youtube.com/watch?v=abc"
    });
  });

  it("rejects incomplete and unsupported URLs", () => {
    expect(validateTutorialUrl("youtube.com/watch?v=abc")).toEqual({
      ok: false,
      message: "Enter a complete URL, including https://."
    });
    expect(validateTutorialUrl("file:///tmp/tutorial.mp4")).toEqual({
      ok: false,
      message: "Use a valid http or https tutorial URL."
    });
  });
});
