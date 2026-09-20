FROM python:3.12-slim
WORKDIR /srv
COPY device/requirements.txt device/requirements.txt
RUN pip install --no-cache-dir -r device/requirements.txt
COPY device ./device
COPY simulator ./simulator
ENV PYTHONUNBUFFERED=1 IN_DOCKER=1
WORKDIR /srv/simulator
CMD ["python", "run_all.py", "--server", "http://backend:8000"]
