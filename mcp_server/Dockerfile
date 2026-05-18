FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (Docker layer caching — deps only re-install if requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source last (most likely to change — keeps cache warm for deps)
COPY . .

# Create __init__.py files for package imports
RUN touch middleware/__init__.py tools/__init__.py

EXPOSE 8000

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]
