(function () {
  const socket = io();
  const pttBtn = document.getElementById('ptt-btn');
  const pttDesc = document.getElementById('ptt-desc');
  const levelMeter = document.getElementById('audio-level');
  const pttDiagnosticsList = document.getElementById('ptt-diagnostics-list');
  const pttDiagnosticsStatus = document.getElementById('ptt-diagnostics-status');
  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  const legacyGetUserMedia = navigator.getUserMedia ||
    navigator.webkitGetUserMedia ||
    navigator.mozGetUserMedia ||
    navigator.msGetUserMedia;
  const hasModernGetUserMedia = !!(
    navigator.mediaDevices &&
    typeof navigator.mediaDevices.getUserMedia === 'function'
  );
  const hasGetUserMedia = hasModernGetUserMedia || !!legacyGetUserMedia;
  const hasMediaRecorder = typeof MediaRecorder !== 'undefined';
  const pttMimeTypen = [
    { typ: 'audio/webm;codecs=opus', name: 'WebM/Opus' },
    { typ: 'audio/webm;codecs=pcm', name: 'WebM/PCM' },
    { typ: 'audio/webm', name: 'WebM' },
    { typ: 'audio/ogg;codecs=opus', name: 'Ogg/Opus' },
    { typ: 'audio/ogg', name: 'Ogg' },
    { typ: 'audio/mp4;codecs=mp4a.40.2', name: 'MP4/AAC' },
    { typ: 'audio/mp4', name: 'MP4' },
    { typ: 'audio/aac', name: 'AAC' },
    { typ: 'audio/wav', name: 'WAV' },
    { typ: 'audio/wave', name: 'Wave' }
  ];

  let audioCtx = null;
  let clientId;
  let mediaStream;
  let mediaPromise;
  let recorder;
  let canSpeak = true;
  let recordingSupported = hasGetUserMedia && hasMediaRecorder;
  let startRequested = false;
  let pendingStopAfterStart = false;
  let speakingActive = false;
  let stoppingRecorder = false;
  let pendingChunkSends = [];
  let totTimer;
  let micSource;
  let micAnalyser;
  let micSilencer;
  let levelReq;
  let lastPing = 0;
  let playbackUnlocked = false;
  let microphoneStatus = 'nicht angefragt';
  let lastChosenMimeType = '';

  function setDescription(text) {
    if (pttDesc) {
      pttDesc.textContent = text;
    }
  }

  function istMimeTypUnterstützt(mimeType) {
    if (!hasMediaRecorder || typeof MediaRecorder.isTypeSupported !== 'function') {
      return null;
    }
    try {
      return MediaRecorder.isTypeSupported(mimeType);
    } catch (err) {
      return false;
    }
  }

  function waehleMimeType() {
    if (!hasMediaRecorder || typeof MediaRecorder.isTypeSupported !== 'function') {
      return '';
    }
    for (let i = 0; i < pttMimeTypen.length; i++) {
      if (istMimeTypUnterstützt(pttMimeTypen[i].typ)) {
        return pttMimeTypen[i].typ;
      }
    }
    return '';
  }

  function codecName(mimeType) {
    for (let i = 0; i < pttMimeTypen.length; i++) {
      if (pttMimeTypen[i].typ === mimeType) {
        return pttMimeTypen[i].name;
      }
    }
    return mimeType || '';
  }

  function jaNein(wert) {
    if (wert === null) {
      return 'nicht prüfbar';
    }
    return wert ? 'ja' : 'nein';
  }

  function pttDiagnoseDaten(grund) {
    const mimeTypes = {};
    for (let i = 0; i < pttMimeTypen.length; i++) {
      mimeTypes[pttMimeTypen[i].typ] = istMimeTypUnterstützt(pttMimeTypen[i].typ);
    }
    const gewählterTyp = lastChosenMimeType || waehleMimeType();
    return {
      grund: grund,
      client_id: clientId || '',
      browser: navigator.userAgent || '',
      platform: navigator.platform || '',
      sprache: navigator.language || '',
      secure_context: window.isSecureContext === true,
      audio_context: {
        vorhanden: !!AudioContextClass,
        zustand: audioCtx ? audioCtx.state : 'nicht erstellt',
        sample_rate: audioCtx ? audioCtx.sampleRate : null
      },
      get_user_media: {
        modern: hasModernGetUserMedia,
        legacy: !!legacyGetUserMedia
      },
      media_recorder: {
        vorhanden: hasMediaRecorder,
        is_type_supported: hasMediaRecorder &&
          typeof MediaRecorder.isTypeSupported === 'function'
      },
      aufnahme_unterstützt: !!recordingSupported,
      mikrofon: microphoneStatus,
      wiedergabe_aktiviert: !!playbackUnlocked,
      gewählter_mime_type: gewählterTyp,
      gewählter_codec: codecName(gewählterTyp) || 'Browser-Standard',
      mime_types: mimeTypes
    };
  }

  function pttDiagnoseAnzeigen(diagnose) {
    if (pttDiagnosticsStatus) {
      if (diagnose.aufnahme_unterstützt) {
        pttDiagnosticsStatus.textContent = diagnose.gewählter_codec;
      } else {
        pttDiagnosticsStatus.textContent = 'Aufnahme nicht verfügbar';
      }
    }
    if (!pttDiagnosticsList) {
      return;
    }
    const unterstützteTypen = [];
    for (let i = 0; i < pttMimeTypen.length; i++) {
      const typ = pttMimeTypen[i].typ;
      if (diagnose.mime_types[typ] === true) {
        unterstützteTypen.push(pttMimeTypen[i].name + ' (' + typ + ')');
      }
    }
    const rows = [
      ['Browser', diagnose.browser || 'unbekannt'],
      ['AudioContext', jaNein(diagnose.audio_context.vorhanden) + ', ' +
        diagnose.audio_context.zustand],
      ['Mikrofon-API', 'modern: ' + jaNein(diagnose.get_user_media.modern) +
        ', legacy: ' + jaNein(diagnose.get_user_media.legacy)],
      ['MediaRecorder', jaNein(diagnose.media_recorder.vorhanden) +
        ', Codec-Prüfung: ' + jaNein(diagnose.media_recorder.is_type_supported)],
      ['Gewählter Codec', diagnose.gewählter_codec +
        (diagnose.gewählter_mime_type ? ' (' + diagnose.gewählter_mime_type + ')' : '')],
      ['Unterstützte Codecs', unterstützteTypen.length ?
        unterstützteTypen.join(', ') : 'keine erkannt'],
      ['Mikrofon', diagnose.mikrofon],
      ['Audiofreigabe', jaNein(diagnose.wiedergabe_aktiviert)],
      ['HTTPS/Secure Context', jaNein(diagnose.secure_context)]
    ];
    while (pttDiagnosticsList.firstChild) {
      pttDiagnosticsList.removeChild(pttDiagnosticsList.firstChild);
    }
    for (let i = 0; i < rows.length; i++) {
      const dt = document.createElement('dt');
      const dd = document.createElement('dd');
      dt.textContent = rows[i][0];
      dd.textContent = rows[i][1];
      pttDiagnosticsList.appendChild(dt);
      pttDiagnosticsList.appendChild(dd);
    }
  }

  function pttDiagnoseMelden(grund) {
    const diagnose = pttDiagnoseDaten(grund);
    pttDiagnoseAnzeigen(diagnose);
    if (socket && typeof socket.emit === 'function') {
      socket.emit('ptt_diagnostics', diagnose);
    }
  }

  if (!AudioContextClass) {
    recordingSupported = false;
    if (pttBtn) {
      pttBtn.disabled = true;
      pttBtn.classList.remove('active-btn');
    }
    if (pttDesc) {
      pttDesc.textContent = 'Push-to-Talk wird von diesem Browser nicht unterstützt.';
    }
    pttDiagnoseMelden('AudioContext fehlt');
    console.warn('PTT disabled: AudioContext is not available in this browser.');
    return;
  }

  audioCtx = new AudioContextClass();

  function setButtonAvailable() {
    if (!pttBtn) {
      return;
    }
    if (!recordingSupported) {
      pttBtn.disabled = false;
      pttBtn.textContent = 'Audio aktivieren';
      pttBtn.classList.remove('active-btn');
      pttBtn.classList.remove('ptt-locked');
      pttBtn.removeAttribute('title');
      setDescription('Audioempfang aktivieren. Mikrofonaufnahme ist in diesem Browser nicht verfügbar.');
      return;
    }
    pttBtn.disabled = !canSpeak;
    if (canSpeak) {
      pttBtn.textContent = 'Push to Talk';
      pttBtn.classList.remove('ptt-locked');
      pttBtn.removeAttribute('title');
    } else {
      pttBtn.textContent = 'Belegt';
      pttBtn.classList.add('ptt-locked');
      pttBtn.setAttribute('title', 'Gerade spricht jemand anderes.');
    }
  }

  if (!recordingSupported) {
    setButtonAvailable();
  }

  function resumeAudioContext() {
    if (!audioCtx) {
      return Promise.resolve();
    }
    if (typeof audioCtx.resume === 'function' && audioCtx.state !== 'running') {
      return audioCtx.resume();
    }
    return Promise.resolve();
  }

  function unlockPlayback() {
    return resumeAudioContext()
      .then(() => {
        if (playbackUnlocked) {
          return;
        }
        const sampleRate = audioCtx.sampleRate || 44100;
        const buffer = audioCtx.createBuffer(1, 1, sampleRate);
        const source = audioCtx.createBufferSource();
        source.buffer = buffer;
        source.connect(audioCtx.destination);
        if (typeof source.start === 'function') {
          source.start(0);
        } else {
          source.noteOn(0);
        }
        playbackUnlocked = true;
        pttDiagnoseMelden('Audiofreigabe erteilt');
      })
      .catch((err) => {
        pttDiagnoseMelden('Audiofreigabe fehlgeschlagen');
        console.error('Audio context unlock failed', err);
      });
  }

  function playPing() {
    return unlockPlayback().then(() => {
      return new Promise((resolve) => {
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.type = 'sine';
        osc.frequency.value = 880;
        gain.gain.value = 1.0;
        osc.connect(gain);
        gain.connect(audioCtx.destination);
        if (typeof osc.start === 'function') {
          osc.start();
        } else {
          osc.noteOn(0);
        }
        if (typeof osc.stop === 'function') {
          osc.stop(audioCtx.currentTime + 0.1);
        } else {
          osc.noteOff(audioCtx.currentTime + 0.1);
        }
        osc.onended = resolve;
      });
    });
  }

  function clearTot() {
    if (totTimer) {
      clearTimeout(totTimer);
      totTimer = null;
    }
  }

  function requestUserMedia(constraints) {
    if (hasModernGetUserMedia) {
      return navigator.mediaDevices.getUserMedia(constraints);
    }
    return new Promise((resolve, reject) => {
      legacyGetUserMedia.call(navigator, constraints, resolve, reject);
    });
  }

  function ensureMedia() {
    if (!recordingSupported) {
      return Promise.reject(new Error('MediaRecorder or getUserMedia unavailable'));
    }
    if (mediaStream) {
      return Promise.resolve(mediaStream);
    }
    if (mediaPromise) {
      return mediaPromise;
    }
    microphoneStatus = 'wird angefragt';
    pttDiagnoseMelden('Mikrofon wird angefragt');
    mediaPromise = requestUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true }
    })
      .then((stream) => {
        mediaStream = stream;
        microphoneStatus = 'freigegeben';
        pttDiagnoseMelden('Mikrofon freigegeben');
        return stream;
      })
      .catch((err) => {
        recordingSupported = false;
        microphoneStatus = 'Fehler: ' + (err && (err.name || err.message) ?
          (err.name || err.message) : 'unbekannt');
        setButtonAvailable();
        pttDiagnoseMelden('Mikrofonfehler');
        console.error('Microphone access denied', err);
        throw err;
      });
    return mediaPromise;
  }

  function blobToArrayBuffer(blob) {
    if (blob && typeof blob.arrayBuffer === 'function') {
      return blob.arrayBuffer();
    }
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = () => reject(reader.error);
      reader.readAsArrayBuffer(blob);
    });
  }

  function sendBlob(blob) {
    if (!blob || !blob.size) {
      return Promise.resolve();
    }
    const sendPromise = blobToArrayBuffer(blob)
      .then((buf) => {
        const chunk = new Uint8Array(buf);
        if (chunk.length) {
          socket.emit('audio_chunk', chunk);
        }
      })
      .catch((err) => {
        console.error('Audio chunk conversion failed', err);
      });
    pendingChunkSends.push(sendPromise);
    sendPromise.then(() => {
      pendingChunkSends = pendingChunkSends.filter((item) => item !== sendPromise);
    });
    return sendPromise;
  }

  function startRecording() {
    if (!mediaStream || !recordingSupported || stoppingRecorder) {
      return false;
    }
    resumeAudioContext().catch((err) => console.error('Audio context resume failed', err));
    pendingChunkSends = [];
    const mimeType = waehleMimeType();
    lastChosenMimeType = mimeType;
    const options = mimeType ? { mimeType } : {};
    try {
      recorder = new MediaRecorder(mediaStream, options);
    } catch (err) {
      recordingSupported = false;
      setButtonAvailable();
      pttDiagnoseMelden('MediaRecorder-Fehler');
      console.error('MediaRecorder start failed', err);
      return false;
    }
    recorder.ondataavailable = (e) => {
      sendBlob(e.data);
    };
    recorder.onerror = (e) => {
      console.error('MediaRecorder error', e);
    };
    recorder.start(250);
    pttDiagnoseMelden('Aufnahme gestartet');
    return true;
  }

  function stopLocalRecording(sendStopAfterChunks) {
    stopLevelMonitoring();
    if (recorder && recorder.state !== 'inactive') {
      const activeRecorder = recorder;
      stoppingRecorder = true;
      activeRecorder.onstop = () => {
        Promise.all(pendingChunkSends.slice())
          .catch(() => {})
          .then(() => {
            recorder = null;
            stoppingRecorder = false;
            if (sendStopAfterChunks) {
              socket.emit('stop_speaking');
            }
          });
      };
      try {
        if (typeof activeRecorder.requestData === 'function') {
          activeRecorder.requestData();
        }
        activeRecorder.stop();
      } catch (err) {
        console.error('MediaRecorder stop failed', err);
        recorder = null;
        stoppingRecorder = false;
        if (sendStopAfterChunks) {
          socket.emit('stop_speaking');
        }
      }
      return;
    }
    recorder = null;
    stoppingRecorder = false;
    if (sendStopAfterChunks) {
      Promise.all(pendingChunkSends.slice())
        .catch(() => {})
        .then(() => socket.emit('stop_speaking'));
    }
  }

  function startLevelMonitoring() {
    if (!mediaStream || !levelMeter) return;
    resumeAudioContext().catch((err) => console.error('Audio context resume failed', err));
    micSource = audioCtx.createMediaStreamSource(mediaStream);
    micAnalyser = audioCtx.createAnalyser();
    micAnalyser.fftSize = 256;
    micSource.connect(micAnalyser);
    micSilencer = audioCtx.createGain();
    micSilencer.gain.value = 0;
    micAnalyser.connect(micSilencer);
    micSilencer.connect(audioCtx.destination);
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
    if (micSilencer) {
      micSilencer.disconnect();
      micSilencer = null;
    }
    if (levelMeter) {
      levelMeter.value = 0;
    }
  }

  function beginSpeaking(event) {
    if (event) {
      event.preventDefault();
    }
    unlockPlayback();
    if (!recordingSupported) {
      setButtonAvailable();
      return;
    }
    if (!canSpeak || startRequested || speakingActive) {
      return;
    }
    startRequested = true;
    pendingStopAfterStart = false;
    if (pttBtn) {
      pttBtn.classList.add('active-btn');
    }
    ensureMedia()
      .then(() => {
        if (pendingStopAfterStart) {
          startRequested = false;
          if (pttBtn) {
            pttBtn.classList.remove('active-btn');
          }
          return;
        }
        lastChosenMimeType = waehleMimeType();
        socket.emit('start_speaking', {
          mime_type: lastChosenMimeType,
          codec: codecName(lastChosenMimeType) || 'Browser-Standard'
        });
      })
      .catch(() => {
        startRequested = false;
        pendingStopAfterStart = false;
        if (pttBtn) {
          pttBtn.classList.remove('active-btn');
        }
      });
  }

  function finishSpeaking(event) {
    if (event) {
      event.preventDefault();
    }
    unlockPlayback();
    if (!recordingSupported || stoppingRecorder) {
      setButtonAvailable();
      return;
    }
    pendingStopAfterStart = true;
    clearTot();
    if (pttBtn) {
      pttBtn.classList.remove('active-btn');
    }
    if (startRequested && !speakingActive) {
      return;
    }
    if (!speakingActive) {
      return;
    }
    startRequested = false;
    speakingActive = false;
    stopLocalRecording(true);
  }

  function decodeAudioDataCompat(buffer) {
    return new Promise((resolve, reject) => {
      try {
        const result = audioCtx.decodeAudioData(buffer, resolve, reject);
        if (result && typeof result.then === 'function') {
          result.then(resolve, reject);
        }
      } catch (err) {
        reject(err);
      }
    });
  }

  function normalisiereAudioDaten(data) {
    if (data instanceof ArrayBuffer) {
      return Promise.resolve(new Uint8Array(data));
    }
    if (data instanceof Uint8Array) {
      return Promise.resolve(data);
    }
    if (data && data.buffer instanceof ArrayBuffer) {
      return Promise.resolve(new Uint8Array(data.buffer));
    }
    if (data && Array.isArray(data.data)) {
      return Promise.resolve(new Uint8Array(data.data));
    }
    if (typeof Blob !== 'undefined' && data instanceof Blob) {
      return blobToArrayBuffer(data).then((buf) => new Uint8Array(buf));
    }
    try {
      return Promise.resolve(new Uint8Array(data));
    } catch (err) {
      return Promise.reject(err);
    }
  }

  if (pttBtn) {
    setButtonAvailable();
    pttBtn.addEventListener('mousedown', beginSpeaking);
    pttBtn.addEventListener('mouseup', finishSpeaking);
    pttBtn.addEventListener('mouseleave', finishSpeaking);
    pttBtn.addEventListener('touchstart', beginSpeaking);
    pttBtn.addEventListener('touchend', finishSpeaking);
    pttBtn.addEventListener('touchcancel', finishSpeaking);
  }
  document.addEventListener('click', () => unlockPlayback(), false);
  document.addEventListener('touchend', () => unlockPlayback(), false);
  pttDiagnoseMelden('Seite geladen');

  socket.on('your_id', (data) => {
    clientId = data.id;
    pttDiagnoseMelden('Client-ID empfangen');
  });

  socket.on('start_accepted', () => {
    speakingActive = true;
    startRequested = false;
    playPing()
      .catch((err) => console.error('Ping playback failed', err))
      .then(() => {
        if (pendingStopAfterStart) {
          finishSpeaking();
          return;
        }
        if (!startRecording()) {
          speakingActive = false;
          socket.emit('stop_speaking');
          return;
        }
        startLevelMonitoring();
        clearTot();
        totTimer = setTimeout(() => {
          finishSpeaking();
          totTimer = null;
        }, 30000);
      });
  });

  socket.on('start_denied', () => {
    startRequested = false;
    pendingStopAfterStart = false;
    speakingActive = false;
    stopLocalRecording(false);
    canSpeak = false;
    setButtonAvailable();
    if (pttBtn) {
      pttBtn.classList.remove('active-btn');
    }
  });

  socket.on('lock_ptt', () => {
    canSpeak = false;
    setButtonAvailable();
    if (pttBtn) {
      pttBtn.classList.remove('active-btn');
      pttBtn.classList.add('ptt-locked');
    }
    clearTot();
    const now = Date.now();
    if (now - lastPing > 500) {
      lastPing = now;
      playPing().catch((err) => console.error('Ping playback failed', err));
    }
  });

  socket.on('unlock_ptt', () => {
    canSpeak = true;
    setButtonAvailable();
    if (pttBtn) {
      pttBtn.classList.remove('active-btn');
      pttBtn.classList.remove('ptt-locked');
    }
    clearTot();
  });

  let playbackTime = audioCtx.currentTime;
  let playbackChain = Promise.resolve();

  socket.on('play_audio', (data) => {
    unlockPlayback();
    normalisiereAudioDaten(data)
      .then((chunk) => {
        if (!chunk.length) {
          console.error('Received empty audio data');
          return;
        }
        const ab = chunk.buffer.slice(
          chunk.byteOffset,
          chunk.byteOffset + chunk.byteLength
        );

        playbackChain = playbackChain
          .catch(() => {})
          .then(() => decodeAudioDataCompat(ab))
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
            if (playbackTime < audioCtx.currentTime + 0.05) {
              playbackTime = audioCtx.currentTime + 0.05;
            }
            if (typeof source.start === 'function') {
              source.start(playbackTime);
            } else {
              source.noteOn(playbackTime);
            }
            playbackTime += buffer.duration;
          })
          .catch((err) => console.error('Audio decode failed', err));
      })
      .catch((err) => console.error('Unsupported audio data format', err));
  });
})();
