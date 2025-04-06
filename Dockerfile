# Dockerfile (Ensure this is in your project root)

# Use an official Python base image
FROM python:3.11-slim

# Set environment variables for smoother installs
ENV PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    POETRY_NO_INTERACTION=1 \
    DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1

# Install Rust via rustup and essential build tools + libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    pkg-config \
    libssl-dev \
    libffi-dev \
    python3-dev \
    curl \
    && curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- --default-toolchain stable -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Add cargo (Rust's package manager) bin directory to the PATH
ENV PATH="/root/.cargo/bin:${PATH}"

# Set working directory inside the container
WORKDIR /app

# Copy ONLY requirements first to leverage Docker build cache
COPY requirements.txt .

# Install Python dependencies (Rust and C/C++ compilers are now available)
# Increased timeout for potentially long builds
RUN pip install --upgrade pip && pip install --timeout 600 -r requirements.txt

# Copy the rest of the application code (app folder, data folder etc.)
COPY ./app ./app
COPY ./data ./data

# Expose the port Gunicorn will run on internally
EXPOSE 7860 

# Define the command to run the application using Gunicorn
# Tuned Gunicorn settings: shared memory tmp, 1 worker/8 threads, longer timeout
CMD ["gunicorn", "--worker-tmp-dir", "/dev/shm", "--workers", "1", "--threads", "8", "--timeout", "180", "--bind", "0.0.0.0:7860", "app.main:app"]