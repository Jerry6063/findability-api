# Eval runner: the service image plus the eval-only dependencies.
# Build from the repo root:  docker build -f evals/Dockerfile -t findability-evals .
FROM findability-api:latest
COPY evals/requirements-evals.txt /tmp/req-evals.txt
RUN pip install --no-cache-dir -r /tmp/req-evals.txt
