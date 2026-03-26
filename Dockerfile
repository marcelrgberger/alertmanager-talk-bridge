FROM python:3.13-alpine
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bridge.py .
EXPOSE 8080
USER nobody
CMD ["python", "bridge.py"]
