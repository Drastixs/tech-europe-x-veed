export type TutorialUrlValidation =
  | { ok: true; url: string }
  | { ok: false; message: string };

export function isOnshapeDocumentUrl(value: string | undefined): boolean {
  if (!value) return false;

  try {
    const url = new URL(value);
    return url.protocol === "https:" &&
      url.hostname === "cad.onshape.com" &&
      /^\/documents\/[^/]+/.test(url.pathname);
  } catch {
    return false;
  }
}

export function validateTutorialUrl(value: string): TutorialUrlValidation {
  const candidate = value.trim();
  if (!candidate) return { ok: false, message: "Paste a tutorial URL to continue." };

  try {
    const url = new URL(candidate);
    if (url.protocol !== "http:" && url.protocol !== "https:") {
      return { ok: false, message: "Use a valid http or https tutorial URL." };
    }
    return { ok: true, url: url.toString() };
  } catch {
    return { ok: false, message: "Enter a complete URL, including https://." };
  }
}
