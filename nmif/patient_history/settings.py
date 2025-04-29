# settings.py

from pathlib import Path
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# BASE_DIR needs to point to the directory containing 'nmif'
# Assuming this settings.py is in 'nmif/patient_history/', then BASE_DIR
# should resolve to 'Final-Year-Project--OSCE-Simulator/'
BASE_DIR = Path(__file__).resolve().parent.parent.parent # Adjusted BASE_DIR calculation

# Static files settings remain unchanged:
STATIC_URL = '/static/'
# Adjust static paths relative to the new BASE_DIR if necessary
STATICFILES_DIRS = [BASE_DIR / "nmif" / "static"] # Example adjustment
STATIC_ROOT = BASE_DIR / "staticfiles" # Usually outside the main code dir

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-!fi*qz93$0z!)-i9#_sn4r)5b0b4fpj_9#fpwh(a-i^c80e)%%'

DEBUG = True
ALLOWED_HOSTS = ['final-year-project-osce-simulator-1.onrender.com', 'localhost', '127.0.0.1']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',
    # --- CHANGE 1: Use fully qualified paths for your apps ---
    'nmif.history',             # Assuming 'history' app is inside 'nmif' dir
    'nmif.marking_scheme_endpoints', # Assuming this app is also inside 'nmif' dir
    # --- End Change 1 ---
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# ROOT_URLCONF = 'patient_history.urls'
# This should point to the urls.py relative to a directory on the python path.
# Since pytest.ini sets `pythonpath = nmif`, Python looks inside 'nmif'.
# So, 'patient_history.urls' implies 'nmif/patient_history/urls.py'. This seems correct.
ROOT_URLCONF = 'nmif.patient_history.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            # Adjust template paths relative to the new BASE_DIR if necessary
            BASE_DIR / "nmif" / "templates",
            BASE_DIR / "nmif" / "patient_history" / "templates",
            BASE_DIR / "nmif" / "history" / "templates",
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# WSGI_APPLICATION = 'patient_history.wsgi.application'
# Similar to ROOT_URLCONF, this implies 'nmif/patient_history/wsgi.py'. Seems correct.
WSGI_APPLICATION = 'nmif.patient_history.wsgi.application'

# -----------------------------------------------------------------------------
# DATABASE CONFIGURATION
# -----------------------------------------------------------------------------
# --- CHANGE 2: Use SQLite for testing instead of dummy backend ---
# Comment out the dummy backend:
# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.dummy',
#     }
# }

# Use SQLite, preferably in-memory for tests:
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        # Use in-memory DB for speed during tests.
        # Pytest-django handles the name ':memory:' correctly.
        'NAME': ':memory:',
        # If you needed a file-based SQLite for testing:
        # 'NAME': BASE_DIR / 'db_test.sqlite3',
    }
}
# --- End Change 2 ---

# -----------------------------------------------------------------------------
# REMAINING SETTINGS (Password validators, CORS, Internationalization, etc.)
# -----------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    { 'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator', },
]

CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000", # Your Next.js app
]
CORS_ALLOW_ALL_ORIGINS = True # Consider restricting this more in production
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:3000",
    "https://fyp-ai-chatbot-git-main-dlaffey1s-projects.vercel.app"
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
# USE_L10N = True # Deprecated in Django 5.0
USE_TZ = True

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'