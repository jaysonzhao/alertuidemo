# Build stage
FROM registry.access.redhat.com/ubi9/python-39:latest AS builder

WORKDIR /app

# Install pip
RUN pip install --upgrade pip

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app.py .

# Production stage
FROM registry.access.redhat.com/ubi9/python-39-minimal

# Install pip in runtime image
RUN pip install --no-cache-dir --upgrade pip

WORKDIR /app

# Copy from builder (files owned by root)
COPY --from=builder /app /app

# OpenShift: Run as non-root user via Security Context (in deployment)
# No chmod needed - permissions set at runtime by OpenShift

# Expose port
EXPOSE 8080

# Environment variables
ENV APP_HOST=0.0.0.0 \
    APP_PORT=8080 \
    APP_DEBUG=false \
    MAX_ALERTS=1000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run the application
CMD ["python", "app.py"]
