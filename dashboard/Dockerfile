FROM python:3.11-slim
WORKDIR /app
COPY main.py /app/
COPY templates /app/templates
RUN pip install --no-cache-dir fastapi uvicorn requests jinja2
EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
