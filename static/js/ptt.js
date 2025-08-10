(function () {
  const socket = io();
  const pttBtn = document.getElementById('ptt-btn');
  const audioCtx = new (window.AudioContext || window.webkitAudioContext)();

  function playPing() {
    return audioCtx.resume().then(() => {
      return new Promise((resolve) => {
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.type = 'sine';
        osc.frequency.value = 880;
        gain.gain.value = 1.0;
        osc.connect(gain);
        gain.connect(audioCtx.destination);
        osc.start();
        osc.stop(audioCtx.currentTime + 0.1);
        osc.onended = resolve;
      });
    });
  }
  let clientId;
  let mediaStream;
  let recorder;
  let canSpeak = true;
  let totTimer;

  function clearTot() {
    if (totTimer) {
      clearTimeout(totTimer);
      totTimer = null;
    }
  }

  async function initMedia() {
    try {
      mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true }
      });
    } catch (err) {
      console.error('Microphone access denied', err);
    }
  }

  function startRecording() {
    if (!mediaStream) return;
    recorder = new MediaRecorder(mediaStream, {
      mimeType: 'audio/webm;codecs=opus'
    });
    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) {
        e.data.arrayBuffer().then((buf) => {
          // Send a typed array so that the Python backend receives the raw
          // bytes without any additional encoding.
          socket.emit('audio_chunk', new Uint8Array(buf));
        });
      }
    };
    recorder.start(250);
  }

  function stopRecording() {
    if (recorder && recorder.state !== 'inactive') {
      recorder.stop();
    }
  }

  if (pttBtn) {
    initMedia();

    pttBtn.addEventListener('mousedown', () => {
      if (canSpeak) {
        pttBtn.classList.add('active-btn');
        socket.emit('start_speaking');
      }
    });

    pttBtn.addEventListener('mouseup', () => {
      socket.emit('stop_speaking');
      stopRecording();
      pttBtn.classList.remove('active-btn');
      clearTot();
    });

    pttBtn.addEventListener('touchstart', (e) => {
      e.preventDefault();
      if (canSpeak) {
        pttBtn.classList.add('active-btn');
        socket.emit('start_speaking');
      }
    });

    pttBtn.addEventListener('touchend', (e) => {
      e.preventDefault();
      socket.emit('stop_speaking');
      stopRecording();
      pttBtn.classList.remove('active-btn');
      clearTot();
    });
  }

  socket.on('your_id', (data) => {
    clientId = data.id;
  });

  socket.on('start_accepted', () => {
    startRecording();
    clearTot();
    totTimer = setTimeout(() => {
      socket.emit('stop_speaking');
      stopRecording();
      if (pttBtn) {
        pttBtn.classList.remove('active-btn');
      }
      totTimer = null;
    }, 30000);
  });

  socket.on('start_denied', () => {
    if (pttBtn) {
      pttBtn.classList.remove('active-btn');
    }
  });

  socket.on('lock_ptt', () => {
    canSpeak = false;
    if (pttBtn) {
      pttBtn.disabled = true;
      pttBtn.classList.remove('active-btn');
    }
    clearTot();
  });

  socket.on('unlock_ptt', () => {
    canSpeak = true;
    if (pttBtn) {
      pttBtn.disabled = false;
      pttBtn.classList.remove('active-btn');
    }
    clearTot();
  });

  socket.on('play_audio', (data) => {
    // Reconstruct the binary data into a playable blob.  The server forwards
    // a ``Uint8Array`` which we turn back into a Blob before playback.
    const chunk = new Uint8Array(data);
    if (!chunk.length) {
      console.error('Received empty audio data');
      return;
    }
    const audioBlob = new Blob([chunk], { type: 'audio/webm;codecs=opus' });
    const url = URL.createObjectURL(audioBlob);
    const audio = new Audio(url);
    audio.volume = 1.0;
    audio.addEventListener('error', (e) => console.error('Audio element error', e));
    const playMain = () => {
      audio.play().catch((err) => console.error('Audio playback failed', err));
      audio.addEventListener('ended', () => URL.revokeObjectURL(url));
    };
    playPing().then(playMain).catch((err) => {
      console.error('Ping playback failed', err);
      playMain();
    });
  });
})();
