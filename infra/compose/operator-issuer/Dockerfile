FROM python:3.11.9-slim

WORKDIR /app

RUN pip install --no-cache-dir \
  "fastapi==0.115.6" \
  "uvicorn[standard]==0.34.0" \
  "PyJWT==2.10.1" \
  "cryptography==44.0.0" \
  "pyyaml==6.0.2" \
  "python-multipart==0.0.20"

COPY main.py /app/main.py

EXPOSE 8088
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8088"]
