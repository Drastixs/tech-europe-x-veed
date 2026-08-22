import { useEffect, useId, useState, type FormEvent } from "react";
import { isOnshapeDocumentUrl, validateTutorialUrl } from "../../src/popup/tutorial-url";

type TabState = "checking" | "ready" | "blocked";
type SubmissionState =
  | { type: "idle" }
  | { type: "error"; message: string }
  | { type: "success"; url: string };

export function Popup() {
  const inputId = useId();
  const helpId = useId();
  const [tabState, setTabState] = useState<TabState>("checking");
  const [tutorialUrl, setTutorialUrl] = useState("");
  const [submission, setSubmission] = useState<SubmissionState>({ type: "idle" });

  useEffect(() => {
    let active = true;

    void browser.tabs
      .query({ active: true, currentWindow: true })
      .then(([tab]) => {
        if (active) setTabState(isOnshapeDocumentUrl(tab?.url) ? "ready" : "blocked");
      })
      .catch(() => {
        if (active) setTabState("blocked");
      });

    return () => {
      active = false;
    };
  }, []);

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (tabState !== "ready") return;

    const result = validateTutorialUrl(tutorialUrl);
    if (!result.ok) {
      setSubmission({ type: "error", message: result.message });
      return;
    }

    // Stub only. A later orchestration change will send this URL to the backend.
    setSubmission({ type: "success", url: result.url });
  };

  const openOnshape = () => {
    void browser.tabs.create({ url: "https://cad.onshape.com/documents" });
  };

  const isReady = tabState === "ready";

  return (
    <main className="popup-shell">
      <header className="popup-header">
        <div className="brand-mark" aria-hidden="true">
          <svg viewBox="0 0 24 24" focusable="false">
            <path d="M7.2 5.3 12 2.5l4.8 2.8v5.5L12 13.6l-4.8-2.8Z" />
            <path d="m7.2 13.2 4.8 2.7 4.8-2.7v5.5L12 21.5l-4.8-2.8Z" />
          </svg>
        </div>
        <div>
          <p className="eyebrow">Onshape Assist</p>
          <h1>Add a tutorial</h1>
        </div>
        <span className={`connection-state is-${tabState}`}>
          <span aria-hidden="true" />
          {tabState === "checking" ? "Checking" : isReady ? "Onshape ready" : "Onshape required"}
        </span>
      </header>

      {tabState === "blocked" ? (
        <section className="blocked-state" aria-labelledby="onshape-required-title">
          <div className="blocked-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" focusable="false">
              <path d="M12 3.25a8.75 8.75 0 1 0 0 17.5 8.75 8.75 0 0 0 0-17.5Z" />
              <path d="M8.5 12h7M12 8.5v7" />
            </svg>
          </div>
          <h2 id="onshape-required-title">Open an Onshape document first</h2>
          <p>The tutorial is attached to your active CAD workspace, so this step only works from an Onshape document.</p>
          <button className="secondary-button" type="button" onClick={openOnshape}>
            Open Onshape
            <span aria-hidden="true">↗</span>
          </button>
        </section>
      ) : (
        <form className="tutorial-form" onSubmit={submit} aria-busy={tabState === "checking"}>
          <label htmlFor={inputId}>Tutorial URL</label>
          <div className={`url-field ${submission.type === "error" ? "has-error" : ""}`}>
            <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
              <path d="M9.75 14.25 14.25 9.75M7.25 16.75l-1 .95a3.5 3.5 0 0 1-4.95-4.95l3.2-3.2A3.5 3.5 0 0 1 9.45 9M16.75 7.25l1-.95a3.5 3.5 0 1 1 4.95 4.95l-3.2 3.2a3.5 3.5 0 0 1-4.95.55" />
            </svg>
            <input
              id={inputId}
              type="url"
              inputMode="url"
              autoComplete="url"
              placeholder="https://youtube.com/watch?v=..."
              value={tutorialUrl}
              disabled={!isReady}
              aria-describedby={helpId}
              aria-invalid={submission.type === "error"}
              onChange={(event) => {
                setTutorialUrl(event.target.value);
                if (submission.type !== "idle") setSubmission({ type: "idle" });
              }}
            />
          </div>

          <div id={helpId} className="field-message" aria-live="polite">
            {submission.type === "error" ? (
              <span className="error-message">{submission.message}</span>
            ) : submission.type === "success" ? (
              <span className="success-message">Tutorial ready. Backend upload is stubbed for now.</span>
            ) : (
              <span>Paste a public video or tutorial link.</span>
            )}
          </div>

          <button className="primary-button" type="submit" disabled={!isReady || tutorialUrl.trim().length === 0}>
            <span>{submission.type === "success" ? "Tutorial added" : "Add tutorial"}</span>
            {submission.type === "success" ? (
              <svg viewBox="0 0 20 20" focusable="false" aria-hidden="true">
                <path d="m4.5 10.2 3.4 3.4 7.6-7.7" />
              </svg>
            ) : (
              <span aria-hidden="true">→</span>
            )}
          </button>
        </form>
      )}

      <footer>
        <span className="privacy-dot" aria-hidden="true" />
        The URL stays local in this stub.
      </footer>
    </main>
  );
}
