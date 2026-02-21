# Install image with uv
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

ARG app_home
ENV APP_HOME=${app_home:-/app}

WORKDIR ${APP_HOME}

ARG CA_PATH
# Copy the certificate file if the path is provided.
COPY ${CA_PATH} /usr/local/share/ca-certificates/CA.crt
RUN if [ -f /usr/local/share/ca-certificates/CA.crt ]; then \
      echo "Updating CA certificates..."; \
      update-ca-certificates; \
    else \
      echo "No CA certificate provided, skipping update."; \
    fi
# --- End Certificate Handling ---

COPY ./src $APP_HOME/src

# Install dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-editable

# Image to run service
FROM python:3.12-slim-bookworm AS runner

ARG env_state
ENV ENV_STATE=${env_state:-dev}
ARG app_home
ENV APP_HOME=${app_home:-/app}

WORKDIR ${APP_HOME}

COPY --from=builder /usr/local/share/ca-certificates/CA.crt /usr/local/share/ca-certificates/CA.crt
RUN if [ -f /usr/local/share/ca-certificates/CA.crt ]; then \
      apt-get update && apt-get install -y ca-certificates && update-ca-certificates; \
    fi

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
COPY --from=builder ${APP_HOME} ${APP_HOME}

ENV PATH="${APP_HOME}/.venv/bin:$PATH"

CMD ["python", "src/app.py"]
