"""Fixtures shared across the test modules."""

import threading
from http.server import ThreadingHTTPServer

import pytest

from .lineage_api import handler


@pytest.fixture
def serve():
    running = []

    def _serve(backend):
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler(backend))
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        running.append((httpd, thread))
        return f"http://127.0.0.1:{httpd.server_address[1]}"

    yield _serve

    for httpd, thread in running:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
