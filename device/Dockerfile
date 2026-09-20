# Optional: run a display agent in Docker instead of Python.
#   docker build -t signage-device device/
#   docker run --rm -p 8101:8101 -e SERVER_URL=https://<name>.trycloudflare.com/api \
#       -e DEVICE_ID=DEV-001 -e REGISTRATION_TOKEN=XXXX-XXXX-XXXX -v signage-cache:/app/.cache signage-device
# then open http://localhost:8101 in a browser.
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PYTHONUNBUFFERED=1 DISPLAY_PORT=8101 DISPLAY_BIND=0.0.0.0
EXPOSE 8101
CMD ["python", "agent.py"]
