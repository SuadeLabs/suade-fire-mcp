FROM python:3.12-slim

# Pinned to a FIRE release tag, not master -- this image serves many different people, so
# it should be reproducible rather than silently changing when FIRE gets a new commit.
# CI reads this line to test against the same FIRE version, so bump it only here.
ARG FIRE_VERSION=v26.10

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

# The server only reads files, so it doesn't need root. FIRE and the package stay
# root-owned (world-readable), so the server can't modify them either.
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin fire
USER fire

# /health answers only on the HTTP transport. A container run as a stdio server
# (FIRE_MCP_TRANSPORT=stdio) has nothing listening, so it reports healthy instead
# of being marked unhealthy for doing its job.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import os, sys, urllib.request; os.environ.get('FIRE_MCP_TRANSPORT') == 'stdio' and sys.exit(0); urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8000') + '/health', timeout=4)"]

EXPOSE 8000
CMD ["fire-mcp"]
