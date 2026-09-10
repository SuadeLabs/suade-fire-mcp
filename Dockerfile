FROM python:3.12-slim

# Pinned to a FIRE release tag, not master -- this image serves many different people, so
# it should be reproducible rather than silently changing when FIRE gets a new commit.
ARG FIRE_VERSION=v26.07

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --branch "${FIRE_VERSION}" --depth 1 \
    https://github.com/SuadeLabs/fire.git /opt/fire

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir .

ENV FIRE_REPO_ROOT=/opt/fire
ENV FIRE_MCP_TRANSPORT=streamable-http

EXPOSE 8000
CMD ["fire-mcp"]
