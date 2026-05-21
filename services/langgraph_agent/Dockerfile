FROM python:3.12-slim

WORKDIR /app

# Install deps first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the langgraph_agent service
COPY . .

# Copy the shared agents package from the repo root.
# The COPY context is ./services/langgraph_agent (set in docker-compose).
# We need ../../agents — so we copy it in docker-compose via a separate
# build context or volume mount. For now we use a volume mount in dev.

EXPOSE 8004

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8004", "--reload"]
