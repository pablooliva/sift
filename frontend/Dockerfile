# Frontend Dockerfile for txtai Personal Knowledge Management
# Includes media processing capabilities (video audio extraction)
# Includes image processing capabilities (SPEC-008)

FROM python:3.12-slim

# Install system dependencies for media and image processing
# - ffmpeg: Core media processing toolkit (required by moviepy, and for ffprobe validation)
# - ffprobe: Media file validation and metadata extraction
# - tesseract-ocr: OCR text extraction from images (SPEC-008 REQ-009)
# - libheif-examples: HEIC/HEIF image support (iPhone photos)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    tesseract-ocr \
    libheif-examples \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better Docker layer caching
COPY requirements.txt .

# Install Python dependencies
# Note: Whisper transcription is now handled by txtai API (GPU-accelerated)
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose Streamlit port
EXPOSE 8501

# Run Streamlit
CMD ["streamlit", "run", "Home.py", "--server.port=8501", "--server.address=0.0.0.0"]
