from .base import *  # noqa: F403
from .base import env

DEBUG = True
SECRET_KEY = env("DJANGO_SECRET_KEY", default="local-dev-only-not-secret")
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]", "*"]
