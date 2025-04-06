---
title: SHL RAG Recommender API (Flask/Docker)
emoji: 🐳🐍
colorFrom: indigo
colorTo: blue
sdk: docker # Specifies Docker deployment
app_port: 7860 # The port EXPOSEd and bound in the Dockerfile CMD
# suggested_hardware: cpu-basic # You can uncomment if needed later
---

# SHL Assessment Recommendation Engine Backend (Flask/Docker)

This repository contains the Flask backend for an SHL Assessment Recommendation Engine. It uses a Retrieval-Augmented Generation (RAG) pipeline built with LangChain, ChromaDB (ephemeral), Sentence Transformers, and the Google Gemini API.

The application is deployed using Docker on Hugging Face Spaces.

## Deployment

This application uses Docker to ensure all system dependencies (like Rust for certain Python packages) are correctly installed. The deployment process involves:

1.  Building the Docker image using the provided `Dockerfile`.
2.  Running the container on Hugging Face Spaces.
3.  On startup, the application checks for a local vector database. Since storage is ephemeral on the free tier, it **builds the ChromaDB index from the source data (`data/merged_shl_product_data.json`) every time the Space starts or wakes up.** This initial build process can take several minutes and consume significant resources.

## API Endpoints

The deployed application exposes the following endpoints:

*   **`/health` (GET):**
    *   A simple health check.
    *   Returns `{"status": "ok"}` if the application started successfully.
    *   Returns `{"status": "unhealthy", "reason": "..."}` if initialization failed.

*   **`/recommend` (POST):**
    *   The main endpoint for getting recommendations.
    *   **Request Body (JSON):** `{ "question": "Your query about SHL assessments..." }`
    *   **Success Response (JSON):** `{ "answer": "The AI-generated recommendation text..." }`
    *   **Error Response (JSON):** `{ "error": "Description of the error..." }` (Status codes 4xx or 5xx)
    *   **Note:** This is a **synchronous** endpoint. The API call will wait until the RAG process (retrieval + LLM call) is complete before returning the response. The *very first* request after a startup will be significantly slower due to the database build happening during initialization.

## Required Secrets / Environment Variables (Set in Hugging Face Space Settings)

*   `GOOGLE_API_KEY`: Your API key for the Google Generative AI service (Mark as Secret).
*   `VECTOR_DB_PATH`: Path inside the container for the ephemeral vector DB (e.g., `/tmp/ephemeral_shl_vector_db`).
*   `JSON_DATA_PATH`: Path inside the container to the source data file (e.g., `data/merged_shl_product_data.json`).
*   `EMBEDDING_MODEL_NAME`: Hugging Face identifier for the embedding model (e.g., `all-MiniLM-L6-v2`).
*   `LLM_MODEL_NAME`: Google Gemini model name (e.g., `gemini-1.5-flash-latest`).

## Local Testing

Refer to previous instructions for setting up a local Python environment, installing requirements, and running `python -m app.main` or using `docker build .` and `docker run ...`. Remember to create a local `.env` file for the `GOOGLE_API_KEY`.
