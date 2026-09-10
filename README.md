# 🚀 NIRMAN — Legal Metrology Compliance Checker

<p align="center">
  <b>AI-assisted compliance verification for physical products and e-commerce listings.</b>
</p>

<p align="center">

![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)
![React](https://img.shields.io/badge/React.js-Frontend-61DAFB?logo=react)
![Flask](https://img.shields.io/badge/Flask-Backend-black?logo=flask)
![OpenCV](https://img.shields.io/badge/OpenCV-Computer%20Vision-red?logo=opencv)
![EasyOCR](https://img.shields.io/badge/EasyOCR-OCR-green)
![Tailwind](https://img.shields.io/badge/Tailwind-CSS-06B6D4?logo=tailwindcss)

</p>

---

## 💡 What is NIRMAN?

**NIRMAN** is an AI-assisted Legal Metrology compliance verification system designed to help inspectors analyze product packaging and e-commerce listings under the **Legal Metrology (Packaged Commodities) Rules, 2011**.

It combines:

**Computer Vision + OCR + Data Extraction + Unit Normalization + Rule-Based Compliance Checking**

to transform unstructured product information into structured compliance results.

### The Problem

Checking packaged commodities manually requires inspectors to:

- Read information from physical packaging
- Verify mandatory declarations (MRP, Net Quantity, Best Before date, etc.)
- Check pricing and unit details
- Compare physical and online information
- Identify inconsistencies
- Record evidence
- Prepare inspection reports

When performed manually across large product catalogs, this workflow becomes **time-consuming, repetitive, and difficult to maintain consistently**.

### The Solution

NIRMAN automates this workflow by:

1. **Extracting** information from packaging images using OCR
2. **Fetching** e-commerce listing data from URLs
3. **Normalizing** units for fair comparison
4. **Applying** compliance rules deterministically
5. **Generating** evidence-backed reports

---

## ✨ Key Features

| Feature | Description |
|---------|-------------|
| 📦 **Visual Evidence Extraction** | Upload product packaging images → Preprocess → Extract text with OCR → Identify product fields → Preserve evidence |
| 🌐 **Online Listing Verification** | Analyze e-commerce URLs → Retrieve listing data → Extract prices and details → Compare with physical packaging |
| ⚖️ **Rule-Based Compliance Engine** | Apply deterministic compliance rules (Rule 6, Rule 18, Rule 6(11)) → Flag violations → Generate audit trail |
| 🔎 **Cross Verification** | Compare physical package vs. online listing → Highlight discrepancies → Identify shrinkflation or over-MRP pricing |
| 📊 **Inspector Dashboard** | View extracted data → See comparison results → Review evidence → Generate forensic reports |

---

## 🧩 Three Inspection Modes

### 1️⃣ Image Only
**For physical/on-ground retail inspections**
```
Product Image → OpenCV → OCR → Field Extraction → Compliance Check
```

### 2️⃣ URL Only
**For digital marketplace verification**
```
E-Commerce URL → Web Retrieval → HTML Parsing → Field Extraction → Compliance Check
```

### 3️⃣ Image + URL
**For complete cross-verification (most powerful)**
```
Physical Package (OCR)  +  Online Listing (Web Scrape)
            ↓                        ↓
    Physical Fields          Online Fields
            └─────────────────────┘
                    ↓
            Unit Normalization
                    ↓
            Cross Verification
                    ↓
            Compliance Rules
                    ↓
        PASS / FAIL / WARN
```

---

## 🖥️ Dashboard & Visual Evidence

### Dual Inspection & Cross Verification
View physical and online information side-by-side, identify discrepancies instantly.

### OCR & Visual Evidence
Extracted text with bounding boxes for forensic accuracy and audit trail.

---

## 🏗️ System Architecture

```
┌─────────────────────┐       ┌──────────────────┐
│  Packaging Image    │       │  E-Commerce URL  │
└──────────┬──────────┘       └────────┬─────────┘
           │                           │
           ├─── OpenCV ─────┐    ┌──── Web Scraper
           │                │    │
           └─── EasyOCR ────┤    │
                            ▼    ▼
                   ┌─────────────────────┐
                   │  Data Extraction    │
                   └────────┬────────────┘
                            │
                   ┌────────▼────────────┐
                   │ Unit Normalization  │
                   │ (g, ml, etc.)       │
                   └────────┬────────────┘
                            │
                   ┌────────▼────────────────┐
                   │ Compliance Rule Engine  │
                   │ • Rule 6: Declarations  │
                   │ • Rule 18: Price Check  │
                   │ • Rule 6(11): USP       │
                   └────────┬────────────────┘
                            │
          ┌─────────────────┼─────────────────┐
          ▼                 ▼                 ▼
        PASS              FAIL              WARN
          │                 │                 │
          └─────────────────┴─────────────────┘
                            │
                   ┌────────▼────────────┐
                   │ Evidence & Report   │
                   └─────────────────────┘
```

---

## ⚙️ How NIRMAN Works

### Step 1: Input
Inspector provides:
- Product image, or
- E-commerce URL, or
- Both

### Step 2: Image Processing
OpenCV prepares image for optimal OCR performance:
```
Original Image → Resize → Grayscale → Contrast Enhancement → Noise Reduction → OCR
```

### Step 3: Information Extraction
OCR output is converted to structured fields:
```
Label Text:
  MRP ₹99
  Net Quantity 800 g
  Best Before 12 Months

↓

Structured Data:
  {
    "mrp": 99,
    "net_quantity": 800,
    "unit": "g",
    "best_before": "12 Months"
  }
```

### Step 4: Unit Normalization
Different representations are standardized:
```
1 kg → 1000 g
1 L  → 1000 ml
```
This enables meaningful comparison across pack sizes.

### Step 5: Rule Engine
Normalized data is evaluated against compliance rules:

| Rule | Purpose |
|------|---------|
| **Rule 6** | Verify mandatory declarations (origin, manufacturer, address) |
| **Rule 18** | Detect over-MRP pricing on e-commerce platforms |
| **Rule 6(11)** | Check unit sale price (USP) consistency across pack sizes |

### Step 6: Evidence & Report
System presents:
- ✅ Extracted values
- ✅ Comparison results
- ✅ Detected discrepancies
- ✅ Supporting evidence
- ✅ Compliance status

---

## 📊 Example Comparison

| Parameter | Physical Pack | Online Listing | Difference | Status |
|-----------|---------------|----------------|------------|--------|
| Listed Price | ₹99 | ₹110 | +₹11 | ⚠️ **Rule 18 Violation** |
| Net Quantity | 800 g | 800 g | 0 g | ✅ Compliant |
| Unit Sale Price | ₹0.123/g | ₹0.137/g | +₹0.014/g | ⚠️ Unfavorable Variance |
| Manufacturer | Detected | Detected | Match | ✅ Compliant |

---

## 🚦 PASS vs FAIL vs WARN

| Status | Meaning | Example |
|--------|---------|---------|
| 🟢 **PASS** | All configured compliance checks satisfied | Price matches, declarations present, units consistent |
| 🔴 **FAIL** | Clear potential issue detected | Over-MRP pricing, missing manufacturer details |
| 🟡 **WARN** | Information unclear, requires human review | Blurry image, OCR confidence low, ambiguous data |

**Why WARN?** Acts as a human-in-the-loop safety mechanism instead of blindly declaring violations when evidence is uncertain.

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|------------|
| **Frontend** | React.js + Vite + Tailwind CSS + Lucide Icons |
| **Backend** | Python + Flask |
| **Computer Vision** | OpenCV (preprocessing & adaptive scaling) |
| **OCR** | EasyOCR |
| **Web Extraction** | BeautifulSoup4 + Requests |
| **Data Format** | JSON |

---

## 🚀 Getting Started

### Prerequisites

- Python 3.10+
- Node.js 18+
- npm

### 1. Clone Repository

```bash
git clone https://github.com/Gbhavya996/nirman-compliance-checker.git
cd nirman-compliance-checker
```

### 2. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows
.\venv\Scripts\activate
# Linux/macOS
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run backend server
python app.py
```

Backend runs at: **http://localhost:5000**

### 3. Frontend Setup

```bash
# Open new terminal
cd frontend

# Install dependencies
npm install

# Run development server
npm run dev
```

Frontend runs at: **http://localhost:5173**

---


## 📁 Directory Structure

```
nirman-compliance-checker/
├── backend/
│   ├── app.py
│   ├── requirements.txt
│   ├── venv/
│   └── ...
├── frontend/
│   ├── src/
│   ├── public/
│   ├── package.json
│   ├── vite.config.js
│   └── ...
├── docs/
│   └── assets/
│       ├── nirman-banner.png
│       ├── cross_verification_dashboard.png
│       ├── visual_evidence_ocr.png
│       └── nirman-demo.gif
└── README.md
```

---

## 🔮 Future Scope

- 🌐 **Large-Scale Monitoring** — Process thousands of products via background workers and parallel processing
- 📱 **Mobile Inspection App** — Enable field inspectors to conduct inspections on mobile devices
- 📏 **Packaging Measurement** — Computer-vision-based measurement of text size and packaging dimensions
- 🔗 **Official Data Integration** — Connect with authorized product registries and government databases
- 🌍 **Multilingual Support** — Extend OCR to regional Indian languages (Hindi, Telugu, Tamil, etc.)
- 📈 **Analytics Dashboard** — Aggregate compliance trends and violation patterns across markets

---

## 🧪 Project Status



NIRMAN is currently in **prototype development** as a solution for the Smart India Hackathon 2026 (Problem Statement 26034/26035).

It is designed as a **proof-of-concept for automated compliance screening and inspector decision support** under India's Legal Metrology framework.

---


## 🤝 Contributing

Contributions, suggestions, and improvements are welcome!

1. **Fork** the repository
2. **Create** a feature branch (`git checkout -b feature/your-feature`)
3. **Make** your changes
4. **Commit** your changes (`git commit -m "Add feature description"`)
5. **Push** to your branch (`git push origin feature/your-feature`)
6. **Open** a Pull Request

---

## 📄 License

Add your preferred license here (e.g., MIT, Apache 2.0, GPL v3).

---

<p align="center">
  <strong>NIRMAN</strong><br>
  <i>Turning product information into explainable compliance evidence.</i><br>
  <br>
  Built with technology, teamwork, and a real-world purpose. 🎯
</p>
