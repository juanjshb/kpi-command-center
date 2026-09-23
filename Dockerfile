FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv/app
COPY pyproject.toml requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
COPY app ./app
COPY scripts/scrapers/scotia_sucursales.py ./scripts/scrapers/scotia_sucursales.py
COPY dashboard ./dashboard
COPY alembic ./alembic
COPY alembic.ini ./
RUN useradd --create-home appuser
USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
