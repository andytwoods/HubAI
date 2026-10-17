from .base import *  # noqa: F403
from .base import env

SECRET_KEY = env("DJANGO_SECRET_KEY")
# No default in production: the code in base.py is public in the repo.
EVENT_CODE = env("HUBAI_EVENT_CODE")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])
# Under ASGI, persistent connections (CONN_MAX_AGE > 0) leak one per worker thread and exhausted
# Postgres ("too many clients"). A small pool per uvicorn worker caps the total instead.
DATABASES["default"]["CONN_MAX_AGE"] = 0  # noqa: F405
DATABASES["default"]["OPTIONS"] = {"pool": {"min_size": 1, "max_size": env.int("DB_POOL_MAX", default=4)}}  # noqa: F405

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_CONTENT_TYPE_NOSNIFF = True

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
