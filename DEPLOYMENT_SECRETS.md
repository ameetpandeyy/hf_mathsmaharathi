# Maths Maharathi — Hugging Face & GitHub Action Environment Configuration

This repository (`hf_mathsmaharathi`) contains the Python FastAPI + PyMuPDF + Tesseract OCR + SymPy + Gradio AI Pipeline Service deployed to Hugging Face Spaces (`ameetspeaks/nomiai`).

For complete end-to-end configuration across **Vercel**, **Hugging Face**, **GitHub**, and **Supabase**, see [API_AND_DEPLOYMENT_SETUP.md](file:///c:/Users/ameet/Maths_Maharathi/API_AND_DEPLOYMENT_SETUP.md).

---

## 1. Secrets to Configure in Hugging Face Spaces (`ameetspeaks/nomiai`)

Navigate to: **Hugging Face Space** → **Settings** → **Variables and secrets** → **New secret**:

| Secret Name | Recommended Value | Purpose |
| :--- | :--- | :--- |
| `ADMIN_API_KEY` | `mm-dev-secret-key-2025` *(or your custom secret key)* | Protects `/generate`, `/analyse`, `/ingest` endpoints against unauthorized access from outside Vercel. Must match `HF_API_KEY` on Vercel. |
| `ADMIN_PASSWORD` | `YourSecureAdminPassword123!` | Basic authentication password for Gradio Admin Console at `/admin`. |
| `GEMINI_API_KEY` | `AIzaSy...` | Gemini 2.5 Flash for natural Hindi/English question rewording & variation synthesis. *(Optional: falls back to offline parametric templates).* |
| `SUPABASE_URL` | `https://xmlizxobkcorddbhgodx.supabase.co` | Supabase Cloud Database URL. |
| `SUPABASE_SERVICE_ROLE_KEY` | `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpX...` | Allows pipeline exporter to directly save verified content packs to Supabase tables. |

---

## 2. Secrets to Configure in GitHub Repository (`ameetpandeyy/hf_mathsmaharathi`)

Navigate to: **GitHub Repo** → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**:

| Secret Name | Value | Purpose |
| :--- | :--- | :--- |
| `HF_TOKEN` | `hf_...` (Write permission) | Allows the GitHub Action `.github/workflows/sync_to_hf.yml` to automatically git push commits to Hugging Face Space. |
| `HF_SPACE_REPO` | `ameetspeaks/nomiai` | Target space repository identifier. |

---

## 3. Connecting Vercel to this Hugging Face Space

On your **Vercel Project Settings** (`mathsmaharathi`), add:
- `HF_SPACE_URL`: `https://ameetspeaks-nomiai.hf.space`
- `HF_API_KEY`: Matching value of `ADMIN_API_KEY` above.
