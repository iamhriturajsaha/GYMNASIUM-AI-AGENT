# Use official Python slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy agent package into a named subfolder (required for adk web to discover it)
RUN mkdir -p /app/gymnasium
COPY agent.py /app/gymnasium/agent.py
COPY __init__.py /app/gymnasium/__init__.py

# ADK's adk web uses 8080 by default
ENV PORT=8080

# Expose the port
EXPOSE 8080

# Run ADK web from /app
CMD ["sh", "-c", "adk web --host 0.0.0.0 --port ${PORT}"]
