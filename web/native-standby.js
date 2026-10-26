'use strict';

// The Python listener reads microphone samples locally. This channel carries
// only ownership, busy state, and a counter of detected double claps.
class NativeStandbyMonitor {
  constructor({context, detector, api, onTrigger=()=>{}, onStatus=()=>{}, isBusy=()=>false,
    schedule=(callback,delay)=>globalThis.setTimeout(callback,delay),
    unschedule=timer=>globalThis.clearTimeout(timer),
    now=()=>globalThis.performance.now(), ownerFactory=()=>{
      if(globalThis.crypto?.randomUUID)return globalThis.crypto.randomUUID();
      if(!globalThis.crypto?.getRandomValues)throw new Error('Secure microphone ownership is unavailable. Restart IRIS.');
      return Array.from(globalThis.crypto.getRandomValues(new Uint8Array(24)),value=>value.toString(16).padStart(2,'0')).join('');
    }, pollMs=250, maxEventDelayMs=1000, startupTimeoutMs=30000}) {
    Object.assign(this,{context,detector,api,onTrigger,onStatus,isBusy,schedule,unschedule,now,
      ownerFactory,pollMs,maxEventDelayMs,startupTimeoutMs});
    this.active=false;this.wanted=false;this.pending=null;this.run=null;this.device=null;
    this.requests=Promise.resolve();
  }

  start() {
    if(this.run)return this.pending||Promise.resolve(this.active);
    let owner;
    try {
      if(typeof this.api!=='function')throw new Error('The local microphone connection is unavailable. Restart IRIS.');
      owner=this.ownerFactory();
      if(typeof owner!=='string'||!/^[A-Za-z0-9_-]{16,128}$/.test(owner))throw new Error('Secure microphone ownership is unavailable. Restart IRIS.');
    } catch(error) {this.onStatus(false,error.message);return Promise.resolve(false);}
    const run={owner,timer:null,sequence:null,lastResponse:null,wakePending:false,settle:null,startedAt:null};
    this.run=run;this.wanted=true;
    this.pending=new Promise(resolve=>{run.settle=resolve;});
    const pending=this.pending;
    this.poll(run);
    return pending;
  }

  // Lifecycle requests share one queue. A cancelled start cannot arrive after
  // a later activation and reclaim its microphone, or stop the new owner.
  request(callback) {
    const result=this.requests.then(callback);
    this.requests=result.catch(()=>{});
    return result;
  }

  current(run) {return this.run===run&&this.wanted;}
  busy() {return Boolean(this.isBusy());}
  settle(run,result) {
    if(!run.settle)return;
    run.settle(result);run.settle=null;
    if(this.run===run)this.pending=null;
  }

  async poll(run) {
    if(!this.current(run))return;
    run.timer=null;
    let sentBusy=false,sentAt=null;
    try {
      const data=await this.request(()=>{
        if(!this.current(run))return null;
        sentBusy=this.busy()||run.wakePending;sentAt=this.now();
        if(run.startedAt===null)run.startedAt=sentAt;
        return this.api('/api/clap',{action:'update',owner:run.owner,busy:sentBusy});
      });
      if(!this.current(run))return;
      if(!data||typeof data.active!=='boolean'||!Number.isSafeInteger(data.sequence)||data.sequence<0)
        throw new Error('The local clap listener returned an invalid status. Restart IRIS.');
      if(data.error)throw new Error(String(data.error));
      if(!data.active&&!data.starting)throw new Error('The local microphone could not start. Check Windows microphone access and your input device.');

      const receivedAt=this.now(),wasActive=this.active,previousSequence=run.sequence;
      const fresh=receivedAt-sentAt<=this.maxEventDelayMs&&
        (run.lastResponse===null||receivedAt-run.lastResponse<=this.maxEventDelayMs);
      const suppress=sentBusy||this.busy()||run.wakePending;
      run.sequence=data.sequence;run.lastResponse=receivedAt;
      if(wasActive&&!data.active)run.startedAt=receivedAt;
      this.device=typeof data.device==='string'&&data.device.trim()?data.device.trim():null;
      this.active=data.active;
      if(wasActive!==this.active)this.onStatus(this.active,null);
      if(this.active)this.settle(run,true);
      else if(receivedAt-run.startedAt>=this.startupTimeoutMs)
        throw new Error('The microphone is taking too long to open. Check your input device, then tap the core to retry.');

      // Busy acknowledgements consume the wake latch. Every observed sequence
      // becomes the baseline, including suppressed/delayed events and startup.
      if(sentBusy)run.wakePending=false;
      // The native detector waits for busy -> idle after every event. Even a
      // deliberately discarded event needs that acknowledgement to rearm it.
      if(data.sequence>(previousSequence??0))run.wakePending=true;
      if(this.active&&wasActive&&previousSequence!==null&&data.sequence>previousSequence&&fresh&&!suppress) {
        run.wakePending=true;
        // The app sets its recording state synchronously here. The latch also
        // forces the next heartbeat busy before another wake can be accepted.
        const trigger=this.onTrigger();
        if(trigger&&typeof trigger.catch==='function')trigger.catch(error=>{
          if(this.current(run))this.onStatus(this.active,error?.message||'Microphone recording could not start.');
        });
      }
      if(this.current(run))run.timer=this.schedule(()=>this.poll(run),this.pollMs);
    } catch(error) {
      if(this.current(run))this.finish(run,error?.message||'The local clap listener disconnected. Tap the core to retry.');
    }
  }

  finish(run,error=null) {
    if(this.run!==run)return;
    if(run.timer!==null)this.unschedule(run.timer);
    run.timer=null;this.active=false;this.wanted=false;this.device=null;
    this.settle(run,false);this.run=null;this.pending=null;
    this.onStatus(false,error);
    // Closing a page may interrupt this request; the server's short heartbeat
    // lease independently releases the microphone if cleanup cannot arrive.
    return this.request(()=>this.api('/api/clap',{action:'stop',owner:run.owner})).catch(()=>{});
  }

  stop() {if(this.run)return this.finish(this.run);}
}

if(typeof module!=='undefined')module.exports={NativeStandbyMonitor};
