import os

SQLALCHEMY_DATABASE_URI = "sqlite:///dashboard.db"
SQLALCHEMY_TRACK_MODIFICATIONS = False
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
TESLA_CLIENT_ID = os.getenv("TESLA_CLIENT_ID", "ownerapi")
TESLA_REDIRECT_URI = os.getenv("TESLA_REDIRECT_URI", "")
TESLA_USER_AGENT = os.getenv("TESLA_USER_AGENT", "Mozilla/5.0")
