FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY frontend ./frontend
COPY data ./data
COPY submission ./submission
COPY tigergraph ./tigergraph
COPY tools ./tools
ENV ARGUS_DB=/app/data/argus.db
ENV ARGUS_STEP_DELAY=0.15
EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
