import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask

# Load the repository-local environment before importing modules that read it.
load_dotenv(Path(__file__).resolve().with_name(".env"))

import config
from web.auth import auth_bp
from web.notebooks_ctx import inject_notebooks
from web.views_api import api_bp
from web.views_ask import ask_bp
from web.views_bookmarks import bookmarks_bp
from web.views_index import index_bp
from web.views_search import search_bp

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.context_processor(inject_notebooks)
app.register_blueprint(auth_bp)
app.register_blueprint(index_bp)
app.register_blueprint(ask_bp)
app.register_blueprint(bookmarks_bp)
app.register_blueprint(search_bp)
app.register_blueprint(api_bp)

if __name__ == "__main__":
    prod = os.environ.get("PROD", "").casefold() in {"1", "true", "yes", "on"}
    app.run(host="0.0.0.0" if prod else "127.0.0.1", debug=not prod)
