FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore
WORKDIR /app
COPY app/requirements.txt .
RUN pip install -r requirements.txt
COPY app/ .

# Test image: the app plus pytest and the tests. Used by `docker compose run test`.
FROM base AS test
COPY requirements-dev.txt /tmp/
RUN pip install -r /tmp/requirements-dev.txt
COPY tests/ /tests/
ENV APP_DIR=/app
CMD ["pytest", "-q", "-p", "no:cacheprovider", "/tests"]

# Runtime image (the default target).
FROM base AS runtime
RUN useradd --uid 10001 --create-home app
USER 10001
EXPOSE 8501
CMD ["streamlit", "run", "app.py"]
