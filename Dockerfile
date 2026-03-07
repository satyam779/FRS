FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=5000

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt
# Install face-recognition without dependency resolution so pip does not
# attempt to build heavy dlib from source during Render free-tier builds.
RUN pip install --no-deps face-recognition==1.3.0

COPY . .

RUN mkdir -p /app/known_faces /app/attendance

EXPOSE 5000

CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT} --workers 1 --threads 2 --timeout 120 wsgi:app"]
