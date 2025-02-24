# Use a base image that includes apt-get (we’re using python:3.11-slim)
FROM python:3.11-slim

# Install system dependencies (including build-essential and PostgreSQL client libraries)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
 && rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /app

# Copy requirements.txt first to leverage Docker cache for dependencies
COPY requirements.txt .

# Upgrade pip and install Python dependencies
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy the rest of the project files into the container
COPY . .

# Collect static files (adjust if needed)
RUN python manage.py collectstatic --noinput

# Run database migrations (optional; consider running this as part of your deployment pipeline)
RUN python manage.py migrate --noinput

# Expose the port (Render and similar services provide the port via the $PORT variable)
EXPOSE $PORT

# Set the default command to run Gunicorn with your Django project's WSGI application.
CMD ["gunicorn", "patient_history.wsgi:application", "--bind", "0.0.0.0:$PORT"]
