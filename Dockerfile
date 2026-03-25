# Use official lightweight Python image
FROM python:3.11-slim

# Set work directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy code
COPY monitor.py .
COPY .env .

# Run script
CMD ["python", "monitor.py"]

