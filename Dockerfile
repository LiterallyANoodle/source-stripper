# Floating tag matches the coyote-config modules/docker/* house convention
# (see mlp-vote). The bot token is NOT baked in — it is injected at runtime
# as SOURCE_STRIPPER_TOKEN (sealed in sops on the host).
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY source-stripper.py .
# Version-controlled domain_matchers travel with the image as its config; the
# template's empty bot_token is overridden at runtime by SOURCE_STRIPPER_TOKEN.
COPY configuration-template.json configuration.json

CMD ["python", "source-stripper.py"]
