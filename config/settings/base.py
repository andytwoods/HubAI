from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve(strict=True).parent.parent.parent
APPS_DIR = BASE_DIR / "hubai"
env = environ.Env()

DEBUG = env.bool("DJANGO_DEBUG", False)
TIME_ZONE = "UTC"
LANGUAGE_CODE = "en-gb"
USE_I18N = False
USE_TZ = True

DATABASES = {"default": env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}")}
DATABASES["default"]["ATOMIC_REQUESTS"] = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

DJANGO_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.admin",
]
LOCAL_APPS = [
    "hubai.users",
    "hubai.projects",
]
INSTALLED_APPS = DJANGO_APPS + LOCAL_APPS

AUTH_USER_MODEL = "users.User"
LOGIN_URL = "users:login"
LOGIN_REDIRECT_URL = "projects:home"

# Hackathon tool: one sign-in should last the whole event and beyond.
SESSION_COOKIE_AGE = 60 * 60 * 24 * 30

# The shared code organisers hand out; anyone holding it can create an account.
EVENT_CODE = env("HUBAI_EVENT_CODE", default="hack")
# Shown in the privacy notice: when all data is wiped, and an optional contact for data requests.
DELETE_ALL_DATA_ON = env("HUBAI_DELETE_ALL_DATA_ON", default="31 October 2026")
DATA_CONTACT = env("HUBAI_DATA_CONTACT", default="")
# Unlocks /stats/ (usage counts, no personal data). Empty disables it.
STATS_KEY = env("HUBAI_STATS_KEY", default="")

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

STATIC_ROOT = str(BASE_DIR / "staticfiles")
STATIC_URL = "/static/"
STATICFILES_DIRS = [str(APPS_DIR / "static")]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [str(APPS_DIR / "templates")],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "hubai.users.context_processors.legal",
            ],
        },
    },
]

ADMIN_URL = env("DJANGO_ADMIN_URL", default="admin/")

# Rate limits need a cache shared by every uvicorn worker, so production uses the database cache.
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"level": "INFO", "handlers": ["console"]},
}
