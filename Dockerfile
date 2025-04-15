# Use an official Python image as base
FROM python:3.11-slim

# Set the working directory
WORKDIR /app

# Copy only the files we need
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the app
COPY . .

# Default command to run the app
CMD ["python3", "p2p.py"]
