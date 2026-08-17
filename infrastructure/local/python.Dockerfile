FROM python:3.13.5-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /workspace

RUN python -m pip install --no-cache-dir --upgrade pip==25.2
COPY requirements.lock /workspace/requirements.lock
RUN python -m pip install --no-cache-dir --require-hashes -r /workspace/requirements.lock

RUN addgroup --system app && adduser --system --ingroup app --home /home/app app
COPY --chown=app:app . /workspace
RUN chown app:app /workspace

USER app
EXPOSE 8000 8001

CMD ["python", "-m", "apps.api.colacci_api.main"]
