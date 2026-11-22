"""Serve the shared companion on loopback (Python 3, no dependencies)."""
from argparse import ArgumentParser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1] / "board/unfreeze-uno-q/python/web"
    handler = partial(SimpleHTTPRequestHandler, directory=str(root))
    with ThreadingHTTPServer(("127.0.0.1", args.port), handler) as server:
        print(f"Unfreeze companion: http://127.0.0.1:{server.server_port}/", flush=True)
        server.serve_forever()

