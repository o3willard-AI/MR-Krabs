
import json
from werkzeug.exceptions import HTTPException
from flask import Response

def handle_api_error(e: Exception) -> Response:
    