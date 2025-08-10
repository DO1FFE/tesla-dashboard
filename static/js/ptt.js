(function () {
  const socket = io();
  const pttBtn = document.getElementById('ptt-btn');
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
    recorder = new MediaRecorder(mediaStream, { mimeType: 'audio/webm' });
    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) {
        e.data.arrayBuffer().then((buf) => {
          socket.emit('audio_chunk', buf);
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
    const audioBlob = new Blob([data], { type: 'audio/webm' });
    const url = URL.createObjectURL(audioBlob);
    const audio = new Audio(url);
    audio.play();
  });
})();
