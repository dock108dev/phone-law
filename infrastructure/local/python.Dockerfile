FROM python:3.14.7-slim-bookworm

ARG COLACCI_CANDIDATE_COMMIT=unbound
ARG COLACCI_CANDIDATE_TREE=unbound
ARG COLACCI_RUNTIME_CONTRACT=unbound

LABEL io.colacci-law.candidate.commit="$COLACCI_CANDIDATE_COMMIT" \
    io.colacci-law.candidate.tree="$COLACCI_CANDIDATE_TREE" \
    io.colacci-law.runtime.contract="$COLACCI_RUNTIME_CONTRACT"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /workspace

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg=7:5.1.9-0+deb12u1 \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --no-cache-dir --upgrade pip==26.2.1
COPY requirements.lock /workspace/requirements.lock
RUN python -m pip install --no-cache-dir --require-hashes -r /workspace/requirements.lock

RUN addgroup --system app && adduser --system --ingroup app --home /home/app app
COPY --chown=app:app . /workspace
RUN chown app:app /workspace

USER app
EXPOSE 8000 8001

CMD ["python", "-m", "apps.api.colacci_api.main"]
