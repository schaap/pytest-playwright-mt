# Copyright 2026 Thomas Schaap
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
A small threaded web server serving static files and some dynamic content.

Typical usage::

    from webserver import WebServer

    with WebServer() as server:
        print(server.url)  # http://127.0.0.1:<port>/
"""

from __future__ import annotations

import logging
from functools import partial
from html import escape
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock, Thread
from typing import TYPE_CHECKING, Any, Self
from urllib.parse import urlparse

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable, Generator
    from types import TracebackType

log = logging.getLogger(__name__)


class _State:
    """State shared between request handler threads."""

    def __init__(self) -> None:
        self.counter = 0
        self.lock = Lock()

    def increment_counter(self) -> int:
        """
        Increment the counter.

        :returns: The new counter value.
        """
        with self.lock:
            self.counter += 1
            return self.counter


class _ThreadingHTTPServer(ThreadingHTTPServer):
    """
    A threading HTTP server that carries the shared state and configuration.
    """

    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        server_address: tuple[str, int],
        request_handler: Callable[..., SimpleHTTPRequestHandler],
        *,
        verbose: bool,
    ) -> None:
        self.state = _State()
        self.verbose = verbose
        super().__init__(server_address, request_handler)


class _RequestHandler(SimpleHTTPRequestHandler):
    """
    Serve static files, intercept specific routes to generate dynamic content.
    """

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/counter":
            self._send_html(self._counter_page())
        else:
            super().do_GET()

    # ruff: ignore[ANN401, A002, PLR6301]  # Method override, this is the original signature
    def log_message(self, format: str, *args: Any) -> None:
        # Log to a log instead of stderr, so it only shows up in pytest traces when needed
        log.warning(format, *args)

    def _send_html(self, content: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        """
        Send an HTML response.

        :param content: The content to send.
        :param status: The HTTP status to report.
        """
        payload = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _counter_page(self) -> str:
        """
        Render the content for a request to the counter page.

        This increases the displayed counter.

        :returns: The HTML page to send to the client.
        """
        assert isinstance(self.server, _ThreadingHTTPServer)
        value = self.server.state.increment_counter()
        body = (
            f'<p>This page has been viewed <span data-testid="counter">{value}</span> '
            f'time{"s" if value != 1 else ""}.</p><p><a href="/counter">Increment again</a></p>'
        )
        return WebServer.basic_html("Counter", body)


class WebServer:
    """
    A simple HTTP server for testing. Based on ``SimpleHTTPRequestHandler``, but including some dynamic pages.

    Static files are served from ``pages_dir``. The dynamic pages are:

    - ``/counter``: increments and displays a shared counter.
    """

    def __init__(
        self,
        pages_dir: str | Path,
        host: str = "127.0.0.1",
        port: int = 0,
        *,
        verbose: bool = False,
    ) -> None:
        """
        Initialize a web server. Enter its context manager to actually run the web server.

        :param pages_dir: The directory from which static files are served.
        :param host: The address to bind to.
        :param port: The port to bind to. Use ``0`` to let the operating system choose a free port.
        :param verbose: Whether to log requests to stderr.
        """
        self._host = host
        self._port = port
        self._pages_dir = Path(pages_dir)
        self._verbose = verbose
        self._httpd: _ThreadingHTTPServer | None = None
        self._thread: Thread | None = None

    @property
    def host(self) -> str:
        """The address the server is bound to."""
        return self._host

    @property
    def port(self) -> int:
        """The port the server is bound to. If the server is running, this is the actual port in use."""
        if self._httpd is not None:
            return self._httpd.server_address[1]
        return self._port

    @property
    def url(self) -> str:
        """
        The base URL of the running server, with a trailing slash.

        :raises RuntimeError: If the server has not been started.
        """
        if self._httpd is None:
            raise RuntimeError("The server is not running. Call start() first.")

        host = self._host
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"  # IPv6 literal
        return f"http://{host}:{self.port}/"

    @property
    def pages_dir(self) -> Path:
        """The directory from which static files are served."""
        return self._pages_dir

    @staticmethod
    def basic_html(title: str, body: str) -> str:
        """
        Write a very basic HTML page.

        This is just a convenience for wrapping simple HTML into a valid page.

        :param title: The title of the page. This will also be shown in an ``<h1></h1>`` above the ``body``.
        :param body: The body of the page to write.
        :returns: A minimal but complete HTML page with the given title and body.
        """
        return (
            '<!DOCTYPE html><html lang="en">'
            f'<head><meta charset="utf-8"><title>{escape(title)}</title></head>'
            f"<body><h1>{escape(title)}</h1>{body}</body>"
            "</html>"
        )

    def _start(self) -> Self:
        """
        Start serving requests in a background thread.

        :returns: This server, so calls can be chained.
        :raises RuntimeError: If the server is already running.
        :raises FileNotFoundError: If the pages directory does not exist.
        """
        if self._httpd is not None:
            raise RuntimeError("The server is already running.")
        if not self._pages_dir.is_dir():
            raise FileNotFoundError(f"Pages directory does not exist: {self._pages_dir}")

        handler = partial(_RequestHandler, directory=str(self._pages_dir))
        httpd = _ThreadingHTTPServer((self._host, self._port), handler, verbose=self._verbose)
        thread = Thread(target=httpd.serve_forever, name="webserver", daemon=False)
        try:
            thread.start()
        except BaseException:
            httpd.server_close()
            raise

        self._httpd = httpd
        self._thread = thread
        return self

    def _stop(self) -> None:
        """
        Stop serving requests and release the port. Does nothing if the server is not running.
        """
        httpd = self._httpd
        thread = self._thread
        if httpd is None:
            return

        self._httpd = None
        self._thread = None
        httpd.shutdown()
        httpd.server_close()
        if thread is not None:
            thread.join(timeout=5)

    def __enter__(self) -> Self:
        return self._start()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        self._stop()
        return None


@pytest.fixture
def web_server(tmp_path: Path) -> Generator[WebServer, None, None]:
    """
    Fixture for a simple webserver.

    Static HTML will be served from an initially (almost) empty temporary directory. Dynamic content is served as
    programmatically defined in the web server classes.

    To prevent some spurious errors, an empty ``favicon.ico`` is written into the temporary directory.

    :yields: The running web server.
    """
    html_dir = tmp_path / "static_html"
    html_dir.mkdir()
    (html_dir / "favicon.ico").write_bytes(b"")
    with WebServer(html_dir) as server:
        yield server
