FROM python:3.11-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agents/ ./agents/
COPY api/    ./api/
COPY db/     ./db/
COPY frontend/ ./frontend/

ENV DB_PATH=/tmp/ssc_scheduler.db
ENV GEMINI_MODEL=gemini-2.0-flash
ENV PORT=8080

EXPOSE 8080
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]
