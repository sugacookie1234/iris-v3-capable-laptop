'use strict';
function resolveInputDevice(nativeName,devices) {
  const normalize=value=>String(value||'').normalize('NFKC').toLowerCase().trim()
    .replace(/^(?:default|communications)\s*[-–:]\s*/,'')
    .replace(/\s*\([0-9a-f]{4}:[0-9a-f]{4}\)\s*$/,'').replace(/\s+/g,' ').trim();
  const name=normalize(nativeName);
  // These PortAudio Windows aliases intentionally follow the system input.
  if(name==='microsoft sound mapper - input'||name==='primary sound capture driver')return 'default';
  const physical=new Map();
  for(const device of devices||[]) {
    if(device.kind!=='audioinput'||typeof device.deviceId!=='string'||!device.deviceId||
      device.deviceId==='default'||device.deviceId==='communications')continue;
    if(!physical.has(device.deviceId))physical.set(device.deviceId,normalize(device.label));
  }
  const exact=[...physical].filter(([,label])=>name&&label===name);
  // Windows MME can truncate the native device name. Accept only a sufficiently
  // specific native prefix that identifies one concrete recording device.
  const matches=exact.length?exact:[...physical].filter(([,label])=>name.length>=12&&label.startsWith(name));
  if(matches.length===1)return matches[0][0];
  const reason=matches.length?'More than one recording microphone matches the clap listener.':'The clap microphone could not be matched to a recording input.';
  throw new Error(reason+' Select the same Windows default input or set IRIS_INPUT_DEVICE to its full name, then restart standby.');
}

function encodeWav(samples) {
  const buffer=new ArrayBuffer(44+samples.length*2),view=new DataView(buffer);
  const text=(offset,value)=>{for(let i=0;i<value.length;i++)view.setUint8(offset+i,value.charCodeAt(i));};
  text(0,'RIFF');view.setUint32(4,36+samples.length*2,true);text(8,'WAVE');text(12,'fmt ');
  view.setUint32(16,16,true);view.setUint16(20,1,true);view.setUint16(22,1,true);
  view.setUint32(24,16000,true);view.setUint32(28,32000,true);view.setUint16(32,2,true);view.setUint16(34,16,true);
  text(36,'data');view.setUint32(40,samples.length*2,true);
  for(let i=0;i<samples.length;i++){const s=Math.max(-1,Math.min(1,samples[i]));view.setInt16(44+i*2,s<0?s*32768:s*32767,true);}
  return new Blob([buffer],{type:'audio/wav'});
}
async function recordingToWav(blob) {
  const context=new OfflineAudioContext(1,1,16000);
  const decoded=await context.decodeAudioData(await blob.arrayBuffer());
  if(decoded.duration>31)throw new Error('Keep spoken requests under 30 seconds.');
  const samples=new Float32Array(decoded.length);
  for(let channel=0;channel<decoded.numberOfChannels;channel++){
    const data=decoded.getChannelData(channel);
    for(let i=0;i<data.length;i++)samples[i]+=data[i]/decoded.numberOfChannels;
  }
  return encodeWav(samples);
}
// Local energy-based endpoint detection: no model, transcript or upload is
// needed to discard a quiet wake or finish a sentence after a natural pause.
class SpeechEndpoint {
  constructor({now=0,initialSilenceMs=6000,endSilenceMs=1100,minSpeechMs=160,maxDurationMs=30000}={}) {
    Object.assign(this,{started:now,last:now,initialSilenceMs,endSilenceMs,minSpeechMs,maxDurationMs});
    this.noise=.004;this.run=0;this.heardSpeech=false;this.lastSpeech=now;
  }
  update(level,now) {
    const gap=now-this.last;this.last=now;
    // A delayed timer did not observe the audio in between its samples. Do not
    // credit that missing interval to a click caught when the timer resumes.
    const continuous=Number.isFinite(gap)&&gap>=0&&gap<=120;
    const elapsed=continuous?Math.min(100,gap):0;
    if(!continuous)this.run=0;
    const voiced=Number.isFinite(level)&&level>Math.max(.012,this.noise*3);
    if(voiced){this.run+=elapsed;if(this.run>=this.minSpeechMs)this.heardSpeech=true;this.lastSpeech=now;}
    else{this.run=0;if(Number.isFinite(level))this.noise=.98*this.noise+.02*Math.max(0,level);}
    if(!this.heardSpeech&&now-this.started>=this.initialSilenceMs)return 'quiet';
    if(this.heardSpeech&&now-this.lastSpeech>=this.endSilenceMs)return 'speech';
    if(now-this.started>=this.maxDurationMs)return this.heardSpeech?'speech':'quiet';
    return null;
  }
}
class VoiceActivityMonitor {
  constructor(stream,onDecision,options={}) {
    Object.assign(this,{stream,onDecision,options});this.closed=false;
  }
  async start() {
    const Audio=globalThis.AudioContext||globalThis.webkitAudioContext;
    if(!Audio)throw new Error('Automatic listening is unavailable. Hold Space to speak instead.');
    this.context=new Audio();this.source=this.context.createMediaStreamSource(this.stream);
    this.analyser=this.context.createAnalyser();this.analyser.fftSize=2048;this.source.connect(this.analyser);
    const samples=new Float32Array(this.analyser.fftSize);
    if(this.context.state==='suspended')await this.context.resume();
    if(this.closed)return;
    this.endpoint=new SpeechEndpoint({...this.options,now:performance.now()});
    // Timers keep working when the native window is hidden in the tray.
    this.timer=setInterval(()=>{
      if(this.closed)return;
      try{
        this.analyser.getFloatTimeDomainData(samples);
        const level=Math.sqrt(samples.reduce((sum,value)=>sum+value*value,0)/samples.length);
        const decision=this.endpoint.update(level,performance.now());
        if(decision){this.stop();this.onDecision(decision);}
      }catch{this.stop();this.onDecision('quiet');}
    },40);
  }
  stop() {
    this.closed=true;clearInterval(this.timer);
    try{this.source?.disconnect();}catch{}
    try{this.analyser?.disconnect();}catch{}
    try{this.context?.close()?.catch(()=>{});}catch{}
  }
}
class RecordedVoiceInput {
  constructor({onState,onText,onError,onBackend=()=>{},onSilence=()=>{},devices=navigator.mediaDevices,Recorder=MediaRecorder,request=(...args)=>globalThis.fetch(...args),convert=recordingToWav,
    activityFactory=(stream,callback,options)=>new VoiceActivityMonitor(stream,callback,options)}) {
    Object.assign(this,{onState,onText,onError,onBackend,onSilence,devices,Recorder,request,convert,activityFactory});
    this.version=0;this.active=false;
  }
  async start(duration=30000,nativeDeviceName=null,options={}) {
    if(this.active)return;
    this.cancel();const version=this.version;this.active=true;this.onState('Microphone permission');
    try {
      const audio={echoCancellation:true,noiseSuppression:true};
      if(nativeDeviceName!==null) {
        if(typeof this.devices.enumerateDevices!=='function')throw new Error('Microphone matching is unavailable. Update IRIS or use Google Chrome.');
        const devices=await this.devices.enumerateDevices();
        if(version!==this.version)return;
        audio.deviceId={exact:resolveInputDevice(nativeDeviceName,devices)};
      }
      const stream=await this.devices.getUserMedia({audio});
      if(version!==this.version){stream.getTracks().forEach(t=>t.stop());return;}
      this.stream=stream;
      const mime=['audio/webm;codecs=opus','audio/ogg;codecs=opus','audio/mp4'].find(t=>this.Recorder.isTypeSupported(t));
      if(!mime)throw new Error('This interface cannot record supported audio. Update IRIS with setup.bat or try Google Chrome.');
      const recorder=this.recorder=new this.Recorder(stream,{mimeType:mime});
      const chunks=[];let bytes=0;
      recorder.ondataavailable=e=>{
        if(e.data.size){bytes+=e.data.size;chunks.push(e.data);}
        if(bytes>4*1024*1024){this.cancel();this.onError('Recording is too large. Try a shorter request.');}
      };
      recorder.onerror=()=>{this.cancel();this.onError('Microphone recording failed. Check the selected input device.');};
      recorder.onstop=async()=>{
        stream.getTracks().forEach(t=>t.stop());
        if(version!==this.version)return;
        this.activity?.stop();this.activity=null;clearTimeout(this.timer);
        this.onState('Transcribing');this.controller=new AbortController();
        try {
          if(bytes<32)throw new Error('No audio captured. Hold Space while speaking, then release.');
          const audio=await this.convert(new Blob(chunks,{type:mime}));
          if(version!==this.version)return;
          const response=await this.request('/api/transcribe',{method:'POST',
            headers:{'Content-Type':'audio/wav','X-IRIS-Request':'1'},body:audio,signal:this.controller.signal});
          const result=await response.json();
          if(version!==this.version)return;
          if(!response.ok)throw new Error(result.error||'Transcription failed.');
          this.active=false;this.onState('idle');
          if(result.speech)this.onBackend(result.speech);
          if(result.text&&result.text.trim())await this.onText(result.text.trim());
          else if(options.autoStop)this.onSilence();
          else this.onError('No speech detected. Check your microphone and try again.');
        }catch(error){
          if(version===this.version){this.active=false;this.onState('idle');this.onError(error.message);}
        }
      };
      recorder.start(250);this.onState('listening');
      if(options.autoStop){
        const activity=this.activity=this.activityFactory(stream,decision=>{
          if(version!==this.version)return;
          if(decision==='quiet'){this.cancel();this.onSilence();}else this.stop();
        },{initialSilenceMs:options.initialSilenceMs||6000,maxDurationMs:Math.min(duration,30000)});
        // A hung/suspended analyser must not leave the microphone open or send
        // unclassified room audio. Manual push-to-talk has its own time limit.
        this.timer=setTimeout(()=>{if(version===this.version){this.cancel();this.onSilence();}},Math.min(duration,30000)+500);
        await activity.start();if(version!==this.version)activity.stop();
      }else this.timer=setTimeout(()=>this.stop(),Math.min(duration,30000));
    }catch(error){
      if(version!==this.version)return;
      this.cancel();
      const message={NotAllowedError:'Microphone access was denied. Allow the microphone for this page and try again.',
        NotFoundError:'No microphone was found. Connect or enable your microphone.',
        OverconstrainedError:'The microphone selected for clap standby is no longer available. Check your input device, then restart standby.',
        NotReadableError:'The microphone is unavailable or in use by another application.'}[error.name];
      this.onError(message||error.message);
    }
  }
  stop() {
    clearTimeout(this.timer);
    this.activity?.stop();this.activity=null;
    if(this.recorder&&this.recorder.state==='recording')this.recorder.stop();
    else if(!this.recorder)this.cancel(); // Key released before permission resolved.
  }
  cancel() {
    this.version++;this.active=false;clearTimeout(this.timer);
    this.activity?.stop();this.activity=null;
    if(this.controller)this.controller.abort();this.controller=null;
    if(this.recorder){this.recorder.onstop=null;if(this.recorder.state==='recording')this.recorder.stop();}
    this.recorder=null;
    if(this.stream)this.stream.getTracks().forEach(t=>t.stop());this.stream=null;
    this.onState('idle');
  }
}
if(typeof module!=='undefined')module.exports={RecordedVoiceInput,encodeWav,resolveInputDevice,SpeechEndpoint,VoiceActivityMonitor};
