import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timedelta
import time

# Thread-safe list to track recent log events
_last_log_time = 0.0
_last_error_time = 0.0
_log_lock = threading.Lock()

class HealthLogHandler(logging.Handler):
    def emit(self, record):
        global _last_log_time, _last_error_time
        ts = record.created  # float: seconds since epoch
        with _log_lock:
            _last_log_time = ts
            if record.levelno >= logging.ERROR:
                _last_error_time = ts

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != '/healthz':
            self.send_response(404)
            self.end_headers()
            return

        now = time.time()
        with _log_lock:
            healthy = (
                (now - _last_log_time <= 300) and  # some recent log
                (_last_log_time > _last_error_time)  # and it’s not an error or worse
            )

        if healthy:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK\n")
        else:
            self.send_response(503)
            self.end_headers()
            self.wfile.write(b"Service Unavailable\n")

    def log_message(self, format, *args):
        return  # Suppress HTTP server logging

def _start_server():
    server = HTTPServer(('localhost', 8181), HealthCheckHandler)
    server.serve_forever()

# Start HTTP server in a background thread
threading.Thread(target=_start_server, daemon=True).start()

# Add our custom log handler to the root logger
logging.getLogger().addHandler(HealthLogHandler())