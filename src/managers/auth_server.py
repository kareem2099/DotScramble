import http.server
import socketserver
import threading
import json
import socket
import secrets
import logging
from urllib.parse import urlparse, parse_qs
from src.config import AUTH_BASE_URL

logger = logging.getLogger(__name__)

class AuthHandler(http.server.BaseHTTPRequestHandler):
    """
    Handles local CORS preflight requests and the POST callback 
    from the DotSuite Next.js web dashboard. Uses BaseHTTPRequestHandler
    to prevent local file disclosure (LFD) vulnerabilities.
    """
    def _get_cors_origin(self) -> str:
        """Verify request Origin and return allowed CORS origin string"""
        origin = self.headers.get('Origin', '')
        allowed_origins = [
            AUTH_BASE_URL,
            'https://dotsuite.app',
            'https://dotsuite.vercel.app',
            'https://dotsuite-core-production.up.railway.app'
        ]
        allowed_origins = [o.rstrip('/') for o in allowed_origins if o]
        if origin and origin.rstrip('/') in allowed_origins:
            return origin
        return 'https://dotsuite.vercel.app'

    def do_OPTIONS(self):
        """Handle CORS preflight"""
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', self._get_cors_origin())
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_POST(self):
        """Handle the actual authentication token callback"""
        if self.path != '/callback':
            self.send_response(404)
            self.end_headers()
            return

        cors_origin = self._get_cors_origin()
        content_length = int(self.headers.get('Content-Length', 0))
        # Prevent Local OOM DoS by capping the allowed content length (API keys are small)
        if content_length > 4096 or content_length <= 0:
            self.send_response(413) # Payload Too Large / Bad Request
            self.send_header('Access-Control-Allow-Origin', cors_origin)
            self.end_headers()
            self.wfile.write(b'{"error": "Invalid payload size"}')
            return

        try:
            post_data = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(post_data)
            received_state = data.get('state')
            api_key = data.get('key')
            
            # Verify the CSRF state token
            if not self.server.auth_manager.verify_state(received_state):
                self.send_response(403)
                self.send_header('Access-Control-Allow-Origin', cors_origin)
                self.end_headers()
                self.wfile.write(b'{"error": "Invalid state token"}')
                return
                
            if not api_key:
                self.send_response(400)
                self.send_header('Access-Control-Allow-Origin', cors_origin)
                self.end_headers()
                self.wfile.write(b'{"error": "Missing key"}')
                return
                
            # Valid callback
            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', cors_origin)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"status": "success"}')
            
            # Trigger the callback in the main thread
            self.server.auth_manager.on_key_received(api_key)
            
        except json.JSONDecodeError:
            self.send_response(400)
            self.send_header('Access-Control-Allow-Origin', cors_origin)
            self.end_headers()
            self.wfile.write(b'{"error": "Invalid JSON"}')

    # Suppress standard logging to stdout to keep terminal clean
    def log_message(self, format, *args):
        logger.debug(f"AuthServer: {format%args}")

class LocalAuthManager:
    """Manages the background HTTP server for receiving seamless auth tokens."""
    
    def __init__(self, callback):
        self.callback = callback
        self.server = None
        self.thread = None
        self.port = None
        self.state_token = None
        
    def start(self):
        """Start the local background server and return port and state token"""
        if self.server:
            self.stop()
            
        self.state_token = secrets.token_urlsafe(32)
        
        # Configure handler
        handler = AuthHandler
        
        # Bind to port 0 to let the OS assign an ephemeral port atomically to prevent conflicts (TOCTOU)
        self.server = socketserver.TCPServer(("127.0.0.1", 0), handler)
        self.port = self.server.server_address[1]
        self.server.auth_manager = self # Inject self into server instance
        
        # Run in background thread
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        
        logger.info(f"Local auth server started on port {self.port}")
        return self.port, self.state_token
        
    def stop(self):
        """Shutdown the local server"""
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
            logger.info("Local auth server stopped")
            
    def verify_state(self, state):
        """Verify the received state token matches the expected one"""
        if not state or not self.state_token:
            return False
        return secrets.compare_digest(state, self.state_token)
        
    def on_key_received(self, key):
        """Called by the AuthHandler when a valid key is received"""
        logger.info("Auth key received successfully via callback")
        # Call the GUI callback
        if self.callback:
            self.callback(key)
        # We can safely stop the server now in a separate thread to avoid HTTP request thread deadlock
        threading.Thread(target=self.stop, daemon=True).start()
