# Dockerfile for Maths Maharathi AI Pipeline Service
# Configured for Hugging Face Spaces (Port 7860, non-root user uid 1000)

FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    PORT=7860

# Install system dependencies: Tesseract OCR (Hindi + English), Poppler for PDFs, and graphics libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-hin \
    tesseract-ocr-eng \
    poppler-utils \
    libgl1 \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for Hugging Face Spaces and set up app directory ownership
RUN useradd -m -u 1000 user && \
    mkdir -p /home/user/app/data/ingested \
             /home/user/app/data/blueprints \
             /home/user/app/data/generated \
             /home/user/app/exports && \
    chown -R user:user /home/user

ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

WORKDIR /home/user/app

# Copy dependency specifications first for Docker layer caching
COPY --chown=user:user requirements.txt .

# Install Python dependencies as non-root user
USER user
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY --chown=user:user . .

# Hugging Face Spaces default port
EXPOSE 7860

# Run FastAPI app with Gradio admin mounted on /admin
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "2"]
