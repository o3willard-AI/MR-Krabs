
from flask import Flask, jsonify
from app.utils import register_error_handlers

def create_app():
    app = Flask(__name__)

    # Register error handlers
    register_error_handlers(app)

    @app.route('/')
    def hello():
        return jsonify({"status": "success", "data": {"message": "Hello, Flask!"}})

    # Example endpoint to test unhandled exception
    @app.route('/error')
    def trigger_error():
        raise ValueError("This is a test error!")

    # Example endpoint to test 404
    @app.route('/test-404')
    def test_404():
        from werkzeug.exceptions import NotFound
        raise NotFound("This page was not found.")

    return app
