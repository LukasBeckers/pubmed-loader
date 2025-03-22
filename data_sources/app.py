# data_sources/backend
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from PubMed import ArticleLoader
import threading
import os
import uuid
import time


app = Flask(__name__)
# Erlaube Anfragen von localhost:5111, deiner Frontend-Domain
CORS(app)  # Enable CORS for all routes


loaders = {}
print("Loaders redifined!")


@app.route("/api/start", methods=["POST"])
def start_loading():
    data = request.json
    search_term = data.get("search_term")
    email = data.get("email")
    max_results = data.get("max_results")

    if not search_term or not email:
        return jsonify({"error": "search_term and email are required"}), 400

    try:
        max_results = int(max_results) if max_results else None
    except ValueError:
        return jsonify({"error": "max_results must be an integer"}), 400

    # Generate a unique ID for this loader
    loader_id = str(uuid.uuid4())
    # Create a new ArticleLoader instance
    loader = ArticleLoader()
    # Store it in the loaders dictionary
    loaders[loader_id] = loader

    # Start the loading process
    loader.load_articles(search_term, email, max_results)

    print("Generated loader ID", loader_id, type(loader_id))

    return jsonify({"message": "Loading started", "loader_id": str(loader_id)}), 200


@app.route("/api/status", methods=["GET"])
def get_status():
    loader_id = request.args.get("loader_id")
    print("loader_id", loader_id, "LOADERS", loaders)

    if not loader_id or loader_id not in loaders:
        print("Request failed!")
        return jsonify({"error": "Invalid loader ID"}), 400

    loader = loaders[loader_id]
    progress = loader.get_progress()
    return jsonify(progress), 200


@app.route("/api/download/json", methods=["GET"])
def download_json():
    loader_id = request.args.get("loader_id")
    if not loader_id or loader_id not in loaders:
        return jsonify({"error": "Invalid loader ID"}), 400

    loader = loaders[loader_id]
    json_path = loader.output_files.get("json")

    if not json_path or not os.path.exists(json_path):
        return jsonify({"error": "JSON file not found"}), 404

    return send_file(json_path, as_attachment=True)


@app.route("/api/download/zip", methods=["GET"])
def download_zip():
    loader_id = request.args.get("loader_id")
    if not loader_id or loader_id not in loaders:
        return jsonify({"error": "Invalid loader ID"}), 400

    loader = loaders[loader_id]
    zip_path = loader.output_files.get("zip")

    if not zip_path or not os.path.exists(zip_path):
        return jsonify({"error": "ZIP file not found"}), 404
    return send_file(zip_path, as_attachment=True)


# Periodically clean up old loaders
def clean_old_loaders():
    while True:
        time.sleep(60)  # Check every minute
        current_time = time.time()
        for loader_id in list(loaders.keys()):
            loader = loaders[loader_id]
            if current_time - loader.last_updated > 13600:  # 1 hour
                del loaders[loader_id]


threading.Thread(target=clean_old_loaders, daemon=True).start()


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
