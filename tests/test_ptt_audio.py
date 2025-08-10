import pathlib
import sys
import pytest

# Ensure the application root is on the import path when tests run from the
# ``tests`` directory.
sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))
from app import app, socketio


def make_client():
    flask_client = app.test_client()
    flask_client.get('/')  # ensure client_id cookie
    return socketio.test_client(app, flask_test_client=flask_client)


def test_audio_chunk_broadcast():
    speaker = make_client()
    listener = make_client()

    # Speaker requests PTT
    speaker.emit('start_speaking')
    speaker.get_received()
    listener.get_received()

    payload = b'hello'
    speaker.emit('audio_chunk', payload)

    # Speaker should not receive its own audio back
    assert not any(m['name'] == 'play_audio' for m in speaker.get_received())

    # Listener should get the audio chunk
    received = listener.get_received()
    msgs = [m for m in received if m['name'] == 'play_audio']
    assert msgs and msgs[0]['args'][0] == payload
