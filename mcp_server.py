import os
import http.server
import pathlib
import threading

PORT = 8765  # default; avoids conflict with ChromaDB on 8000


def _make_handler(serve_dir: str):
    _root = pathlib.Path(serve_dir).resolve()

    class FileHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(_root), **kwargs)

        def do_GET(self):
            """Handle GET request to list files or read a file."""
            if self.path == "/list":
                self.list_files()
            else:
                super().do_GET()

        def do_POST(self):
            """Handle POST request to write to a file."""
            content_length = int(self.headers["Content-Length"])
            post_data = self.rfile.read(content_length)
            filename = self._safe_path(self.path.strip("/"))
            if filename is None:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Invalid path.")
                return
            with open(filename, "wb") as f:
                f.write(post_data)
            self.send_response(201)
            self.end_headers()
            self.wfile.write(f"File {filename} created/updated successfully.".encode())

        def do_DELETE(self):
            """Handle DELETE request to remove a file."""
            filename = self._safe_path(self.path.strip("/"))
            if filename is None:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Invalid path.")
                return
            if os.path.exists(filename):
                os.remove(filename)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(f"File {filename} deleted successfully.".encode())
            else:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(f"File {filename} not found.".encode())

        def list_files(self):
            """List all files in the served directory."""
            files = os.listdir(str(_root))
            self.send_response(200)
            self.end_headers()
            self.wfile.write("\n".join(files).encode())

        def _safe_path(self, rel: str):
            """Resolve rel relative to serve_dir; return None on path traversal."""
            try:
                target = (_root / rel).resolve()
                if not str(target).startswith(str(_root)):
                    return None
                return str(target)
            except Exception:
                return None

        def log_message(self, fmt, *args):
            pass  # silence access log spam

    return FileHandler


def start(port: int = PORT, directory: str | None = None) -> http.server.HTTPServer:
    """
    Start the MCP filesystem server in a background daemon thread.
    Binds to 127.0.0.1 (localhost only).
    Returns the HTTPServer instance; call .shutdown() to stop.
    """
    if directory is None:
        directory = os.getcwd()
    directory = str(pathlib.Path(directory).resolve())
    httpd = http.server.HTTPServer(("127.0.0.1", port), _make_handler(directory))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def run(port: int = PORT, directory: str | None = None) -> None:
    """Block until interrupted (for direct command-line use)."""
    if directory is None:
        directory = os.getcwd()
    directory = str(pathlib.Path(directory).resolve())
    print(f"Starting MCP server on port {port}, serving {directory}...")
    http.server.HTTPServer(("", port), _make_handler(directory)).serve_forever()


if __name__ == "__main__":
    run()
