import os
from dotenv import load_dotenv

load_dotenv()

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your_default_secret_key'  # Replace with a strong secret key
    SQLALCHEMY_TRACK_MODIFICATIONS = False  # Disable Flask-SQLAlchemy event system
    FLASK_ENV = os.getenv('FLASK_ENV')



class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.getenv('SQLALCHEMY_DATABASE_URI')  # Local SQLite database
    


class StagingConfig(Config):
    DEBUG = True
    # Replace with your staging database URI
    SQLALCHEMY_DATABASE_URI = os.environ.get('STAGING_DATABASE_URI') or 'postgresql://...'


class ProductionConfig(Config):
    DEBUG = False
    # Replace with your production database URI
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URI') or 'postgresql://...'
