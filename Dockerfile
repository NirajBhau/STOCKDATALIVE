# Use official Playwright Python base image with Chromium pre-installed
FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Set environment variables
ENV HEADLESS=true
ENV PYTHONUNBUFFERED=1

# Run the 24/7 continuous main script
CMD ["python", "main.py"]
