# Pin by digest per repo convention (see coyote-config modules/docker/*).
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY source-stripper.py .

# configuration.json is mounted read-only at /app/configuration.json (see the
# compose service); it is intentionally NOT baked into the image.
CMD ["python", "source-stripper.py"]
