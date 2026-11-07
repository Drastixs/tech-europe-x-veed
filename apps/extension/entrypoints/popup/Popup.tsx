import { useEffect, useId, useState, type FormEvent } from "react";
import type { TutorialCreationResult } from "../../src/popup/tutorial-api";
import type { SavedTutorial } from "../../src/popup/tutorial-library";
import { isOnshapeDocumentUrl, validateTutorialUrl } from "../../src/popup/tutorial-url";

type TabState = "checking" | "ready" | "blocked";
type SubmissionState =
  | { type: "idle" }
  | { type: "loading" }
  | { type: "error"; message: string }
  | { type: "success"; tutorialId: string };
type ReplayState =
  | { type: "idle" }
  | { type: "loading"; tutorialId: string }
  | { type: "error"; tutorialId: string; message: string };

type TutorialCreationResponse = TutorialCreationResult & { tutorial?: SavedTutorial };

const sourceLabel = (videoUrl: string) => {
  try {
    return new URL(videoUrl).hostname.replace(/^www\./, "");
  } catch {
    return "Video tutorial";
  }
};

export function Popup() {
  const inputId = useId();
  const helpId = useId();
  const [tabState, setTabState] = useState<TabState>("checking");
  const [tutorialUrl, setTutorialUrl] = useState("");
  const [submission, setSubmission] = useState<SubmissionState>({ type: "idle" });
  const [tutorials, setTutorials] = useState<SavedTutorial[]>([]);
  const [libraryLoading, setLibraryLoading] = useState(true);
  const [replay, setReplay] = useState<ReplayState>({ type: "idle" });

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

  useEffect(() => {
    let active = true;
    void browser.runtime.sendMessage({ channel: "onshape-assist", type: "tutorial.list" })
      .then((response: { ok?: boolean; tutorials?: SavedTutorial[] } | undefined) => {
        if (active && response?.ok && Array.isArray(response.tutorials)) {
          setTutorials(response.tutorials);
        }
      })
      .finally(() => {
        if (active) setLibraryLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (tabState !== "ready") return;

    const result = validateTutorialUrl(tutorialUrl);
    if (!result.ok) {
      setSubmission({ type: "error", message: result.message });
      return;
    }

    setSubmission({ type: "loading" });
    let response: TutorialCreationResponse | undefined;
    try {
      response = (await browser.runtime.sendMessage({
        channel: "onshape-assist",
        type: "tutorial.create",
        videoUrl: result.url
      })) as TutorialCreationResponse | undefined;
    } catch {
      setSubmission({
        type: "error",
        message: "The extension background service is unavailable. Reopen the extension and try again."
      });
      return;
    }
    if (!response?.ok) {
      setSubmission({
        type: "error",
        message: response?.message ?? "The tutorial could not be prepared. Try again."
      });
      return;
    }
    if (response.tutorial) {
      setTutorials((current) => [
        response.tutorial as SavedTutorial,
        ...current.filter((tutorial) => tutorial.tutorialId !== response?.tutorial?.tutorialId)
      ]);
    }
    setSubmission({ type: "success", tutorialId: response.tutorialId });
  };

  const replayTutorial = async (tutorialId: string) => {
    if (tabState !== "ready") return;
    setReplay({ type: "loading", tutorialId });
    try {
      const response = await browser.runtime.sendMessage({
        channel: "onshape-assist",
        type: "tutorial.replay",
        tutorialId
      }) as { ok?: boolean; message?: string } | undefined;
      setReplay(response?.ok
        ? { type: "idle" }
        : { type: "error", tutorialId, message: response?.message ?? "The tutorial could not be replayed." });
    } catch {
      setReplay({ type: "error", tutorialId, message: "The extension background service is unavailable." });
    }
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
        <form
          className="tutorial-form"
          onSubmit={(event) => void submit(event)}
          aria-busy={tabState === "checking" || submission.type === "loading"}
        >
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
              disabled={!isReady || submission.type === "loading"}
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
            ) : submission.type === "loading" ? (
              <span>Analyzing the video and preparing narration. Keep Onshape open.</span>
            ) : submission.type === "success" ? (
              <span className="success-message">Tutorial ready in Onshape.</span>
            ) : (
              <span>Paste a public video or tutorial link.</span>
            )}
          </div>

          <button
            className="primary-button"
            type="submit"
            disabled={
              !isReady || tutorialUrl.trim().length === 0 || submission.type === "loading"
            }
          >
            <span>
              {submission.type === "loading"
                ? "Preparing tutorial…"
                : submission.type === "success"
                  ? "Tutorial added"
                  : "Add tutorial"}
            </span>
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

      <section className="tutorial-library" aria-labelledby="saved-tutorials-title" aria-busy={libraryLoading}>
        <div className="section-heading">
          <h2 id="saved-tutorials-title">Your tutorials</h2>
          {!libraryLoading && tutorials.length > 0 ? <span>{tutorials.length}</span> : null}
        </div>
        {libraryLoading ? (
          <div className="library-skeleton" aria-label="Loading saved tutorials">
            <span />
            <span />
          </div>
        ) : tutorials.length === 0 ? (
          <p className="empty-library">Analyzed tutorials will appear here, ready to replay.</p>
        ) : (
          <ul className="tutorial-list">
            {tutorials.map((tutorial) => {
              const isReplaying = replay.type === "loading" && replay.tutorialId === tutorial.tutorialId;
              const replayError = replay.type === "error" && replay.tutorialId === tutorial.tutorialId
                ? replay.message
                : null;
              return (
                <li key={tutorial.tutorialId}>
                  <div className="tutorial-details">
                    <strong>{tutorial.title}</strong>
                    <span>{sourceLabel(tutorial.videoUrl)} · {tutorial.plan.steps.length} {tutorial.plan.steps.length === 1 ? "step" : "steps"}</span>
                    {replayError ? <small role="alert">{replayError}</small> : null}
                  </div>
                  <button
                    className="replay-button"
                    type="button"
                    disabled={!isReady || replay.type === "loading"}
                    onClick={() => void replayTutorial(tutorial.tutorialId)}
                    aria-label={`Replay ${tutorial.title}`}
                    title={isReady ? `Replay ${tutorial.title}` : "Open an Onshape document to replay"}
                  >
                    <svg viewBox="0 0 20 20" focusable="false" aria-hidden="true">
                      <path d="M7.2 5.5 14 10l-6.8 4.5Z" />
                    </svg>
                    {isReplaying ? "Starting…" : "Replay"}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <footer>
        <span className="privacy-dot" aria-hidden="true" />
        The local relay prepares and sends guidance to this Onshape tab.
      </footer>
    </main>
  );
}
