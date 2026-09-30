FROM python:3.11-slim

WORKDIR /app

# 시스템 패키지 최소화 (레이어 캐시를 위해 requirements 먼저 복사)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# non-root 사용자로 실행 (보안 권장 사항)
RUN useradd --create-home appuser
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
