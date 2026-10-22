'use strict';
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
class RecordedVoiceInput {
  constructor({onState,onText,onError,devices=navigator.mediaDevices,Recorder=MediaRecorder,request=fetch,convert=recordingToWav}) {
    Object.assign(this,{onState,onText,onError,devices,Recorder,request,convert});
    this.version=0;this.active=false;
  }
  async start(duration=30000) {
    if(this.active)return;
    this.cancel();const version=this.version;this.active=true;this.onState('Microphone permission');
    try {
      const stream=await this.devices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true}});
      if(version!==this.version){stream.getTracks().forEach(t=>t.stop());return;}
      this.stream=stream;
      const mime=['audio/webm;codecs=opus','audio/ogg;codecs=opus','audio/mp4'].find(t=>this.Recorder.isTypeSupported(t));
      if(!mime)throw new Error('This browser cannot record supported audio. Open IRIS in Edge.');
      const recorder=this.recorder=new this.Recorder(stream,{mimeType:mime});
      const chunks=[];let bytes=0;
      recorder.ondataavailable=e=>{
        if(e.data.size){bytes+=e.data.size;chunks.push(e.data);}
        if(bytes>4*1024*1024){this.cancel();this.onError('Recording is too large. Try a shorter request.');}
      };
      recorder.onerror=()=>{this.cancel();this.onError('Microphone recording failed. Check the selected input device.');};
      recorder.onstop=async()=>{
        stream.getTracks().forEach(t=>t.stop());clearTimeout(this.timer);
        if(version!==this.version)return;
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
          if(result.text&&result.text.trim())this.onText(result.text.trim());
          else this.onError('No speech detected. Check your microphone and try again.');
        }catch(error){
          if(version===this.version){this.active=false;this.onState('idle');this.onError(error.message);}
        }
      };
      recorder.start(250);this.onState('listening');
      this.timer=setTimeout(()=>this.stop(),Math.min(duration,30000));
    }catch(error){
      if(version!==this.version)return;
      this.cancel();
      const message={NotAllowedError:'Microphone access was denied. Allow the microphone for this page and try again.',
        NotFoundError:'No microphone was found. Connect or enable your microphone.',
        NotReadableError:'The microphone is unavailable or in use by another application.'}[error.name];
      this.onError(message||error.message);
    }
  }
  stop() {
    clearTimeout(this.timer);
    if(this.recorder&&this.recorder.state==='recording')this.recorder.stop();
    else if(!this.recorder)this.cancel(); // Key released before permission resolved.
  }
  cancel() {
    this.version++;this.active=false;clearTimeout(this.timer);
    if(this.controller)this.controller.abort();this.controller=null;
    if(this.recorder){this.recorder.onstop=null;if(this.recorder.state==='recording')this.recorder.stop();}
    this.recorder=null;
    if(this.stream)this.stream.getTracks().forEach(t=>t.stop());this.stream=null;
    this.onState('idle');
  }
}
if(typeof module!=='undefined')module.exports={RecordedVoiceInput,encodeWav};
