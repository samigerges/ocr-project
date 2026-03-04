# Use official lightweight Python image
FROM python:3.11-slim

# Prevent Python from writing .pyc files
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies required for:
# - OpenCV
# - PaddleOCR
# - PyMuPDF
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first (better Docker caching)
COPY requirements.txt /app/requirements.txt

# Upgrade pip and install Python dependencies
RUN python -m pip install --upgrade pip \
    && python -m pip install -r /app/requirements.txt

# Copy project files
COPY . /app

# Expose FastAPI port
EXPOSE 8000

# Default command (API)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]