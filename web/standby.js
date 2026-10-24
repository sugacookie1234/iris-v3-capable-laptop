'use strict';

// The browser keeps this local sound meter alive after microphone permission.
// Samples are discarded immediately; only an explicit wake starts transcription.
class StandbyMonitor {
  constructor({context, detector, onTrigger, onStatus=()=>{}, isBusy=()=>false,
    devices=globalThis.navigator?.mediaDevices,
    schedule=(callback,delay)=>globalThis.setInterval(callback,delay),
    unschedule=timer=>globalThis.clearInterval(timer), now=()=>globalThis.performance.now()/1000}) {
    Object.assign(this,{context,detector,onTrigger,onStatus,isBusy,devices,schedule,unschedule,now});
    this.active=false; this.wanted=false; this.version=0; this.pending=null;
    this.stream=null; this.source=null; this.analyser=null; this.timer=null; this.trackListeners=[];
  }

  start() {
    this.wanted=true;
    if(this.active)return Promise.resolve(true);
    if(this.pending) {
      if(this.pendingVersion===this.version)return this.pending;
      // A new activation waits for a cancelled permission request to release its stream.
      return this.pending.then(()=>this.wanted?this.start():false);
    }
    const version=this.version;
    this.pendingVersion=version;
    const pending=this.activate(version).finally(()=>{if(this.pending===pending)this.pending=null;});
    this.pending=pending;
    return pending;
  }

  async activate(version) {
    let stream=null;
    try {
      if(!this.context || !this.devices?.getUserMedia)throw new Error('Microphone standby needs the IRIS desktop app or Google Chrome.');
      stream=await this.devices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:false,autoGainControl:false}});
      if(version!==this.version || !this.wanted){stream.getTracks().forEach(track=>track.stop());return false;}
      this.stream=stream;
      if(this.context.state==='suspended')await this.context.resume();
      if(version!==this.version || !this.wanted)return false;
      this.source=this.context.createMediaStreamSource(stream);
      this.analyser=this.context.createAnalyser();
      this.analyser.fftSize=1024;
      this.samples=new Float32Array(this.analyser.fftSize);
      this.source.connect(this.analyser); // Never connect the microphone to speakers.
      for(const track of stream.getTracks()) {
        const ended=()=>{
          if(version!==this.version)return;
          this.stop();this.onStatus(false,'The microphone disconnected. Tap the core to restore standby.');
        };
        if(track.addEventListener){track.addEventListener('ended',ended,{once:true});this.trackListeners.push([track,ended]);}
      }
      this.detector.reset();this.active=true;
      this.timer=this.schedule(()=>this.sample(version),16);
      this.onStatus(true,null);
      return true;
    } catch(error) {
      if(version!==this.version)return false;
      this.release();this.wanted=false;
      const message={
        NotAllowedError:'Allow microphone access, then tap the core to enable standby.',
        NotFoundError:'Connect a microphone, then tap the core to enable standby.',
        NotReadableError:'The microphone is unavailable. Close any app holding it, then tap the core.'
      }[error.name] || error.message || 'Microphone standby could not start.';
      this.onStatus(false,message);
      return false;
    }
  }

  sample(version) {
    if(!this.active || version!==this.version)return;
    if(this.isBusy() || this.context.state==='suspended') {this.detector.reset();return;}
    this.analyser.getFloatTimeDomainData(this.samples);
    let squares=0;
    for(const sample of this.samples)squares+=sample*sample;
    if(this.detector.feed(Math.sqrt(squares/this.samples.length),this.now()))this.onTrigger();
  }

  release() {
    this.active=false;
    if(this.timer!==null)this.unschedule(this.timer);
    this.timer=null;
    for(const [track,listener] of this.trackListeners)track.removeEventListener?.('ended',listener);
    this.trackListeners=[];
    this.source?.disconnect();this.analyser?.disconnect();
    this.source=null;this.analyser=null;this.samples=null;
    this.stream?.getTracks().forEach(track=>track.stop());this.stream=null;
    this.detector.reset();
  }

  stop() {
    this.wanted=false;this.version++;this.release();this.onStatus(false,null);
  }
}

function parseVoiceCommand(text) {
  if(typeof text!=='string')return null;
  const normalized=text.toLowerCase().trim().replace(/[’]/g,"'")
    .replace(/^(?:hey\s+)?iris[,.!]?\s+/,'').replace(/^please\s+/,'')
    .replace(/[.!?]+$/,'').replace(/,?\s+please$/,'').replace(/\s+/g,' ').trim();
  const commands={
    mute:/^(?:mute(?: (?:audio|yourself|iris))?|(?:turn |switch )?(?:the )?(?:audio|sound) off|stop speaking|be quiet)$/,
    unmute:/^(?:unmute(?: (?:audio|yourself|iris))?|(?:turn |switch )?(?:the )?(?:audio|sound) on)$/,
    newchat:/^(?:(?:start|begin|open) (?:a )?)?new (?:chat|conversation)$/,
    memories:/^(?:(?:show|open|view)(?: me)? )?(?:(?:my|the) )?(?:memories|memory panel)$/,
    tasks:/^(?:(?:show|open|view)(?: me)? )?(?:(?:my|the) )?(?:tasks|task list)$/,
    council:/^(?:(?:show|open|view)(?: me)? )?(?:the )?council(?: review| results)?$/,
    help:/^(?:help|setup|show help|open help|show setup|open setup|voice commands|show voice commands)$/,
    close:/^(?:close(?: (?:the|this))? (?:panel|window)|close that|go back)$/,
    approve:/^(?:approve(?: (?:that|this|the action|this action|that action))?|confirm (?:the |this |that )?action)$/,
    decline:/^(?:decline(?: (?:that|this|the action|this action|that action))?|(?:reject|deny|cancel) (?:the |this |that )?action)$/
  };
  for(const [command,pattern] of Object.entries(commands))if(pattern.test(normalized))return command;
  return null;
}

if(typeof module!=='undefined')module.exports={StandbyMonitor,parseVoiceCommand};
