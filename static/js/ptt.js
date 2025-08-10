(function () {
  const socket = io();
  const pttBtn = document.getElementById('ptt-btn');
  const levelMeter = document.getElementById('audio-level');
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
  let micSource;
  let micAnalyser;
  let levelReq;
  let lastPing = 0;

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
    audioCtx.resume().catch((err) => console.error('Audio context resume failed', err));
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
    // Use a small timeslice so that audio chunks are delivered frequently,
    // enabling smoother streaming on the receiving side.
    recorder.start(100);
  }

  function stopRecording() {
    if (recorder && recorder.state !== 'inactive') {
      recorder.stop();
    }
    stopLevelMonitoring();
  }

  function startLevelMonitoring() {
    if (!mediaStream || !levelMeter) return;
    audioCtx.resume().catch((err) => console.error('Audio context resume failed', err));
    micSource = audioCtx.createMediaStreamSource(mediaStream);
    micAnalyser = audioCtx.createAnalyser();
    micAnalyser.fftSize = 256;
    micSource.connect(micAnalyser);
    const data = new Uint8Array(micAnalyser.fftSize);
    const update = () => {
      micAnalyser.getByteTimeDomainData(data);
      let sum = 0;
      for (let i = 0; i < data.length; i++) {
        const v = (data[i] - 128) / 128;
        sum += v * v;
      }
      const rms = Math.sqrt(sum / data.length);
      levelMeter.value = rms;
      levelReq = requestAnimationFrame(update);
    };
    update();
  }

  function stopLevelMonitoring() {
    if (levelReq) {
      cancelAnimationFrame(levelReq);
      levelReq = null;
    }
    if (micSource) {
      micSource.disconnect();
      micSource = null;
    }
    if (micAnalyser) {
      micAnalyser.disconnect();
      micAnalyser = null;
    }
    if (levelMeter) {
      levelMeter.value = 0;
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
    // Play a short ping before transmission starts so the speaker also
    // receives an audible indication that the channel is live.  The ping is
    // played locally and not forwarded to other clients.
    playPing()
      .catch((err) => console.error('Ping playback failed', err))
      .finally(() => {
        startRecording();
        startLevelMonitoring();
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
    // Give listeners a short ping indicating that another user started
    // transmitting.  Errors are logged but should not interrupt normal
    // operation.  A small time buffer avoids multiple pings when the
    // server emits duplicate lock events in quick succession.
    const now = Date.now();
    if (now - lastPing > 500) {
      lastPing = now;
      playPing().catch((err) => console.error('Ping playback failed', err));
    }
  });

  socket.on('unlock_ptt', () => {
    canSpeak = true;
    if (pttBtn) {
      pttBtn.disabled = false;
      pttBtn.classList.remove('active-btn');
    }
    clearTot();
  });

  // Maintain a running timestamp so that received chunks can be scheduled
  // back-to-back without gaps.  ``playbackTime`` is initialised with the
  // current context time and advanced by the duration of each decoded chunk.
  let playbackTime = audioCtx.currentTime;
  // Promise chain to ensure chunks are decoded and scheduled sequentially.
  let playbackChain = Promise.resolve();

  socket.on('play_audio', (data) => {
    // Normalise ``data`` into a ``Uint8Array`` irrespective of the transport
    // used by Socket.IO.
    let chunk;
    if (data instanceof ArrayBuffer) {
      chunk = new Uint8Array(data);
    } else if (data instanceof Uint8Array) {
      chunk = data;
    } else if (data && data.buffer instanceof ArrayBuffer) {
      chunk = new Uint8Array(data.buffer);
    } else if (data && Array.isArray(data.data)) {
      chunk = new Uint8Array(data.data);
    } else {
      try {
        chunk = new Uint8Array(data);
      } catch (err) {
        console.error('Unsupported audio data format', err);
        return;
      }
    }
    if (!chunk.length) {
      console.error('Received empty audio data');
      return;
    }

    // ``decodeAudioData`` expects an ``ArrayBuffer`` containing the encoded
    // audio.  ``slice`` ensures the view only covers the transmitted bytes.
    const ab = chunk.buffer.slice(
      chunk.byteOffset,
      chunk.byteOffset + chunk.byteLength
    );

    // Queue decoding and playback so chunks are processed in order.  This
    // avoids gaps or stutter caused by out-of-order Promise resolution when
    // ``decodeAudioData`` completes at different times for each chunk.
    playbackChain = playbackChain
      .catch(() => {})
      .then(() => audioCtx.decodeAudioData(ab))
      .then((buffer) => {
        const source = audioCtx.createBufferSource();
        source.buffer = buffer;
        const analyser = audioCtx.createAnalyser();
        analyser.fftSize = 256;
        source.connect(analyser);
        analyser.connect(audioCtx.destination);
        const dataArr = new Uint8Array(analyser.fftSize);
        const updateLevel = () => {
          analyser.getByteTimeDomainData(dataArr);
          let sum = 0;
          for (let i = 0; i < dataArr.length; i++) {
            const v = (dataArr[i] - 128) / 128;
            sum += v * v;
          }
          const rms = Math.sqrt(sum / dataArr.length);
          if (levelMeter) levelMeter.value = rms;
          req = requestAnimationFrame(updateLevel);
        };
        let req = requestAnimationFrame(updateLevel);
        source.onended = () => {
          cancelAnimationFrame(req);
          if (levelMeter) levelMeter.value = 0;
        };
        // Schedule the chunk immediately after the previous one.  Maintain a
        // small lead over ``currentTime`` so late chunks do not cause audible
        // gaps.
        if (playbackTime < audioCtx.currentTime + 0.05) {
          playbackTime = audioCtx.currentTime + 0.05;
        }
        source.start(playbackTime);
        playbackTime += buffer.duration;
      })
      .catch((err) => console.error('Audio decode failed', err));
  });
})();
