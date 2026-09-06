import React, { useState, useRef, useCallback, useEffect } from 'react';

const API_BASE = '/api/inspections';

// ── Status helpers ────────────────────────────────────────────────────────────
const STATUS_META = {
  PASS:    { label: 'PASS',    cls: 'pass',    icon: '✓' },
  FAIL:    { label: 'FAIL',    cls: 'fail',    icon: '✗' },
  WARNING: { label: 'WARN',    cls: 'warning', icon: '⚠' },
  SKIP:    { label: 'SKIP',    cls: 'skip',    icon: '—' },
};
const OVERALL_META = {
  COMPLIANT:     { icon: '🛡️', label: 'Compliant',      cls: 'compliant' },
  NON_COMPLIANT: { icon: '🚨', label: 'Non-Compliant',  cls: 'non_compliant' },
  NEEDS_REVIEW:  { icon: '⚠️', label: 'Needs Review',   cls: 'needs_review' },
};
const HISTORY_OVERALL_ICON = { COMPLIANT: '🛡️', NON_COMPLIANT: '🚨', NEEDS_REVIEW: '⚠️' };

// ── Sub-components ────────────────────────────────────────────────────────────

function StatusBadge({ status }) {
  const m = STATUS_META[status] || STATUS_META.SKIP;
  return <span className={`badge badge--${m.cls}`}>{m.icon} {m.label}</span>;
}

function SectionTitle({ icon, children }) {
  return (
    <h2 className="section-title">
      <span className="section-title__dot" />
      {icon && <span>{icon}</span>}
      {children}
    </h2>
  );
}

function SummaryBanner({ summary }) {
  const m = OVERALL_META[summary.overall] || OVERALL_META.NEEDS_REVIEW;
  return (
    <div className={`summary-banner summary-banner--${m.cls.toLowerCase()}`}>
      <div className="summary-banner__icon">{m.icon}</div>
      <div>
        <div className="summary-banner__title">{m.label}</div>
        <div className="summary-banner__sub">{summary.total_checks} rule checks completed</div>
        <div className="summary-stats">
          <span className="stat-pill"><span style={{ color: 'var(--clr-pass)' }}>✓</span>{summary.pass_count} passed</span>
          <span className="stat-pill"><span style={{ color: 'var(--clr-fail)' }}>✗</span>{summary.fail_count} failed</span>
          <span className="stat-pill"><span style={{ color: 'var(--clr-warning)' }}>⚠</span>{summary.warning_count} warnings</span>
        </div>
      </div>
    </div>
  );
}

function ViolationCard({ item, index }) {
  const cls = (item.status || 'skip').toLowerCase();
  return (
    <div className={`violation-card violation-card--${cls} animate-fadeInUp`} style={{ animationDelay: `${index * 50}ms` }}>
      <div className="violation-card__header">
        <span className="violation-card__field">{item.field}</span>
        <StatusBadge status={item.status} />
      </div>
      <div className="violation-card__rule">{item.rule_ref}</div>
      <div className="violation-card__explanation">{item.explanation}</div>
      {item.value !== null && item.value !== undefined && (
        <div className="violation-card__value">Detected: {String(item.value)}</div>
      )}
    </div>
  );
}

function ComparisonTable({ comparison }) {
  if (!comparison) return null;
  const rows = [
    ['Physical MRP (Label)', comparison.physical_mrp != null ? `₹ ${comparison.physical_mrp}` : '—'],
    ['Online Price',         comparison.online_price != null ? `₹ ${comparison.online_price}` : '—'],
    ['Delta',                comparison.delta_pct != null ? `${comparison.delta_pct > 0 ? '+' : ''}${comparison.delta_pct}%` : '—'],
    ['Source',               comparison.source || '—'],
    ['Status',               <StatusBadge key="s" status={comparison.status} />],
  ];
  return (
    <div className="comparison-table-wrap">
      <table className="comparison-table">
        <thead><tr><th>Parameter</th><th>Value</th></tr></thead>
        <tbody>
          {rows.map(([param, val]) => (
            <tr key={param}>
              <td style={{ color: 'var(--clr-text-secondary)', fontWeight: 500 }}>{param}</td>
              <td>{val}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {comparison.explanation && (
        <div style={{ padding: 'var(--sp-3) var(--sp-4)', fontSize: 'var(--text-xs)', color: 'var(--clr-text-muted)', borderTop: '1px solid var(--clr-border)' }}>
          {comparison.explanation}
        </div>
      )}
    </div>
  );
}

function ReadabilityRow({ readability }) {
  if (!readability) return null;
  return (
    <div className="readability-row">
      <div>
        <div style={{ fontWeight: 600, marginBottom: 2 }}>Label Readability</div>
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--clr-text-muted)' }}>LM-PC Schedule II font height check</div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-4)' }}>
        {readability.estimated_min_mm != null && (
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--clr-text-muted)' }}>Min height</div>
            <div style={{ fontWeight: 700, fontFamily: 'var(--font-mono)' }}>{readability.estimated_min_mm} mm</div>
          </div>
        )}
        <StatusBadge status={readability.status} />
      </div>
    </div>
  );
}

// ── Cross-Verification Panel ──────────────────────────────────────────────────
const VERDICT_META = {
  'MATCH':                                    { icon: '✅', cls: 'pass' },
  'POTENTIAL DISCREPANCY / REVIEW REQUIRED':  { icon: '🚨', cls: 'fail' },
  'UNAVAILABLE':                              { icon: '—',  cls: 'skip' },
};

function CrossVerifyPanel({ cross }) {
  if (!cross) return null;

  if (!cross.scraped) {
    return (
      <div className="cross-verify-error">
        <div style={{ fontSize: '1.5rem', marginBottom: 'var(--sp-2)' }}>🔗</div>
        <div style={{ fontWeight: 600, marginBottom: 'var(--sp-1)' }}>Listing data unavailable</div>
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--clr-text-muted)' }}>
          {cross.error || 'The product page could not be scraped.'}
        </div>
      </div>
    );
  }

  const overallMeta = {
    ALL_MATCH:       { icon: '✅', label: 'All fields match',              cls: 'pass'    },
    HAS_DISCREPANCY: { icon: '🚨', label: 'Discrepancies detected',        cls: 'fail'    },
    UNAVAILABLE:     { icon: '—',  label: 'Insufficient data to compare',  cls: 'skip'    },
  }[cross.overall] || { icon: '—', label: 'Unknown', cls: 'skip' };

  return (
    <div>
      {cross.listing_title && (
        <div className="listing-title-card">
          <span style={{ color: 'var(--clr-text-muted)', fontSize: 'var(--text-xs)' }}>Listing found on {cross.domain}</span>
          <div style={{ fontWeight: 600, marginTop: 'var(--sp-1)' }}>{cross.listing_title}</div>
        </div>
      )}

      <div className={`cross-overall cross-overall--${overallMeta.cls}`}>
        <span style={{ fontSize: '1.2rem' }}>{overallMeta.icon}</span>
        {overallMeta.label}
      </div>

      <div className="comparison-table-wrap" style={{ marginTop: 'var(--sp-3)' }}>
        <table className="comparison-table">
          <thead>
            <tr>
              <th>Field</th>
              <th>Label (OCR)</th>
              <th>Online Listing</th>
              <th>Verdict</th>
            </tr>
          </thead>
          <tbody>
            {(cross.rows || []).map((row) => {
              const vm = VERDICT_META[row.verdict] || VERDICT_META['UNAVAILABLE'];
              return (
                <tr key={row.field}>
                  <td style={{ fontWeight: 600, color: 'var(--clr-text-secondary)' }}>{row.field}</td>
                  <td style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)' }}>
                    {row.label_value ?? <em style={{ color: 'var(--clr-text-muted)' }}>—</em>}
                  </td>
                  <td style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)' }}>
                    {row.listing_value ?? <em style={{ color: 'var(--clr-text-muted)' }}>—</em>}
                  </td>
                  <td>
                    <span className={`cross-verdict cross-verdict--${vm.cls}`}>
                      {vm.icon} {row.verdict}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {(cross.rows || []).some(r => r.note) && (
          <div style={{ padding: 'var(--sp-3) var(--sp-4)', borderTop: '1px solid var(--clr-border)' }}>
            {cross.rows.filter(r => r.note).map(r => (
              <div key={r.field} style={{ fontSize: 'var(--text-xs)', color: 'var(--clr-text-muted)', marginBottom: 'var(--sp-1)' }}>
                <strong style={{ color: 'var(--clr-text-secondary)' }}>{r.field}:</strong> {r.note}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ── History Sidebar ───────────────────────────────────────────────────────────
function HistorySidebar({ open, onClose, onLoadRecord }) {
  const [items, setItems]   = useState([]);
  const [loading, setLoading] = useState(false);

  const fetchHistory = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`${API_BASE}/history`);
      const d = await r.json();
      setItems(d.history || []);
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { if (open) fetchHistory(); }, [open, fetchHistory]);

  const clearHistory = async () => {
    if (!window.confirm('Clear all scan history?')) return;
    await fetch(`${API_BASE}/history`, { method: 'DELETE' });
    setItems([]);
  };

  const handleLoad = async (id) => {
    try {
      const r = await fetch(`${API_BASE}/history/${id}`);
      const d = await r.json();
      if (d.result) {
        onLoadRecord(d.result);
        onClose();
      }
    } catch (e) {
      alert('Failed to load inspection.');
    }
  };

  const fmtDate = (iso) => {
    try {
      return new Date(iso).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
    } catch { return iso; }
  };

  if (!open) return null;

  return (
    <>
      <div className="sidebar-backdrop" onClick={onClose} />
      <aside className="history-sidebar animate-slideInLeft">
        <div className="history-sidebar__header">
          <span style={{ fontSize: '1.1rem', fontWeight: 700 }}>📋 Scan History</span>
          <button className="sidebar-close" onClick={onClose} title="Close">✕</button>
        </div>

        <div className="history-sidebar__body">
          {loading && <div className="history-empty">Loading…</div>}
          {!loading && items.length === 0 && (
            <div className="history-empty">No scans yet. Run your first inspection!</div>
          )}
          {!loading && items.map(item => (
            <button key={item.id} className="history-item" onClick={() => handleLoad(item.id)}>
              <div className="history-item__meta">
                <span className="history-item__icon">
                  {HISTORY_OVERALL_ICON[item.overall] || '❓'}
                </span>
                <div>
                  <div className="history-item__date">{fmtDate(item.ts)}</div>
                  <div className="history-item__mode">
                    {item.mode === 'both' ? '🔀 Image + URL' : item.mode === 'url' ? '🔗 URL' : '📷 Image'}
                  </div>
                </div>
              </div>
              <div className={`history-item__badge badge--${(item.overall || 'skip').toLowerCase().replace('_', '-')}`}>
                {item.pass_count}✓ {item.fail_count}✗ {item.warning_count}⚠
              </div>
            </button>
          ))}
        </div>

        {items.length > 0 && (
          <div className="history-sidebar__footer">
            <button className="btn-danger-sm" onClick={clearHistory}>🗑 Clear History</button>
          </div>
        )}
      </aside>
    </>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function InspectionDetails() {
  // Input state
  const [mode, setMode]           = useState('image'); // 'image' | 'url' | 'both'
  const [file, setFile]           = useState(null);
  const [preview, setPreview]     = useState(null);
  const [productUrl, setProductUrl] = useState('');
  const [dragging, setDragging]   = useState(false);

  // Process state
  const [loading, setLoading]     = useState(false);
  const [progress, setProgress]   = useState(0);
  const [result, setResult]       = useState(null);
  const [error, setError]         = useState(null);
  const [activeTab, setActiveTab] = useState('violations');

  // History
  const [historyOpen, setHistoryOpen] = useState(false);

  const inputRef = useRef(null);

  // ── Mode change ─────────────────────────────────────────────────────────────
  const handleModeChange = useCallback((newMode) => {
    setMode(newMode);
    setError(null);
    setResult(null);
    setProgress(0);
    // Clear the non-applicable input to prevent cross-contamination
    if (newMode === 'url') {
      setFile(null);
      setPreview(null);
      if (inputRef.current) inputRef.current.value = '';
    } else if (newMode === 'image') {
      setProductUrl('');
    }
  }, []);

  // ── Full reset ──────────────────────────────────────────────────────────────
  const resetAll = useCallback(() => {
    setFile(null);
    setPreview(null);
    setProductUrl('');
    setResult(null);
    setError(null);
    setProgress(0);
    setLoading(false);
    setActiveTab('violations');
    if (inputRef.current) inputRef.current.value = '';
  }, []);

  // ── File handling ───────────────────────────────────────────────────────────
  const handleFile = useCallback((f) => {
    if (!f) return;
    setFile(f);
    setResult(null);
    setError(null);
    setProgress(0);
    setPreview(URL.createObjectURL(f));
  }, []);

  const onInputChange = (e) => { if (e.target.files?.[0]) handleFile(e.target.files[0]); };
  const onDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    if (e.dataTransfer.files?.[0]) handleFile(e.dataTransfer.files[0]);
  };
  const clearImage = () => {
    setFile(null);
    setPreview(null);
    if (inputRef.current) inputRef.current.value = '';
  };

  // ── Validation ──────────────────────────────────────────────────────────────
  const needsImage = mode === 'image' || mode === 'both';
  const needsUrl   = mode === 'url'   || mode === 'both';
  const canSubmit  = !loading &&
    (!needsImage || !!file) &&
    (!needsUrl   || productUrl.trim().startsWith('http'));

  // ── Analysis ────────────────────────────────────────────────────────────────
  const analyze = async () => {
    if (!canSubmit) return;
    setLoading(true);
    setError(null);
    setResult(null);

    let tick = 0;
    const timer = setInterval(() => {
      tick += 1;
      setProgress(Math.min(10 + tick * 6, 88));
    }, 400);

    try {
      const form = new FormData();
      form.append('mode', mode);
      if ((mode === 'image' || mode === 'both') && file) {
        form.append('image', file);
      }
      if ((mode === 'url' || mode === 'both') && productUrl.trim()) {
        form.append('url', productUrl.trim());
      }

      const resp = await fetch(`${API_BASE}/analyze`, { method: 'POST', body: form });
      clearInterval(timer);
      setProgress(100);

      const json = await resp.json();
      if (!resp.ok || json.success === false) {
        setError(json.error || 'Server error');
        setResult(null);
      } else {
        setError(null);
        setResult(json);
        // Auto-select cross-verification tab when both modes used
        if (json.mode === 'both' && json.cross_verification?.scraped) {
          setActiveTab('crossverify');
        }
      }
    } catch (err) {
      clearInterval(timer);
      setError(`Network error: ${err.message}. Is the backend running on port 5000?`);
    } finally {
      setLoading(false);
    }
  };

  // Load a history record directly
  const loadHistoryRecord = (rec) => {
    setResult(rec);
    setActiveTab('violations');
    setPreview(rec.image_b64 && rec.image_mime
      ? `data:${rec.image_mime};base64,${rec.image_b64}` : null);
  };

  // ── Tab list for results ────────────────────────────────────────────────────
  const resultTabs = [
    { id: 'violations', label: `🏛 Rule Violations (${result?.violations?.length ?? 0})` },
    { id: 'comparison', label: '💰 Price Comparison' },
    { id: 'extracted',  label: '📋 Extracted Fields' },
    ...(result?.cross_verification ? [{ id: 'crossverify', label: '🔀 Cross-Verification' }] : []),
  ];

  // ── Render ──────────────────────────────────────────────────────────────────
  return (
    <>
      {/* History toggle button */}
      <button
        id="history-toggle-btn"
        className="history-toggle-btn"
        onClick={() => setHistoryOpen(true)}
        title="Scan History"
      >
        📋 History
      </button>

      <HistorySidebar
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
        onLoadRecord={loadHistoryRecord}
      />

      {/* ── Hero ── */}
      {!result && (
        <div className="hero animate-fadeInUp">
          <h1 className="hero__title">Nirman: Legal Metrology<br />Compliance Checker</h1>
          <p className="hero__desc">
            Scan product packaging or paste an e-commerce product URL to detect
            mandatory declarations, identify potential compliance issues, and generate
            an evidence-based compliance report.
          </p>
        </div>
      )}

      {/* ── Input area ── */}
      {!result && (
        <div style={{ maxWidth: 720, margin: '0 auto' }}>
          {/* Mode tabs */}
          <div className="mode-tabs">
            {[
              { id: 'image', icon: '📷', label: 'Image Only' },
              { id: 'url',   icon: '🔗', label: 'URL Only' },
              { id: 'both',  icon: '🔀', label: 'Image + URL' },
            ].map(m => (
              <button
                key={m.id}
                id={`mode-tab-${m.id}`}
                className={`mode-tab ${mode === m.id ? 'mode-tab--active' : ''}`}
                onClick={() => handleModeChange(m.id)}
              >
                {m.icon} {m.label}
              </button>
            ))}
          </div>

          {/* Image zone */}
          {(mode === 'image' || mode === 'both') && (
            !preview ? (
              <div
                className={`upload-zone ${dragging ? 'upload-zone--active' : ''}`}
                onClick={() => inputRef.current?.click()}
                onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
                onDragLeave={() => setDragging(false)}
                onDrop={onDrop}
                role="button" tabIndex={0} aria-label="Upload product image"
                onKeyDown={(e) => e.key === 'Enter' && inputRef.current?.click()}
                style={{ marginBottom: mode === 'both' ? 'var(--sp-4)' : 0 }}
              >
                <div className="upload-zone__icon">📦</div>
                <div className="upload-zone__title">Drop a product label image here</div>
                <div className="upload-zone__hint">or click to browse · JPEG, PNG, WebP, BMP — max 20 MB</div>
                <input
                  ref={inputRef} id="image-upload" type="file"
                  className="upload-zone__input"
                  accept="image/jpeg,image/png,image/webp,image/bmp"
                  onChange={onInputChange}
                />
              </div>
            ) : (
              <div className="preview-wrap" style={{ marginBottom: mode === 'both' ? 'var(--sp-4)' : 0, position: 'relative', display: 'inline-block', width: '100%' }}>
                <img src={preview} alt="Product label preview" style={{ width: '100%', maxHeight: 280, objectFit: 'contain', borderRadius: 8 }} />
                <button className="preview-clear" onClick={clearImage} title="Remove image">✕</button>
              </div>
            )
          )}

          {/* URL input */}
          {(mode === 'url' || mode === 'both') && (
            <div className="url-input-wrap">
              <div className="url-input-icon">🔗</div>
              <input
                id="product-url-input"
                className="url-input"
                type="url"
                placeholder="Paste product URL (Amazon, Flipkart, BigBasket, etc.)"
                value={productUrl}
                onChange={e => setProductUrl(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && canSubmit && analyze()}
              />
              {productUrl && (
                <button className="url-input-clear" onClick={() => setProductUrl('')} title="Clear URL">✕</button>
              )}
            </div>
          )}

          {/* Action buttons */}
          <div style={{ display: 'flex', gap: 'var(--sp-3)', alignItems: 'center', marginTop: 'var(--sp-4)', justifyContent: 'center' }}>
            <button id="analyze-btn" className="btn-primary" onClick={analyze} disabled={!canSubmit}>
              {loading ? <><span className="spinner" /> Analysing…</> : <><span>🔍</span> Run Compliance Check</>}
            </button>
            {(file || productUrl) && (
              <button className="btn-secondary" onClick={resetAll}>Reset</button>
            )}
          </div>

          {loading && (
            <div style={{ width: '100%', marginTop: 'var(--sp-4)' }}>
              <div className="progress-bar-wrap">
                <div className="progress-bar-fill" style={{ width: `${progress}%` }} />
              </div>
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--clr-text-muted)', marginTop: 6, textAlign: 'center' }}>
                {mode === 'url' ? 'Fetching listing…' : mode === 'both' ? 'Running OCR · Scraping listing · Cross-verifying…' : 'Running OCR · Extracting fields · Evaluating rules…'}
              </div>
            </div>
          )}

          {error && (
            <div className="error-toast" style={{ marginTop: 'var(--sp-4)' }}>
              <span style={{ fontSize: '1.2rem' }}>⚠️</span>
              <div>{error}</div>
            </div>
          )}
        </div>
      )}

      {/* ── Results ── */}
      {result && result.unable_to_verify && (
        <div className="animate-fadeIn" style={{ maxWidth: 720, margin: '0 auto' }}>
          <div className="summary-banner summary-banner--needs_review" style={{ marginBottom: 'var(--sp-4)' }}>
            <div className="summary-banner__icon">🔒</div>
            <div>
              <div className="summary-banner__title">Unable to Verify This Product</div>
              <div className="summary-banner__sub" style={{ marginTop: 'var(--sp-1)' }}>
                {result.error || 'Access restrictions or anti-bot verification prevented fetching this listing.'}
              </div>
            </div>
          </div>

          <div className="glass-card" style={{ padding: 'var(--sp-6)', textAlign: 'center' }}>
            <div style={{ fontSize: '2.5rem', marginBottom: 'var(--sp-3)' }}>🛡️</div>
            <h3 style={{ fontSize: '1.25rem', fontWeight: 600, marginBottom: 'var(--sp-2)' }}>
              Protected E-Commerce Listing
            </h3>
            <p style={{ color: 'var(--clr-text-secondary)', fontSize: 'var(--text-sm)', lineHeight: 1.6, maxWidth: 540, margin: '0 auto var(--sp-5)' }}>
              Websites like Amazon and Flipkart deploy automated bot challenges (CAPTCHAs) that restrict automated inspection.
              To check Legal Metrology compliance for this product, please upload a photo of the product package directly.
            </p>

            <div style={{ display: 'flex', gap: 'var(--sp-3)', justifyContent: 'center', flexWrap: 'wrap' }}>
              <button
                className="btn-primary"
                onClick={() => {
                  resetAll();
                  handleModeChange('image');
                }}
              >
                📷 Upload Package Image Instead
              </button>
              <button
                className="btn-secondary"
                onClick={resetAll}
              >
                ↩ Try Another URL
              </button>
            </div>
          </div>
        </div>
      )}

      {result && !result.unable_to_verify && (
        <div className="animate-fadeIn">
          <SummaryBanner summary={result.summary} />

          <div className="results-grid">
            {/* Left: Evidence + Readability */}
            <div className="evidence-panel">
              <div className="glass-card" style={{ padding: 'var(--sp-5)' }}>
                <SectionTitle icon="📸">Visual Evidence</SectionTitle>

                {result.image_b64 ? (
                  <div className="evidence-panel__image-wrap">
                    <img src={`data:${result.image_mime};base64,${result.image_b64}`} alt="Uploaded product label" />
                  </div>
                ) : (
                  <div className="evidence-no-image">
                    <div style={{ fontSize: '2rem' }}>🔗</div>
                    <div style={{ fontSize: 'var(--text-sm)', color: 'var(--clr-text-muted)', marginTop: 'var(--sp-2)' }}>
                      URL-only scan — no image provided
                    </div>
                    {result.listing?.url && (
                      <a href={result.listing.url} target="_blank" rel="noopener noreferrer" className="listing-link">
                        View listing ↗
                      </a>
                    )}
                  </div>
                )}

                {result.ocr?.raw_text && (
                  <div style={{ marginTop: 'var(--sp-4)' }}>
                    <div style={{ fontSize: 'var(--text-xs)', color: 'var(--clr-text-muted)', marginBottom: 'var(--sp-2)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                      Raw OCR Output
                      {result.ocr.ocr_engine && <span style={{ marginLeft: 8, fontWeight: 400, textTransform: 'none' }}>({result.ocr.ocr_engine})</span>}
                    </div>
                    <div className="ocr-textbox">{result.ocr.raw_text || '(No text extracted)'}</div>
                  </div>
                )}

                <button
                  className="btn-secondary"
                  style={{ marginTop: 'var(--sp-4)', width: '100%', justifyContent: 'center' }}
                  onClick={resetAll}
                >
                  ↩ New Inspection
                </button>
              </div>

              {/* Readability */}
              <div className="glass-card" style={{ padding: 'var(--sp-5)' }}>
                <SectionTitle icon="🔡">Readability Check</SectionTitle>
                <ReadabilityRow readability={result.readability} />
                {result.readability?.explanation && (
                  <div style={{ fontSize: 'var(--text-xs)', color: 'var(--clr-text-muted)', marginTop: 'var(--sp-3)', lineHeight: 1.6 }}>
                    {result.readability.explanation}
                  </div>
                )}
              </div>

              {/* Listing info (URL mode) */}
              {result.listing && (
                <div className="glass-card" style={{ padding: 'var(--sp-5)' }}>
                  <SectionTitle icon="🔗">Listing Info</SectionTitle>
                  <div style={{ fontSize: 'var(--text-xs)', color: 'var(--clr-text-muted)' }}>Source: {result.listing.domain || '—'}</div>
                  {result.listing.product_title && (
                    <div style={{ fontWeight: 600, marginTop: 'var(--sp-2)' }}>{result.listing.product_title}</div>
                  )}
                  {result.listing.error && (
                    <div style={{ color: 'var(--clr-fail)', fontSize: 'var(--text-xs)', marginTop: 'var(--sp-2)' }}>
                      ⚠ {result.listing.error}
                    </div>
                  )}
                  {result.listing.url && (
                    <a href={result.listing.url} target="_blank" rel="noopener noreferrer" className="listing-link">
                      Open listing ↗
                    </a>
                  )}
                </div>
              )}
            </div>

            {/* Right: Tabs */}
            <div className="glass-card" style={{ padding: 'var(--sp-5)' }}>
              <div className="tabs">
                {resultTabs.map(tab => (
                  <button
                    key={tab.id}
                    id={`tab-${tab.id}`}
                    className={`tab-btn ${activeTab === tab.id ? 'tab-btn--active' : ''}`}
                    onClick={() => setActiveTab(tab.id)}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>

              {/* Violations tab */}
              {activeTab === 'violations' && (
                <div className="violation-list">
                  {result.violations.map((v, i) => (
                    <ViolationCard key={`${v.field}-${i}`} item={v} index={i} />
                  ))}
                </div>
              )}

              {/* Price comparison tab */}
              {activeTab === 'comparison' && (
                <div>
                  <SectionTitle icon="💰">Online vs. Physical Price</SectionTitle>
                  <ComparisonTable comparison={result.comparison} />
                </div>
              )}

              {/* Extracted fields tab */}
              {activeTab === 'extracted' && (
                <div className="comparison-table-wrap">
                  <table className="comparison-table">
                    <thead><tr><th>Field</th><th>Status</th><th>Extracted Value</th></tr></thead>
                    <tbody>
                      {Object.entries(result.extracted).map(([key, val]) => (
                        <tr key={key}>
                          <td style={{ color: 'var(--clr-text-secondary)', fontWeight: 500, textTransform: 'capitalize' }}>
                            {key.replace(/_/g, ' ')}
                          </td>
                          <td><StatusBadge status={val.found ? 'PASS' : 'FAIL'} /></td>
                          <td style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)', color: val.found ? 'var(--clr-amber-200)' : 'var(--clr-fail)' }}>
                            {val.display ?? (val.value != null ? String(val.value) : <em style={{ color: 'var(--clr-text-muted)' }}>NOT DETECTED / REVIEW REQUIRED</em>)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {/* Cross-verification tab */}
              {activeTab === 'crossverify' && (
                <div>
                  <SectionTitle icon="🔀">Online Listing vs. Package</SectionTitle>
                  <CrossVerifyPanel cross={result.cross_verification} />
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
