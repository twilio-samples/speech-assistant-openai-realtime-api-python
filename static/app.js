let ws;
let audioContext;
let processor;
let mediaStream;
let isRecording = false;
let pulseTimeout;
let nextPlaybackTime = 0;
let activeSources = [];

const startBtn = document.getElementById('startBtn');
const stopBtn = document.getElementById('stopBtn');
const hal = document.querySelector('.animation');
hal.classList.add('idle');

startBtn.addEventListener('click', async () => {
    ws = new WebSocket(`ws://${location.host}/ws`);
    ws.onmessage = handleMessage;
    await startAudio();
    startBtn.disabled = true;
    stopBtn.disabled = false;
});

stopBtn.addEventListener('click', () => {
    stopAudio();
    ws.close();
    startBtn.disabled = false;
    stopBtn.disabled = true;
});

function handleMessage(event) {
    const data = JSON.parse(event.data);
    if (data.event === 'clear') {
        clearAudio();
        return;
    }
    if (data.audio) {
        const ulaw = Uint8Array.from(atob(data.audio), c => c.charCodeAt(0));
        const pcm = ulawToPCM(ulaw);
        playAudio(pcm);
    }
}

async function startAudio() {
    audioContext = new (window.AudioContext || window.webkitAudioContext)({sampleRate: 8000});
    nextPlaybackTime = audioContext.currentTime;
    mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const source = audioContext.createMediaStreamSource(mediaStream);
    if (audioContext.audioWorklet) {
        await audioContext.audioWorklet.addModule('/worklet.js');
        processor = new AudioWorkletNode(audioContext, 'capture-processor');
        processor.port.onmessage = e => {
            const pcm16 = e.data;
            const ulaw = pcmToUlaw(pcm16);
            const b64 = btoa(String.fromCharCode(...ulaw));
            if (ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({audio: b64}));
            }
        };
    } else {
        processor = audioContext.createScriptProcessor(1024, 1, 1);
        processor.onaudioprocess = e => {
            const input = e.inputBuffer.getChannelData(0);
            const pcm16 = floatTo16BitPCM(input);
            const ulaw = pcmToUlaw(pcm16);
            const b64 = btoa(String.fromCharCode(...ulaw));
            if (ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({audio: b64}));
            }
        };
    }
    source.connect(processor);
    processor.connect(audioContext.destination);
    isRecording = true;
}

function stopAudio() {
    if (processor) {
        processor.disconnect();
    }
    if (mediaStream) {
        mediaStream.getTracks().forEach(t => t.stop());
    }
    if (audioContext) {
        audioContext.close();
    }
    nextPlaybackTime = 0;
    isRecording = false;
    activeSources = [];
    hal.classList.remove('speaking');
    hal.classList.add('idle');
}

function clearAudio() {
    activeSources.forEach(src => {
        try { src.stop(); } catch (e) {}
    });
    activeSources = [];
    if (audioContext) {
        nextPlaybackTime = audioContext.currentTime;
    } else {
        nextPlaybackTime = 0;
    }
    hal.classList.remove('speaking');
    hal.classList.add('idle');
}

function floatTo16BitPCM(input) {
    const output = new Int16Array(input.length);
    for (let i = 0; i < input.length; i++) {
        let s = Math.max(-1, Math.min(1, input[i]));
        output[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
    }
    return output;
}

function pcmToUlaw(samples) {
    const ulaw = new Uint8Array(samples.length);
    for (let i = 0; i < samples.length; i++) {
        let s = samples[i];
        let sign = (s >> 8) & 0x80;
        if (sign) s = -s;
        if (s > 32635) s = 32635;
        s = s + 132;
        let exponent = Math.floor(Math.log2(s)) - 7;
        let mantissa = (s >> (exponent + 3)) & 0x0F;
        let val = ~(sign | (exponent << 4) | mantissa);
        ulaw[i] = val & 0xFF;
    }
    return ulaw;
}

function ulawToPCM(ulaw) {
    const pcm = new Float32Array(ulaw.length);
    for (let i = 0; i < ulaw.length; i++) {
        let u = ~ulaw[i];
        let sign = u & 0x80;
        let exponent = (u >> 4) & 0x07;
        let mantissa = u & 0x0F;
        let sample = ((mantissa << 3) + 132) << exponent;
        sample -= 132;
        if (sign) sample = -sample;
        pcm[i] = sample / 32768;
    }
    return pcm;
}

function playAudio(pcm) {
    const buffer = audioContext.createBuffer(1, pcm.length, 8000);
    buffer.copyToChannel(pcm, 0);
    const src = audioContext.createBufferSource();
    src.buffer = buffer;
    src.connect(audioContext.destination);
    if (nextPlaybackTime < audioContext.currentTime) {
        nextPlaybackTime = audioContext.currentTime;
    }
    src.start(nextPlaybackTime);
    activeSources.push(src);
    hal.classList.remove('idle');
    hal.classList.add('speaking');
    src.onended = () => {
        activeSources = activeSources.filter(s => s !== src);
        if (activeSources.length === 0) {
            hal.classList.remove('speaking');
            hal.classList.add('idle');
        }
    };
    nextPlaybackTime += buffer.duration;
}
