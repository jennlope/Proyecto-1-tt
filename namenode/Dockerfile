FROM python:3.11-slim
WORKDIR /app
COPY app /app
RUN pip install --no-cache-dir fastapi uvicorn[standard] aiosqlite pydantic[dotenv] python-multipart
EXPOSE 8000
CMD ["uvicorn", "main:api", "--host", "0.0.0.0", "--port", "8000"]
