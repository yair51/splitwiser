from app import app, db
from app.views import views
from app.auth import auth

# Register blueprints
app.register_blueprint(views, url_prefix='/')  # Register the views blueprint
app.register_blueprint(auth, url_prefix='/')  # Register the auth blueprint

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)
