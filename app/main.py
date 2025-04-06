# app/main.py (Flask Version - Confirmed Suitable for Docker)
import logging
import os
from flask import Flask, request, jsonify
from flask_cors import CORS

# Import components - initialization happens within these calls
from app.rag_component import get_rag_chain, GOOGLE_API_KEY # Ensure using absolute import

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
log = logging.getLogger(__name__)

# Initialize Flask App
app = Flask(__name__)
CORS(app) # Enable CORS for all origins
log.info("Flask-Cors enabled for all origins.")

# Application Initialization & State
rag_chain_instance = None
initialization_error = None
log.info("Flask application module loaded. Attempting RAG component initialization (will build DB if needed)...")
try:
    if not GOOGLE_API_KEY:
         raise ValueError("GOOGLE_API_KEY environment variable not set or empty.")
    # Initialize components via get_rag_chain. This triggers DB build if needed.
    # This can be slow on startup in the ephemeral Docker environment!
    rag_chain_instance = get_rag_chain()
    log.info("RAG components initialization attempt finished successfully.")
except Exception as e:
    log.exception("FATAL ERROR during application startup initialization.")
    initialization_error = f"Initialization Failed: {type(e).__name__} - Check server logs."

# API Endpoints
@app.route("/recommend", methods=['POST'])
def recommend_assessment():
    log.debug("'/recommend' endpoint hit.")
    if initialization_error:
         log.error(f"Initialization error detected. Returning 503. Error: {initialization_error}")
         return jsonify({"error": f"Service Unavailable: {initialization_error}"}), 503
    if not rag_chain_instance:
         log.error("RAG chain is None. Unexpected state.")
         return jsonify({"error": "Service Unavailable: RAG components not ready."}), 503

    # --- Request Validation ---
    if not request.is_json:
        log.warning("Request Content-Type is not application/json.")
        return jsonify({"error": "Request must be JSON."}), 415
    try:
        data = request.get_json()
        if not data or 'question' not in data or not isinstance(data['question'], str) or not data['question'].strip():
            log.warning(f"Invalid request payload received: {data}")
            return jsonify({"error": "Invalid request body. Required: {'question': 'your non-empty query'}."}), 400
        question = data['question']
        log.info(f"Processing recommendation for question: '{question[:100]}...'")
    except Exception as e:
         log.error(f"Error parsing request JSON: {e}", exc_info=True)
         return jsonify({"error": "Invalid JSON format in request body."}), 400

    # --- RAG Invocation ---
    try:
        # Synchronous call - Flask waits here
        result = rag_chain_instance.invoke(question)
        log.info(f"Successfully generated recommendation for question: '{question[:100]}...'")
        # Return the answer directly
        return jsonify({"answer": result}), 200
    except Exception as e:
        log.exception(f"Error invoking RAG chain for question: '{question[:100]}...'")
        return jsonify({"error": "An internal error occurred while processing the request."}), 500

@app.route("/health", methods=['GET'])
def health_check():
    log.debug("'/health' endpoint hit.")
    if initialization_error:
         log.warning(f"Health check reporting unhealthy due to initialization error: {initialization_error}")
         return jsonify({"status": "unhealthy", "reason": initialization_error}), 503
    return jsonify({"status": "ok"}), 200

# NO __main__ block needed - Gunicorn runs the 'app' object via CMD in Dockerfile