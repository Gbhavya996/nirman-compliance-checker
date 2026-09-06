import React from 'react';
import './index.css';
import InspectionDetails from './pages/InspectionDetails';

export default function App() {
  return (
    <div className="app-shell">
      {/* ── Header ───────────────────────────────────────────────── */}
      <header className="header">
        <div className="header__brand">
          <div className="header__logo" aria-hidden="true">⚖️</div>
          <div>
            <div className="header__title">Nirman: Legal Metrology Compliance Checker</div>
          </div>
        </div>

      </header>

      {/* ── Main ─────────────────────────────────────────────────── */}
      <main className="main-content" id="main-content">
        <InspectionDetails />
      </main>

      {/* ── Footer ───────────────────────────────────────────────── */}
      <footer className="footer">
        <p>
          Nirman · Legal Metrology (Packaged Commodities) Rules, 2011
        </p>
        <p style={{ marginTop: '0.25rem' }}>
          For official inspections, always cross-reference with a licensed
          Legal Metrology Officer.
        </p>
      </footer>
    </div>
  );
}
