import React, { useMemo, useState } from "react";
import "./App.css";

export default function App() {
  const [file, setFile] = useState(null);
  const [docId, setDocId] = useState(null);
  const [jobId, setJobId] = useState(null);

  const [job, setJob] = useState(null);
  const [pipeline, setPipeline] = useState(null);
  const [resultText, setResultText] = useState("");
  const [resultJson, setResultJson] = useState(null);
  const [error, setError] = useState("");
  const [isUploading, setIsUploading] = useState(false);

  const progress = useMemo(() => {
    const p = job?.meta?.progress;
    return typeof p === "number" ? p : 0;
  }, [job]);

  async function uploadAndProcess() {
    setError("");
    setResultText("");
    setResultJson(null);
    setPipeline(null);
    setJob(null);
    setDocId(null);
    setJobId(null);

    if (!file) return;

    try {
      setIsUploading(true);

      const form = new FormData();
      form.append("file", file);

      const res = await fetch("/v1/documents", {
        method: "POST",
        body: form,
      });

      if (!res.ok) {
        const msg = await safeErrorMessage(res);
        throw new Error(msg || `Upload failed (${res.status})`);
      }

      const data = await res.json();
      setDocId(data.doc_id);
      setJobId(data.job_id);

      pollJob(data.job_id, data.doc_id);
    } catch (err) {
      setError(err.message || "Upload failed");
    } finally {
      setIsUploading(false);
    }
  }

  async function pollJob(jid, did) {
    let keepPolling = true;

    while (keepPolling) {
      try {
        const res = await fetch(`/v1/jobs/${jid}`);
        if (!res.ok) {
          const msg = await safeErrorMessage(res);
          throw new Error(msg || `Job status failed (${res.status})`);
        }

        const data = await res.json();
        setJob(data);

        try {
          const pRes = await fetch(`/v1/documents/${did}/pipeline`);
          if (pRes.ok) {
            const pData = await pRes.json();
            setPipeline(pData);
          }
        } catch {
          // ignore until ready
        }

        if (data.is_failed) {
          const details =
            data.exc_info?.split("\n").slice(-8).join("\n") ||
            "Job failed. Check worker logs.";
          setError(details);
          keepPolling = false;
          break;
        }

        if (data.is_finished) {
          keepPolling = false;

          try {
            const txtRes = await fetch(`/v1/documents/${did}/text`);
            if (txtRes.ok) {
              setResultText(await txtRes.text());
            }
          } catch {
            // ignore
          }

          try {
            const jsonRes = await fetch(`/v1/documents/${did}/result`);
            if (jsonRes.ok) {
              setResultJson(await jsonRes.json());
            }
          } catch {
            // ignore
          }

          try {
            const pRes = await fetch(`/v1/documents/${did}/pipeline`);
            if (pRes.ok) {
              const pData = await pRes.json();
              setPipeline(pData);
            }
          } catch {
            // ignore
          }

          break;
        }

        await sleep(1000);
      } catch (err) {
        setError(err.message || "Polling failed");
        keepPolling = false;
      }
    }
  }

  function handleFileChange(e) {
    const selected = e.target.files?.[0] ?? null;
    setFile(selected);
  }

  return (
    <div className="page">
      <div className="container">
        <header className="header">
          <h1 className="title">OCR Pipeline Viewer</h1>
          <p className="subtitle">
            Upload a document and watch it move through the OCR pipeline.
          </p>
        </header>

        <section className="card">
          <h2 className="section-title">1) Upload</h2>

          <div className="upload-row">
            <input type="file" onChange={handleFileChange} />
            <button
              onClick={uploadAndProcess}
              disabled={!file || isUploading}
              className="button"
            >
              {isUploading ? "Uploading..." : "Upload & Process"}
            </button>
          </div>

          {file && (
            <div className="small-info">
              <strong>Selected file:</strong> {file.name}
            </div>
          )}

          {error && (
            <div className="error-box">
              <strong>Error:</strong>
              <pre className="error-pre">{error}</pre>
            </div>
          )}
        </section>

        {(docId || jobId) && (
          <section className="card">
            <h2 className="section-title">2) Job Progress</h2>

            <div className="info-grid">
              <div>
                <strong>Document ID:</strong>
                <div className="mono">{docId || "-"}</div>
              </div>
              <div>
                <strong>Job ID:</strong>
                <div className="mono">{jobId || "-"}</div>
              </div>
              <div>
                <strong>Status:</strong>
                <div>{job?.status || "-"}</div>
              </div>
              <div>
                <strong>Stage:</strong>
                <div>{job?.meta?.stage || "-"}</div>
              </div>
            </div>

            <div style={{ marginTop: 16 }}>
              <div className="progress-outer">
                <div
                  className="progress-inner"
                  style={{ width: `${progress}%` }}
                />
              </div>
              <div className="progress-label">
                <span>{progress}%</span>
                <span>{job?.meta?.message || ""}</span>
              </div>
            </div>
          </section>
        )}

        {pipeline && (
          <section className="card">
            <h2 className="section-title">3) Pipeline Artifacts</h2>

            {pipeline.pages.length === 0 ? (
              <div>No pages available yet.</div>
            ) : (
              pipeline.pages.map((page) => (
                <div key={page.page} className="page-card">
                  <div className="page-header">
                    <h3 style={{ margin: 0 }}>Page {page.page}</h3>
                    <div className="badge">
                      source: <strong>{page.source}</strong>
                    </div>
                  </div>

                  {page.source === "native" ? (
                    <div className="native-box">
                      This page used native PDF text extraction, so OCR was skipped.
                    </div>
                  ) : (
                    <div className="stage-grid">
                      <ArtifactCard
                        title="Rendered"
                        src={
                          page.rendered
                            ? `/v1/documents/${docId}/pages/${page.rendered}`
                            : null
                        }
                      />

                      <ArtifactCard
                        title="Processed (Basic)"
                        src={
                          page.processed_basic
                            ? `/v1/documents/${docId}/processed/basic/${page.processed_basic}`
                            : null
                        }
                      />

                      <ArtifactCard
                        title="Processed (Strong)"
                        src={
                          page.processed_strong
                            ? `/v1/documents/${docId}/processed/strong/${page.processed_strong}`
                            : null
                        }
                      />
                    </div>
                  )}
                </div>
              ))
            )}
          </section>
        )}

        {resultText && (
          <section className="card">
            <h2 className="section-title">4) Extracted Text</h2>
            <pre className="text-box">{resultText}</pre>
          </section>
        )}

      </div>
    </div>
  );
}

function ArtifactCard({ title, src }) {
  return (
    <div className="artifact-card">
      <div className="artifact-title">{title}</div>
      {src ? (
        <img src={src} alt={title} className="image" />
      ) : (
        <div className="image-placeholder">Not ready yet</div>
      )}
    </div>
  );
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function safeErrorMessage(res) {
  try {
    const data = await res.json();
    return data.detail || JSON.stringify(data);
  } catch {
    return "";
  }
}