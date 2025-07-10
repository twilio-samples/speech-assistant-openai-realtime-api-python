let ws;
let audioContext;
let processor;
let mediaStream;
let isRecording = false;

const startBtn = document.getElementById('startBtn');
const stopBtn = document.getElementById('stopBtn');
const hal = document.getElementById('hal-container');

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
    if (data.audio) {
        hal.classList.add('speaking');
        const ulaw = Uint8Array.from(atob(data.audio), c => c.charCodeAt(0));
        const pcm = ulawToPCM(ulaw);
        playAudio(pcm);
        setTimeout(()=>hal.classList.remove('speaking'), 500);
    }
}

async function startAudio() {
    audioContext = new (window.AudioContext || window.webkitAudioContext)({sampleRate: 8000});
    mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const source = audioContext.createMediaStreamSource(mediaStream);
    processor = audioContext.createScriptProcessor(1024, 1, 1);
    source.connect(processor);
    processor.connect(audioContext.destination);
    processor.onaudioprocess = e => {
        const input = e.inputBuffer.getChannelData(0);
        const pcm16 = floatTo16BitPCM(input);
        const ulaw = pcmToUlaw(pcm16);
        const b64 = btoa(String.fromCharCode(...ulaw));
        if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({audio: b64}));
        }
    };
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
    isRecording = false;
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
    src.start();
}
