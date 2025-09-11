FROM python:3.11-slim
WORKDIR /app
COPY app /app
# 👇 AGREGA python-multipart
RUN pip install --no-cache-dir fastapi uvicorn[standard] requests python-multipart
EXPOSE 8001
CMD ["uvicorn", "main:api", "--host", "0.0.0.0", "--port", "8001"]
