---
title: Maths Maharathi AI Pipeline
emoji: 🎯
colorFrom: red
colorTo: yellow
sdk: docker
app_port: 7860
pinned: false
license: apache-2.0
---

# Maths Maharathi — AI Exam Pipeline Service

This repository houses the offline-first AI question extraction, mathematical verification, pattern analysis, and mock generation pipeline for **Maths Maharathi** (SSC, Banking, and Railway calculation speed trainer).

It is designed to run as a **Hugging Face Space** (Docker SDK on port 7860) and execute heavy-load recurring batch processing via **GitHub Actions scheduled cron jobs** (benefiting from unlimited free public workflow minutes).

---

## Architecture & Core Modules

```
hf_mathsmaharathi/
├── .github/workflows/
│   ├── sync_to_hf.yml        # Auto-syncs repo changes from GitHub to Hugging Face Space
│   └── scheduled_cron.yml    # Daily heavy-load batch cron (02:00 UTC) with free GitHub runners
├── app/
│   ├── main.py               # FastAPI backend with REST endpoints & health checks
│   ├── admin_ui.py           # Gradio web console mounted at /admin
│   └── auth.py               # Token & Basic Auth security layer
├── pipeline/
│   ├── ingest/               # PDF/TXT/OCR extraction (Tesseract, PyMuPDF, pdfplumber)
│   ├── parse/                # Bilingual question segmenter (Hindi & English)
│   ├── analyse/              # Topic weightage & blueprint analysis engine
│   ├── classify/             # Bloom taxonomy, exam tagger, and difficulty classifier
│   ├── generate/             # Algorithmic template & Gemini LLM question synthesizer
│   ├── verify/               # SymPy symbolic math solver & option verifier
│   ├── dedupe/               # SimHash & SHA-256 duplicate detection engine
│   ├── review/               # Quality review workflow manager
│   ├── export/               # Content pack builder with legal gating & Supabase sync
│   └── cli.py                # Local command-line interface
├── schemas/                  # Pydantic v2 models and enums
├── cron/
│   └── run_batch_pipeline.py # Heavy-load batch runner for recurring scheduled tasks
├── samples/                  # Reference previous-year paper samples
├── tests/                    # Pytest integrity and solver verification suite
├── Dockerfile                # Hugging Face Spaces optimized Docker image
└── requirements.txt          # Python dependencies
```

---

## Security & Copyright Guardrails (Mandatory)

1. **Zero Secret Leakage:**
   - No API keys, database credentials, or auth tokens are committed to this repository.
   - All secrets (`HF_TOKEN`, `GEMINI_API_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `ADMIN_PASSWORD`) must be stored in:
     - **GitHub Repository Settings** > **Secrets and variables** > **Actions**
     - **Hugging Face Space Settings** > **Variables and secrets**
   - The batch runner operates smoothly with offline fallback templates even if external LLM keys are absent.

2. **Legal & Rights Isolation Gate:**
   - Every ingested question is stamped with `source_type='pyq_reference'`.
   - The `ContentPackBuilder` strictly blocks `pyq_reference` rows from entering published packs unless explicitly marked `rights_cleared=True` by a verified administrator.
   - Only original, mathematically verified questions (`source_type='original'` and `machine_verified=True`) are packaged for student practice packs.

---

## GitHub Actions Sync & Free Unlimited Cron

### 1. Auto-Sync to Hugging Face Spaces (`sync_to_hf.yml`)
Whenever code is pushed to the `main` branch on GitHub, GitHub Actions mirrors all changes to your Hugging Face Space automatically.

**Required GitHub Secrets:**
- `HF_TOKEN`: Hugging Face User Access Token with **Write** permissions (create at `huggingface.co/settings/tokens`).
- `HF_SPACE_REPO`: Destination Space name (e.g. `your-username/maths-maharathi-pipeline`).

### 2. Heavy-Load Scheduled Batch Cron (`scheduled_cron.yml`)
- Runs automatically every night at **02:00 UTC (07:30 IST)** or on-demand via **Run workflow** button.
- Executes:
  1. Blueprint pattern analysis on PYQ references.
  2. Synthesizes original mock papers across all 5 exam tracks (SSC CGL, SSC CHSL, IBPS PO, SBI Clerk, RRB NTPC).
  3. Proves every answer using SymPy symbolic mathematics.
  4. Deduplicates against the hash database.
  5. Packages cryptographically checksummed offline content packs to `exports/`.
- Uploads the generated packs and execution logs as downloadable workflow artifacts.

---

## Local Development & CLI

### Running with Docker (Same as Hugging Face Spaces)
```bash
docker build -t maths-maharathi-pipeline .
docker run -p 7860:7860 -e ADMIN_PASSWORD="your-admin-password" maths-maharathi-pipeline
```
Open [http://localhost:7860](http://localhost:7860) for FastAPI docs or [http://localhost:7860/admin](http://localhost:7860/admin) for the Gradio admin UI.

### Running the Batch Pipeline Locally
```bash
# In virtual environment:
pip install -r requirements.txt
python cron/run_batch_pipeline.py
```

### Running Test Suite
```bash
pytest tests/ -v
```

---

## Deployment to Standalone GitHub Repository

To publish this folder to its own dedicated public GitHub repository:

```bash
cd hf_mathsmaharathi
git init
git add .
git commit -m "feat: initial commit of Maths Maharathi AI Pipeline"
git branch -M main
git remote add origin https://github.com/YOUR_GITHUB_USERNAME/hf_mathsmaharathi.git
git push -u origin main
```
Then configure `HF_TOKEN` and `HF_SPACE_REPO` in your GitHub repository secrets.
