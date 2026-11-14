FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY pyproject.toml .
COPY app ./app
COPY eval ./eval
COPY tests ./tests

RUN useradd --create-home agent
USER agent

EXPOSE 8000
# Load the data first; the API starts only if the load succeeded
CMD ["sh", "-c", "python -m app.data.loader && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
