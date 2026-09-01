FROM python:3.12-slim
WORKDIR /app/event-detector
COPY event-detector/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY event-detector/ .
COPY ce_definitions/ /app/ce_definitions/
ENV CE_DEFINITION_DIR=/app/ce_definitions
CMD ["python", "-m", "services.visualization", "--host", "0.0.0.0"]
