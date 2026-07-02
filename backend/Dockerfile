# Use AMD ROCm official Ubuntu-based development image which contains
# the complete development toolchain (hipcc, hipify-clang, and libraries)
FROM rocm/dev-ubuntu-22.04:6.0.2

# Set the working directory in the container
WORKDIR /app

# Add ROCm bin directory to PATH so hipcc and hipify-clang are accessible
ENV PATH="${PATH}:/opt/rocm/bin"

# Install Python 3, pip, python-is-python3, and clean apt caches to keep the image slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python-is-python3 \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file from backend context
COPY *requirements.txt */requirements.txt ./

# Install python packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the backend application code
COPY *ap[p] */ap[p] ./app/

# Expose port 8000 for FastAPI
EXPOSE 8000

# Run the FastAPI application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
