(function () {
  const pttBtn = document.getElementById('ptt-btn');
  if (!pttBtn) {
    return;
  }

  const socket = io();
  let mediaStream;
  let recorder;
  let canSpeak = true;

  async function initMedia() {
    try {
      mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true }
      });
    } catch (err) {
      console.error('Microphone access denied', err);
    }
  }

  initMedia();

  function startRecording() {
    if (!mediaStream) return;
    recorder = new MediaRecorder(mediaStream, { mimeType: 'audio/webm' });
    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) {
        socket.emit('audio_chunk', e.data);
      }
    };
    recorder.start(250);
  }

  function stopRecording() {
    if (recorder && recorder.state !== 'inactive') {
      recorder.stop();
    }
  }

  pttBtn.addEventListener('mousedown', () => {
    if (canSpeak) {
      socket.emit('start_speaking');
    }
  });

  pttBtn.addEventListener('mouseup', () => {
    socket.emit('stop_speaking');
    stopRecording();
  });

  pttBtn.addEventListener('touchstart', (e) => {
    e.preventDefault();
    if (canSpeak) {
      socket.emit('start_speaking');
    }
  });

  pttBtn.addEventListener('touchend', (e) => {
    e.preventDefault();
    socket.emit('stop_speaking');
    stopRecording();
  });

  socket.on('start_accepted', () => {
    startRecording();
  });

  socket.on('start_denied', () => {
    // speaking denied
  });

  socket.on('lock_ptt', () => {
    canSpeak = false;
    pttBtn.disabled = true;
  });

  socket.on('unlock_ptt', () => {
    canSpeak = true;
    pttBtn.disabled = false;
  });

  socket.on('play_audio', (data) => {
    const audioBlob = new Blob([data], { type: 'audio/webm' });
    const url = URL.createObjectURL(audioBlob);
    const audio = new Audio(url);
    audio.play();
  });
})();
