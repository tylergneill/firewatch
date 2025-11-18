FROM python:3.11-slim-bookworm
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN groupadd appgroup && \
    useradd -r -M -G appgroup sanskrit && \
    mkdir -p /app && \
    chown -R sanskrit:appgroup /app
COPY --chown=sanskrit:appgroup templates /app/templates
COPY --chown=sanskrit:appgroup static /app/static
COPY --chown=sanskrit:appgroup ./*.py /app/
COPY --chown=sanskrit:appgroup ./*.txt /app/
COPY --chown=sanskrit:appgroup ./VERSION /app/
USER sanskrit
CMD ["gunicorn", "--workers", "4", "--bind", "0.0.0.0:5070", "--log-level", "info", "--error-logfile", "-", "flask_app:app"]
EXPOSE 5070