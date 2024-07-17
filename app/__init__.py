from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from dotenv import load_dotenv
from app.config import Config, ProductionConfig, StagingConfig, DevelopmentConfig  # Replace with the actual path
import os

# load_dotenv()

app = Flask(__name__)


# Determine the config class based on the environment
config_class = {
    'production': ProductionConfig,
    'development': DevelopmentConfig,
    'staging': StagingConfig,
}.get(os.environ.get('FLASK_ENV'), DevelopmentConfig)  # Default to DevelopmentConfig

app.config.from_object(config_class)  # Load the appropriate config class

# app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('SQLALCHEMY_DATABASE_URI') # Your PostgreSQL connection URI
# app.config['SECRET_KEY'] = 'your_secret_key'
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

from app import views, models  # Import routes and models after app is created
