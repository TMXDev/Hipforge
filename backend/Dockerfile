# Use an official Python runtime as a parent image
FROM python:3.10-slim-buster

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file from either backend/requirements.txt or requirements.txt
# This ensures build compatibility whether context is set to . or ./backend
COPY backend/requirements.tx[t] requirements.tx[t] ./

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the backend application code from either backend/app or app
# This ensures build compatibility whether context is set to . or ./backend
COPY backend/ap[p] ap[p] ./app/

# Expose port 8000 for FastAPI
EXPOSE 8000

# Run the FastAPI application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
