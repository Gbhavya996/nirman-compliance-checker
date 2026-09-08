import React, { useState, useRef, useCallback, useEffect } from 'react';

const API_BASE = '/api/inspections';

// ── Status helpers ────────────────────────────────────────────────────────────
const STATUS_META = {
  PASS:              { label: 'PASS',              cls: 'pass',    icon: '✓' },
  VARIANT_COMPLIANT: { label: 'VARIANT COMPLIANT', cls: 'pass',    icon: '✓' },
  FAIL:              { label: 'FAIL',              cls: 'fail',    icon: '✗' },
  WARNING:           { label: 'WARN',              cls: 'warning', icon: '⚠' },
  SKIP:              { label: 'SKIP',              cls: 'skip',    icon: '—' },
  VARIANT_MISMATCH:  { label: 'VARIANT MISMATCH',  cls: 'warning', icon: '⚠' },
  REVIEW_REQUIRED:   { label: 'REVIEW REQUIRED',   cls: 'warning', icon: '⚠' },
};
const OVERALL_META = {
  COMPLIANT:     { icon: '🛡️', label: 'Compliant',      cls: 'compliant' },
  NON_COMPLIANT: { icon: '🚨', label: 'Non-Compliant',  cls: 'non_compliant' },
  NEEDS_REVIEW:  { icon: '⚠️', label: 'Needs Review',   cls: 'needs_review' },
};
const HISTORY_OVERALL_ICON = { COMPLIANT: '🛡️', NON_COMPLIANT: '🚨', NEEDS_REVIEW: '⚠️' };

// ── Sub-components ────────────────────────────────────────────────────────────

function StatusBadge({ status }) {
  if (status === 'Physical Sample Required for Comparison' || status === 'SAMPLE_REQUIRED') {
    return <span className="badge badge--warning">⚠️ PHYSICAL SAMPLE REQUIRED</span>;
  }
  if (status === 'E-Commerce Declarations Available (Pending Physical Ground Truth Verification)') {
    return <span className="badge badge--warning">📋 PENDING PHYSICAL VERIFICATION</span>;
  }
  if (status === 'RULE_6_10_VIOLATION') {
    return <span className="badge badge--fail">🚨 RULE 6(10) VIOLATION</span>;
  }
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

function SummaryBanner({ summary, isPhysicalMissing }) {
  if (isPhysicalMissing) {
    return (
      <div className="summary-banner summary-banner--needs_review">
        <div className="summary-banner__icon">📋</div>
        <div>
          <div className="summary-banner__title">E-Commerce Listing Audit (Physical Sample Pending)</div>
          <div className="summary-banner__sub">Online disclosures audited under Rule 6(10). Upload physical sample image for full OCR compliance.</div>
          <div className="summary-stats">
            <span className="stat-pill"><span style={{ color: '#fbbf24' }}>ℹ</span> Physical Sample: Missing</span>
            <span className="stat-pill"><span style={{ color: 'var(--clr-pass)' }}>✓</span> Online Scraped: Active</span>
          </div>
        </div>
      </div>
    );
  }

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

function EnforcementActionCard({ activeEnf, hasPhysicalImage, onDownloadNotice, isDownloading }) {
  if (!activeEnf) return null;

  const sampleUploaded = hasPhysicalImage || Boolean(activeEnf.has_physical_image);
  const isPhysicalMissing = !sampleUploaded && activeEnf.physical_mrp == null;

  // Rule 6(10) E-Commerce Incomplete Disclosures Violation
  if (activeEnf.verdict?.includes('Rule 6(10)') || activeEnf.case_name?.includes('Rule 6(10)')) {
    return (
      <div className="enforcement-card enforcement-card--violation">
        <div className="enforcement-card__header">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: '1.3rem' }}>🚨</span>
            <span className="enforcement-card__badge" style={{ background: 'rgba(239, 68, 68, 0.2)', borderColor: 'rgba(239, 68, 68, 0.4)', color: '#fca5a5' }}>
              RULE 6(10) VIOLATION: INCOMPLETE E-COMMERCE DISCLOSURES
            </span>
          </div>
          <span style={{ fontSize: 'var(--text-xs)', color: '#fecdd3', fontWeight: 600 }}>
            Rule 6(10) LM-PC Rules 2011
          </span>
        </div>

        <div className="enforcement-card__directive">
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--clr-text-muted)', marginBottom: 2 }}>MANDATORY DIRECTIVE:</div>
          {activeEnf.action || 'Issue Statutory Notice to E-Commerce Platform / Seller under Rule 6(10) for incomplete digital disclosures.'}
        </div>

        <div className="enforcement-card__penalty">
          <span style={{ fontSize: '1.1rem' }}>⚖️</span>
          <div>
            <strong style={{ color: 'var(--clr-amber-300)' }}>Statutory Penalty Bracket: </strong>
            {activeEnf.penalty_bracket || 'Section 36 fine of ₹25,000 for first offence, up to ₹50,000 for second offence & Rule 6(10) show-cause'}
          </div>
        </div>

        {activeEnf.explanation && (
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--clr-text-secondary)', marginTop: 8, lineHeight: 1.5 }}>
            {activeEnf.explanation}
          </div>
        )}

        <div className="enforcement-card__actions">
          <button
            id="download-platform-notice-btn"
            className="btn-notice-download btn-notice-download--case-a"
            onClick={() => onDownloadNotice('CASE_A')}
            disabled={isDownloading}
          >
            {isDownloading ? 'Generating Notice…' : '📄 Download Platform Show-Cause Notice (Rule 6(10))'}
          </button>
        </div>
      </div>
    );
  }

  // Pending physical packaging sample verification
  if (isPhysicalMissing) {
    return (
      <div className="enforcement-card" style={{ background: 'rgba(245, 158, 11, 0.08)', border: '1px solid rgba(245, 158, 11, 0.35)', borderRadius: 'var(--radius-md)', padding: 'var(--sp-4)' }}>
        <div className="enforcement-card__header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: '1.2rem' }}>📋</span>
            <span className="enforcement-card__badge" style={{ background: 'rgba(245, 158, 11, 0.2)', borderColor: 'rgba(245, 158, 11, 0.4)', color: '#fbbf24' }}>
              E-COMMERCE AUDIT ONLY · PHYSICAL SAMPLE REQUIRED
            </span>
          </div>
          <span style={{ fontSize: 'var(--text-xs)', color: '#fbbf24', fontWeight: 600 }}>Rule 6(10) Screening</span>
        </div>
        <div className="enforcement-card__directive" style={{ color: '#fbbf24', marginBottom: 4 }}>
          ℹ️ Ground Truth Comparison Pending: Physical packaging label image is required to compare against online price.
        </div>
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--clr-text-secondary)', lineHeight: 1.5 }}>
          {activeEnf.explanation || 'E-Commerce mandatory disclosures are present online. Upload a retail package sample photo to test for Rule 18 Over-MRP violations.'}
        </div>
      </div>
    );
  }

  const isMismatch = activeEnf.status === 'VARIANT_MISMATCH' || activeEnf.status === 'REVIEW_REQUIRED';

  if (isMismatch) {
    return (
      <div className="enforcement-card enforcement-card--warning">
        <div className="enforcement-card__header">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: '1.2rem' }}>⚠️</span>
            <span className="enforcement-card__badge" style={{ background: 'rgba(230, 163, 32, 0.2)', borderColor: 'rgba(230, 163, 32, 0.4)', color: '#fde047' }}>
              SKU / VARIANT MISMATCH · REVIEW REQUIRED
            </span>
          </div>
          <span style={{ fontSize: 'var(--text-xs)', color: '#fde047', fontWeight: 600 }}>Rule 6(11) Protection</span>
        </div>
        <div className="enforcement-card__directive" style={{ color: 'var(--clr-warning)', marginBottom: 4 }}>
          ⚠️ Variant Size / SKU Mismatch: Over-MRP violation suppressed to prevent false enforcement.
        </div>
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--clr-text-secondary)', lineHeight: 1.5 }}>
          {activeEnf.explanation || 'Physical sample size does not match the online listing size. Please link the identical SKU variant URL or verify Unit Sale Price.'}
        </div>
      </div>
    );
  }

  const isViolation = activeEnf.is_violation;
  const isCaseA = activeEnf.case === 'CASE_A';
  const isCaseB = activeEnf.case === 'CASE_B';

  if (!isViolation) {
    return (
      <div className="enforcement-card enforcement-card--pass">
        <div className="enforcement-card__header">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: '1.2rem' }}>🛡️</span>
            <span className="enforcement-card__badge" style={{ background: 'rgba(34, 197, 94, 0.2)', borderColor: 'rgba(34, 197, 94, 0.4)', color: '#86efac' }}>
              RULE 18 / 6(11) COMPLIANT · NO VIOLATION
            </span>
          </div>
          <span style={{ fontSize: 'var(--text-xs)', color: '#86efac', fontWeight: 600 }}>LM-PC Rules 2011</span>
        </div>
        <div className="enforcement-card__directive" style={{ color: 'var(--clr-pass)', marginBottom: 4 }}>
          ✓ Compliant Pricing: Selling price / unit sale rate does not exceed declared baseline.
        </div>
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--clr-text-secondary)', lineHeight: 1.5 }}>
          {activeEnf.explanation || 'No statutory overcharging, tampering, or dual-MRP infractions detected. No notice required.'}
        </div>
      </div>
    );
  }

  return (
    <div className="enforcement-card enforcement-card--violation">
      <div className="enforcement-card__header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: '1.3rem' }}>🚨</span>
          <span className="enforcement-card__badge">
            {isCaseB ? 'CASE B: OFFLINE FRAUD / TAMPERING' : 'CASE A: ONLINE FRAUD'}
          </span>
        </div>
        <span style={{ fontSize: 'var(--text-xs)', color: '#fecdd3', fontWeight: 600 }}>
          {isCaseB ? 'Section 36 LM Act, 2009' : 'Section 18 & 36(1) LM-PC Rules'}
        </span>
      </div>

      <div className="enforcement-card__directive">
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--clr-text-muted)', marginBottom: 2 }}>MANDATORY DIRECTIVE:</div>
        {activeEnf.action || (isCaseB
          ? 'Issue Compounding Penalty Notice (₹25,000 to ₹1,00,000) against Retail Store for Price Smudging / Dual MRP.'
          : 'Generate Statutory Notice to E-Commerce Platform / Seller under Rule 6(10) / 6(11) & Section 36.'
        )}
      </div>

      <div className="enforcement-card__penalty">
        <span style={{ fontSize: '1.1rem' }}>⚖️</span>
        <div>
          <strong style={{ color: 'var(--clr-amber-300)' }}>Statutory Penalty Bracket: </strong>
          {activeEnf.penalty_bracket || (isCaseB
            ? 'Section 36 fine of ₹25,000 to ₹1,00,000 against Retail Store for Price Smudging / Dual MRP'
            : 'Section 36 fine of ₹25,000 for first offence, up to ₹50,000 for second offence & Rule 6(10) show-cause')}
        </div>
      </div>

      <div className="enforcement-card__actions">
        {isCaseB ? (
          <button
            id="generate-retailer-notice-btn"
            className="btn-notice-download btn-notice-download--case-b"
            onClick={() => onDownloadNotice('CASE_B')}
            disabled={isDownloading}
          >
            {isDownloading ? 'Generating Notice…' : '⚖️ Generate Retailer Compound Offence Notice'}
          </button>
        ) : (
          <button
            id="download-platform-notice-btn"
            className="btn-notice-download btn-notice-download--case-a"
            onClick={() => onDownloadNotice('CASE_A')}
            disabled={isDownloading}
          >
            {isDownloading ? 'Generating Notice…' : '📄 Download Platform Show-Cause Notice (PDF)'}
          </button>
        )}
      </div>
    </div>
  );
}

function ComparisonTable({ comparison, hasPhysicalImage, isRetailSample, onToggleRetailSample, onDownloadNotice, isDownloading }) {
  if (!comparison) return null;

  const activeEnf = (isRetailSample ? comparison.cases?.case_b : comparison.cases?.case_a) || comparison;
  const p_mrp = comparison.physical_mrp;
  const o_price = comparison.online_price;
  const sampleUploaded = hasPhysicalImage || Boolean(comparison.has_physical_image);
  const isPhysicalMissing = !sampleUploaded && (p_mrp == null || p_mrp === '');

  const isMismatch = activeEnf.status === 'VARIANT_MISMATCH' || activeEnf.status === 'REVIEW_REQUIRED';
  const deltaColor = isMismatch
    ? 'var(--clr-warning)'
    : activeEnf.is_violation ? 'var(--clr-fail)' : 'var(--clr-pass)';
  const verdictClass = isMismatch
    ? 'warning'
    : activeEnf.is_violation ? 'violation' : 'pass';

  const deltaDisplay = activeEnf.delta_str || (
    comparison.delta_pct != null
      ? `${comparison.delta_pct > 0 ? '+' : ''}${comparison.delta_pct}%`
      : '—'
  );

  let uspDisplay = '—';
  if (comparison.usp_comparison) {
    uspDisplay = comparison.usp_comparison;
  } else if (comparison.physical_usp != null && comparison.online_usp != null && comparison.usp_unit) {
    uspDisplay = `₹${Number(comparison.physical_usp).toFixed(2)}/${comparison.usp_unit} vs ₹${Number(comparison.online_usp).toFixed(2)}/${comparison.usp_unit}`;
  }

  const physUspDisplay = comparison.physical_usp_display || (
    comparison.physical_usp != null
      ? (typeof comparison.physical_usp === 'string'
          ? comparison.physical_usp
          : `₹ ${Number(comparison.physical_usp).toFixed(comparison.physical_usp < 1 ? 2 : 2)} / ${comparison.usp_unit || 'g'}`)
      : null
  );

  const onlUspDisplay = comparison.online_usp_display || (
    comparison.online_usp != null
      ? (typeof comparison.online_usp === 'string'
          ? comparison.online_usp
          : `₹ ${Number(comparison.online_usp).toFixed(comparison.online_usp < 1 ? 3 : 2)} / ${comparison.usp_unit || 'g'}`)
      : null
  );

  const rows = [
    [
      'Physical MRP (Label)',
      isPhysicalMissing ? (
        <span key="pm" style={{ color: 'var(--clr-warning)', fontWeight: 600 }}>
          Not Uploaded / Missing
        </span>
      ) : (
        p_mrp != null ? (comparison.physical_mrp_display || `₹ ${Number(p_mrp).toFixed(2)}`) : (
          <span key="pm_nd" style={{ color: 'var(--clr-warning)', fontWeight: 500 }}>
            Not Detected on Label
          </span>
        )
      )
    ],
    [
      'Online Price',
      o_price != null ? (comparison.online_price_display || `₹ ${Number(o_price).toFixed(2)}`) : '—'
    ],
    [
      'Physical Net Quantity',
      isPhysicalMissing ? (
        <span key="pq" style={{ color: 'var(--clr-warning)', fontWeight: 600 }}>
          Not Uploaded / Missing
        </span>
      ) : (
        comparison.physical_quantity || (
          <span key="pq_nd" style={{ color: 'var(--clr-text-muted)' }}>
            Not Detected
          </span>
        )
      )
    ],
    [
      'Online Net Quantity',
      comparison.online_quantity || '—'
    ],
    [
      'Physical USP',
      isPhysicalMissing ? 'N/A' : (physUspDisplay || 'N/A')
    ],
    ...(onlUspDisplay ? [['Online USP', onlUspDisplay]] : []),
    [
      'Normalized Unit Price (USP)',
      isPhysicalMissing ? 'N/A' : uspDisplay
    ],
    [
      'Delta',
      isPhysicalMissing ? (
        <span key="d" style={{ color: 'var(--clr-text-muted)', fontWeight: 700, fontFamily: 'var(--font-mono)' }}>
          N/A
        </span>
      ) : (
        <span key="d" style={{ color: deltaColor, fontWeight: 700, fontFamily: 'var(--font-mono)' }}>
          {deltaDisplay}
        </span>
      )
    ],
    [
      'Regulatory Finding',
      isPhysicalMissing ? (
        <span key="v" className="verdict-tag verdict-tag--warning" style={{ background: 'rgba(245, 158, 11, 0.15)', borderColor: 'rgba(245, 158, 11, 0.4)', color: '#fbbf24', fontWeight: 600 }}>
          PHYSICAL SAMPLE REQUIRED FOR COMPARISON
        </span>
      ) : (
        <span key="v" className={`verdict-tag verdict-tag--${verdictClass}`}>
          {activeEnf.verdict || (comparison.status === 'PASS' ? 'PASS - Compliant with Rule 18' : 'Under Review')}
        </span>
      )
    ],
    [
      'Source',
      comparison.source || '—'
    ],
    [
      'Status',
      <StatusBadge key="s" status={activeEnf.status || comparison.status} />
    ],
  ];

  return (
    <div className="comparison-wrap">
      {/* Sample Context Toggle */}
      <div className="sample-context-bar">
        <div className="sample-context-info">
          <div className="sample-context-title">Inspection Sample Mode</div>
          <div className="sample-context-desc">
            Toggle mode if sample was acquired from an offline retail shop to test for price tampering (Case B) vs e-commerce over-MRP (Case A).
          </div>
        </div>
        <label className={`retail-toggle-label ${isRetailSample ? 'retail-toggle-label--active' : ''}`}>
          <input
            id="comparison-retail-toggle"
            type="checkbox"
            checked={Boolean(isRetailSample)}
            onChange={(e) => onToggleRetailSample(e.target.checked)}
          />
          <span className="retail-toggle-text">
            {isRetailSample ? '🏪 Retail Store Physical Sample' : '🌐 Standard Online Inspection'}
          </span>
        </label>
      </div>

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
        {(activeEnf.explanation || comparison.explanation) && (
          <div style={{ padding: 'var(--sp-3) var(--sp-4)', fontSize: 'var(--text-xs)', color: 'var(--clr-text-muted)', borderTop: '1px solid var(--clr-border)' }}>
            {activeEnf.explanation || comparison.explanation}
          </div>
        )}
      </div>

      <EnforcementActionCard
        activeEnf={activeEnf}
        hasPhysicalImage={sampleUploaded}
        onDownloadNotice={onDownloadNotice}
        isDownloading={isDownloading}
      />
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

function CrossVerifyPanel({ cross, comparison, isRetailSample, onToggleRetailSample, onDownloadNotice, isDownloading }) {
  if (!cross) return null;

  const activeEnf = (isRetailSample ? comparison?.cases?.case_b : comparison?.cases?.case_a) || comparison;

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

      {/* Sample Context Toggle */}
      {comparison && (
        <div className="sample-context-bar" style={{ marginTop: 'var(--sp-3)' }}>
          <div className="sample-context-info">
            <div className="sample-context-title">Inspection Sample Mode</div>
            <div className="sample-context-desc">
              Toggle to test Retail Store Sample (Case B) vs E-Commerce Listing (Case A).
            </div>
          </div>
          <label className={`retail-toggle-label ${isRetailSample ? 'retail-toggle-label--active' : ''}`}>
            <input
              id="cross-retail-toggle"
              type="checkbox"
              checked={Boolean(isRetailSample)}
              onChange={(e) => onToggleRetailSample(e.target.checked)}
            />
            <span className="retail-toggle-text">
              {isRetailSample ? '🏪 Retail Store Physical Sample' : '🌐 Standard Online Inspection'}
            </span>
          </label>
        </div>
      )}

      <div className={`cross-overall cross-overall--${overallMeta.cls}`} style={{ marginTop: 'var(--sp-3)' }}>
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
              <th>Delta / Finding</th>
              <th>Verdict</th>
            </tr>
          </thead>
          <tbody>
            {(cross.rows || []).map((row) => {
              const vm = VERDICT_META[row.verdict] || VERDICT_META['UNAVAILABLE'];
              const isMRP = row.field === 'MRP';
              return (
                <tr key={row.field}>
                  <td style={{ fontWeight: 600, color: 'var(--clr-text-secondary)' }}>{row.field}</td>
                  <td style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)' }}>
                    {row.label_value ?? <em style={{ color: 'var(--clr-text-muted)' }}>—</em>}
                  </td>
                  <td style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)' }}>
                    {row.listing_value ?? <em style={{ color: 'var(--clr-text-muted)' }}>—</em>}
                  </td>
                  <td style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)' }}>
                    {isMRP && activeEnf?.delta_str ? (
                      <span style={{ color: activeEnf.is_violation ? 'var(--clr-fail)' : 'var(--clr-pass)', fontWeight: 700 }}>
                        {activeEnf.delta_str}
                      </span>
                    ) : (row.delta_str || '—')}
                  </td>
                  <td>
                    <span className={`cross-verdict cross-verdict--${vm.cls}`}>
                      {vm.icon} {isMRP && activeEnf ? (activeEnf.is_violation ? 'VIOLATION' : 'MATCH') : row.verdict}
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

      {comparison && (
        <EnforcementActionCard
          activeEnf={activeEnf}
          onDownloadNotice={onDownloadNotice}
          isDownloading={isDownloading}
        />
      )}
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
  const [isRetailSample, setIsRetailSample] = useState(false);
  const [dragging, setDragging]   = useState(false);

  // Process state
  const [loading, setLoading]     = useState(false);
  const [progress, setProgress]   = useState(0);
  const [result, setResult]       = useState(null);
  const [error, setError]         = useState(null);
  const [activeTab, setActiveTab] = useState('violations');
  const [downloadingNotice, setDownloadingNotice] = useState(false);

  // History
  const [historyOpen, setHistoryOpen] = useState(false);

  const inputRef = useRef(null);

  // ── Mode change ─────────────────────────────────────────────────────────────
  const handleModeChange = useCallback((newMode) => {
    setMode(newMode);
    setError(null);
    setResult(null);
    setProgress(0);
    // Only clear non-applicable input when explicitly switching between image and url
    // (Preserve file and URL when switching to or from 'both' mode)
    if (newMode === 'url' && mode === 'image') {
      setFile(null);
      setPreview(null);
      if (inputRef.current) inputRef.current.value = '';
    } else if (newMode === 'image' && mode === 'url') {
      setProductUrl('');
    }
  }, [mode]);

  // ── Full reset ──────────────────────────────────────────────────────────────
  const resetAll = useCallback(() => {
    setFile(null);
    setPreview(null);
    setProductUrl('');
    setIsRetailSample(false);
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
  const cleanUrl = productUrl.trim();
  const hasValidUrl = Boolean(cleanUrl && (cleanUrl.startsWith('http') || cleanUrl.includes('.')));
  const needsImage = mode === 'image' || mode === 'both';
  const needsUrl   = mode === 'url'   || mode === 'both';
  const canSubmit  = !loading &&
    (!needsImage || !!file) &&
    (!needsUrl   || hasValidUrl);

  // ── Statutory Notice Download ────────────────────────────────────────────────
  const handleDownloadNotice = async (caseType) => {
    setDownloadingNotice(true);
    try {
      const activeEnf = (isRetailSample ? result?.comparison?.cases?.case_b : result?.comparison?.cases?.case_a) || result?.comparison;
      const targetCase = caseType || activeEnf?.case || (isRetailSample ? 'CASE_B' : 'CASE_A');
      const payload = {
        case_type: targetCase,
        product_title: result?.listing?.product_title || result?.extracted?.manufacturer?.value || 'Packaged Commodity Sample',
        physical_mrp: result?.comparison?.physical_mrp,
        online_price: result?.comparison?.online_price,
        delta_rupees: activeEnf?.delta_rupees ?? result?.comparison?.delta_rupees,
        delta_pct: activeEnf?.delta_pct ?? result?.comparison?.delta_pct,
        domain_or_seller: result?.listing?.domain || result?.comparison?.source || 'E-Commerce Platform',
        retailer_name: 'Retail Store Premise',
        manufacturer: result?.extracted?.manufacturer?.value || '',
      };

      const resp = await fetch('/api/inspections/generate-notice', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!resp.ok) {
        throw new Error(`Server returned HTTP ${resp.status}`);
      }

      const blob = await resp.blob();
      const blobUrl = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = blobUrl;
      link.download = targetCase === 'CASE_A'
        ? 'Platform_Show_Cause_Notice_Section_36.pdf'
        : 'Retailer_Compound_Offence_Notice_Section_36.pdf';
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(blobUrl);
    } catch (err) {
      alert(`Error generating statutory notice: ${err.message}`);
    } finally {
      setDownloadingNotice(false);
    }
  };

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
      const rawUrl = productUrl.trim();
      const normalizedUrl = rawUrl && !/^https?:\/\//i.test(rawUrl) ? `https://${rawUrl}` : rawUrl;
      const effectiveMode = (file && normalizedUrl) ? 'both' : (file ? 'image' : 'url');

      form.append('mode', effectiveMode);
      form.append('is_retail_sample', isRetailSample ? 'true' : 'false');
      if (file) {
        form.append('image', file);
      }
      if (normalizedUrl) {
        form.append('url', normalizedUrl);
      }

      // Do NOT set headers: {'Content-Type': 'application/json'}; let browser set multipart/form-data with boundary
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
        if (json.is_retail_sample != null) {
          setIsRetailSample(Boolean(json.is_retail_sample));
        }
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
    if (rec.is_retail_sample != null) {
      setIsRetailSample(Boolean(rec.is_retail_sample));
    }
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

          {/* Retail Store Physical Sample Mode Toggle */}
          <div className="sample-context-bar" style={{ marginTop: 'var(--sp-3)', background: 'rgba(30, 41, 59, 0.45)' }}>
            <div className="sample-context-info">
              <div className="sample-context-title">Sample Context</div>
              <div className="sample-context-desc">
                Flag if this sample is from an offline retail shop to test for price tampering / dual MRP (Case B).
              </div>
            </div>
            <label className={`retail-toggle-label ${isRetailSample ? 'retail-toggle-label--active' : ''}`}>
              <input
                id="form-retail-sample-checkbox"
                type="checkbox"
                checked={isRetailSample}
                onChange={(e) => setIsRetailSample(e.target.checked)}
              />
              <span className="retail-toggle-text">{isRetailSample ? '🏪 Retail Store Physical Sample' : '🌐 Standard Online Inspection'}</span>
            </label>
          </div>

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

      {result && !result.unable_to_verify && (() => {
        const isPhysicalMissing = result.has_physical_image !== undefined
          ? !result.has_physical_image
          : Boolean(
              result.mode === 'url' ||
              result.is_catalog_thumbnail ||
              result.ocr?.raw_text?.includes('No physical sample image uploaded')
            );

        return (
          <div className="animate-fadeIn">
            <SummaryBanner summary={result.summary} isPhysicalMissing={isPhysicalMissing} />

            <div className="results-grid">
              {/* Left: Evidence + Readability */}
              <div className="evidence-panel">
                <div className="glass-card" style={{ padding: 'var(--sp-5)' }}>
                  <SectionTitle icon="📸">Visual Evidence</SectionTitle>

                  {result.image_b64 ? (
                    <div className="evidence-panel__image-wrap">
                      <img src={`data:${result.image_mime};base64,${result.image_b64}`} alt="Product visual" />
                      {result.is_catalog_thumbnail || isPhysicalMissing ? (
                        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--clr-amber-300)', textAlign: 'center', marginTop: 'var(--sp-2)' }}>
                          🌐 E-Commerce catalog thumbnail preview (No physical sample uploaded)
                        </div>
                      ) : (
                        <div style={{ fontSize: 'var(--text-xs)', color: '#34d399', textAlign: 'center', marginTop: 'var(--sp-2)', fontWeight: 500 }}>
                          📸 Physical Packaging Sample Image (OCR Processed)
                        </div>
                      )}
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
                  isPhysicalMissing ? (
                    <div className="empty-ocr-card" style={{
                      padding: 'var(--sp-6)',
                      background: 'rgba(230, 163, 32, 0.07)',
                      border: '1px dashed rgba(230, 163, 32, 0.4)',
                      borderRadius: 'var(--radius-md)',
                      textAlign: 'center',
                      margin: 'var(--sp-3) 0'
                    }}>
                      <div style={{ fontSize: '2.4rem', marginBottom: 'var(--sp-2)' }}>📷</div>
                      <div style={{ fontSize: 'var(--text-base)', fontWeight: 600, color: 'var(--clr-amber-300)', marginBottom: 'var(--sp-2)' }}>
                        No Physical Packaging Sample Image Uploaded
                      </div>
                      <div style={{ fontSize: 'var(--text-sm)', color: 'var(--clr-text-primary)', marginBottom: 'var(--sp-2)', fontWeight: 500 }}>
                        Upload physical packaging image to run OCR label verification.
                      </div>
                      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--clr-text-muted)', maxWidth: 520, margin: '0 auto', lineHeight: 1.6 }}>
                        E-Commerce URL inspections evaluate digital mandatory declarations under Rule 6(10). Physical label OCR checks (font heights, manufacturing date, retail packaging MRP, consumer care) require an uploaded package sample photo.
                      </div>
                    </div>
                  ) : (
                    <div className="violation-list">
                      {result.violations && result.violations.length > 0 ? (
                        result.violations.map((v, i) => (
                          <ViolationCard key={`${v.field}-${i}`} item={v} index={i} />
                        ))
                      ) : (
                        <div style={{ color: 'var(--clr-text-muted)', padding: 'var(--sp-4)', textAlign: 'center' }}>
                          No rule violations detected.
                        </div>
                      )}
                    </div>
                  )
                )}

                {/* Price comparison tab */}
                {activeTab === 'comparison' && (
                  <div>
                    <SectionTitle icon="💰">Online vs. Physical Price</SectionTitle>
                    <ComparisonTable
                      comparison={result.comparison}
                      hasPhysicalImage={Boolean(result.has_physical_image)}
                      isRetailSample={isRetailSample}
                      onToggleRetailSample={setIsRetailSample}
                      onDownloadNotice={handleDownloadNotice}
                      isDownloading={downloadingNotice}
                    />
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
                            <td><StatusBadge status={val.found ? 'PASS' : (isPhysicalMissing ? 'SKIP' : 'FAIL')} /></td>
                            <td style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)', color: val.found ? 'var(--clr-amber-200)' : (isPhysicalMissing ? 'var(--clr-text-muted)' : 'var(--clr-fail)') }}>
                              {val.display ?? (val.value != null ? String(val.value) : (
                                isPhysicalMissing
                                  ? <em style={{ color: 'var(--clr-text-muted)' }}>Not Uploaded / Missing (No physical sample)</em>
                                  : <em style={{ color: 'var(--clr-text-muted)' }}>NOT DETECTED / REVIEW REQUIRED</em>
                              ))}
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
                  <CrossVerifyPanel
                    cross={result.cross_verification}
                    comparison={result.comparison}
                    isRetailSample={isRetailSample}
                    onToggleRetailSample={setIsRetailSample}
                    onDownloadNotice={handleDownloadNotice}
                    isDownloading={downloadingNotice}
                  />
                </div>
              )}
            </div>
          </div>
        </div>
      );
    })()}
    </>
  );
}
