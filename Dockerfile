FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY frontend ./frontend
RUN mkdir -p data
ENV ARGUS_DB=/app/data/argus.db
EXPOSE 8000
# The database is created and seeded on first start. Mount /app/data to keep it between runs.
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
