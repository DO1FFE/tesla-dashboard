import pathlib
import sys
import pytest

# Ensure the application root is on the import path when tests run from the
# ``tests`` directory.
sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))
import app as app_module

app = app_module.app
socketio = app_module.socketio


def make_client():
    flask_client = app.test_client()
    flask_client.get('/')  # ensure client_id cookie
    return socketio.test_client(app, flask_test_client=flask_client)


@pytest.fixture(autouse=True)
def reset_ptt():
    app_module.current_speaker_id = None
    if app_module.ptt_timer:
        app_module.ptt_timer.cancel()
        app_module.ptt_timer = None
    app_module.audio_buffer.clear()
    yield
    app_module.current_speaker_id = None
    if app_module.ptt_timer:
        app_module.ptt_timer.cancel()
        app_module.ptt_timer = None
    app_module.audio_buffer.clear()


def test_audio_chunk_broadcast():
    speaker = make_client()
    listener = make_client()

    # Speaker requests PTT
    speaker.emit('start_speaking')
    speaker.get_received()
    listener.get_received()

    payload = b'hello'
    speaker.emit('audio_chunk', payload)
    # No audio should be broadcast until speaking stops
    assert not any(m['name'] == 'play_audio' for m in listener.get_received())

    speaker.emit('stop_speaking')

    # Speaker should not receive its own audio back
    assert not any(m['name'] == 'play_audio' for m in speaker.get_received())

    # Listener should get the buffered audio chunk
    received = listener.get_received()
    msgs = [m for m in received if m['name'] == 'play_audio']
    assert msgs and msgs[0]['args'][0] == payload


def test_audio_chunk_multiple_listeners():
    speaker = make_client()
    listener1 = make_client()
    listener2 = make_client()

    speaker.emit('start_speaking')
    speaker.get_received()
    listener1.get_received()
    listener2.get_received()

    payload = b'data'
    speaker.emit('audio_chunk', payload)
    # No audio should be broadcast until speaking stops
    assert not any(m['name'] == 'play_audio' for m in listener1.get_received())
    assert not any(m['name'] == 'play_audio' for m in listener2.get_received())

    speaker.emit('stop_speaking')

    msgs1 = [m for m in listener1.get_received() if m['name'] == 'play_audio']
    msgs2 = [m for m in listener2.get_received() if m['name'] == 'play_audio']

    assert msgs1 and msgs1[0]['args'][0] == payload
    assert msgs2 and msgs2[0]['args'][0] == payload
