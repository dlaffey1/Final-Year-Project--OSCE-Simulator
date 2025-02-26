# Use a Debian‑based image that includes apt-get
FROM python:3.11-slim

# Install system dependencies required for your project
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    python3-dev \
    libpq-dev \
    libsystemd-dev \
    pkg-config \
    libcairo2-dev \
    meson \
    ninja-build \
    libffi-dev \
    libgirepository1.0-dev \
    libdbus-1-dev \
    libdbus-glib-1-dev \
 && rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /app

# Copy requirements.txt first to leverage Docker cache for dependency installation
COPY requirements.txt .

# Upgrade pip and install Python dependencies
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy the rest of the project files into the container
COPY . .

# (Optional) For Django: Collect static files and run migrations
RUN python manage.py collectstatic --noinput
# RUN python manage.py migrate --noinput

# Expose the port (Render provides the port via the $PORT variable)
EXPOSE $PORT

# Set the default command to run Gunicorn with your Django project's WSGI application.
CMD ["gunicorn", "patient_history.wsgi:application", "--bind", "0.0.0.0:$PORT"]
