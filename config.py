import os

SQLALCHEMY_DATABASE_URI = "sqlite:///dashboard.db"
SQLALCHEMY_TRACK_MODIFICATIONS = False
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
