from app import app, db  # Import the Flask app instance and the database

# Optional: Create database tables if they don't exist
# with app.app_context():
#     db.create_all()

if __name__ == '__main__':
    app.run(debug=True)