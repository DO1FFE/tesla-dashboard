import base64
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
def reset_ptt(monkeypatch):
    monkeypatch.setattr(app_module, "is_ptt_enabled", lambda: True)
    monkeypatch.setattr(app_module, "is_ptt_recording_enabled", lambda: False)
    app_module.current_speaker_id = None
    app_module.ptt_speaker_info = {}
    app_module.ptt_started_at = None
    if app_module.ptt_timer:
        app_module.ptt_timer.cancel()
        app_module.ptt_timer = None
    app_module.audio_buffer.clear()
    app_module.ptt_diagnostics.clear()
    yield
    app_module.current_speaker_id = None
    app_module.ptt_speaker_info = {}
    app_module.ptt_started_at = None
    if app_module.ptt_timer:
        app_module.ptt_timer.cancel()
        app_module.ptt_timer = None
    app_module.audio_buffer.clear()
    app_module.ptt_diagnostics.clear()


def auth_headers(user="test@example.org", password="geheim"):
    token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {token}"}


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
    assert msgs
    wiedergabe = msgs[0]['args'][0]
    assert wiedergabe['audio'] == payload
    assert wiedergabe['content_type'] == 'audio/webm'


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

    assert msgs1 and msgs1[0]['args'][0]['audio'] == payload
    assert msgs2 and msgs2[0]['args'][0]['audio'] == payload


def test_ptt_diagnostics_are_reported():
    flask_client = app.test_client()
    flask_client.get('/')
    client = socketio.test_client(app, flask_test_client=flask_client)

    client.emit('ptt_diagnostics', {
        'browser': 'Tesla QtCarBrowser',
        'aufnahme_unterstützt': True,
        'gewählter_mime_type': 'audio/webm;codecs=opus',
        'mime_types': {
            'audio/webm;codecs=opus': True,
            'audio/mp4': False,
        },
    })

    response = flask_client.get('/api/ptt/diagnostics')
    data = response.get_json()

    assert response.status_code == 200
    assert len(data['diagnostics']) == 1
    diagnose = data['diagnostics'][0]
    assert diagnose['diagnostics']['browser'] == 'Tesla QtCarBrowser'
    assert diagnose['diagnostics']['mime_types']['audio/webm;codecs=opus'] is True


def test_connect_receives_lock_when_other_client_speaks():
    app_module.current_speaker_id = 'anderer-client'

    client = make_client()
    received = client.get_received()

    assert any(message['name'] == 'lock_ptt' for message in received)


def test_ptt_recording_is_saved_and_playable(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "PTT_RECORDINGS_DIR", str(tmp_path))
    monkeypatch.setattr(app_module, "is_ptt_recording_enabled", lambda: True)
    monkeypatch.setattr(app_module, "PTT_RECORDING_MIN_SECONDS", 0.0)
    monkeypatch.setenv("TESLA_EMAIL", "test@example.org")
    monkeypatch.setenv("TESLA_PASSWORD", "geheim")

    speaker = make_client()
    payload = b'aufnahmedaten'

    speaker.emit('start_speaking', {
        'mime_type': 'audio/webm;codecs=opus',
        'codec': 'WebM/Opus',
    })
    speaker.get_received()
    speaker.emit('audio_chunk', payload)
    speaker.emit('stop_speaking')

    aufnahmen = app_module._ptt_aufnahmen_laden()
    assert len(aufnahmen) == 1
    assert aufnahmen[0]['size_bytes'] == len(payload)
    assert aufnahmen[0]['content_type'] == 'audio/webm'

    flask_client = app.test_client()
    page = flask_client.get('/ptt', headers=auth_headers())
    assert page.status_code == 200
    assert 'PTT-Übertragungen'.encode('utf-8') in page.data

    audio = flask_client.get(
        f"/ptt/audio/{aufnahmen[0]['id']}",
        headers=auth_headers(),
    )
    assert audio.status_code == 200
    assert audio.data == payload
    assert audio.mimetype == 'audio/webm'


def test_ptt_recording_skips_zero_second_audio(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "PTT_RECORDINGS_DIR", str(tmp_path))
    monkeypatch.setattr(app_module, "is_ptt_recording_enabled", lambda: True)
    monkeypatch.setattr(app_module, "PTT_RECORDING_MIN_SECONDS", 1.0)

    speaker = make_client()
    speaker.emit('start_speaking', {
        'mime_type': 'audio/webm;codecs=opus',
        'codec': 'WebM/Opus',
    })
    speaker.get_received()
    speaker.emit('audio_chunk', b'zu-kurz')
    speaker.emit('stop_speaking')

    assert app_module._ptt_aufnahmen_laden() == []


def test_ptt_cleanup_removes_zero_second_audio(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "PTT_RECORDINGS_DIR", str(tmp_path))
    monkeypatch.setattr(app_module, "PTT_RECORDING_MIN_SECONDS", 1.0)
    audio_file = tmp_path / "kurz.webm"
    audio_file.write_bytes(b'kurz')
    app_module._ptt_index_schreiben_ungesperrt([
        {
            'id': 'kurz',
            'filename': 'kurz.webm',
            'timestamp': 9999999999,
            'duration_seconds': 0.4,
        }
    ])

    assert app_module._ptt_aufnahmen_laden() == []
    assert not audio_file.exists()
