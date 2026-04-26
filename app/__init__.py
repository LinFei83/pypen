import os
import socketio
from quart import Quart

app = Quart(__name__)
app.config['SECRET_KEY'] = os.urandom(24)

sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins='*',
    ping_timeout=60,
    ping_interval=25,
)

from app.routes import routes
from app import cron

asgi_app = socketio.ASGIApp(sio, app)
