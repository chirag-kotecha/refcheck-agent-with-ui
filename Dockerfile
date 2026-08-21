# Reference Check Analyzer -- container image.
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd --create-home --uid 1000 appuser
USER appuser

# No default CMD -- run any entry point on demand:
#   docker run --env-file .env <image> run_demo.py
#   docker run --env-file .env <image> run_demo_multi.py
#   docker run --env-file .env <image> run_batch_demo.py
#   docker run --env-file .env <image> run_batch_demo.py --provider bedrock
#   docker run --env-file .env <image> -m pytest tests/ -v
ENTRYPOINT ["python"]
CMD ["run_demo_multi.py"]
