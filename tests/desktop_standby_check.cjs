const assert = require('node:assert/strict');
const {StandbyMonitor,parseVoiceCommand} = require('../web/standby.js');
const {DoubleClapDetector} = require('../web/clap.js');

function deferred() {
  let resolve,reject;
  const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});
  return {promise,resolve,reject};
}
function fixture({permission,resume}={}) {
  const listeners=new Set();
  const track={stops:0,stop(){this.stops++;},addEventListener(name,fn){listeners.add(fn);},removeEventListener(name,fn){listeners.delete(fn);}};
  const stream={getTracks:()=>[track]};
  const source={connections:[],disconnects:0,connect(node){this.connections.push(node);},disconnect(){this.disconnects++;}};
  let sampleLevel=0,clock=0,busy=false,requests=0,triggers=0,callback=null,clears=0;
  const analyser={fftSize:0,disconnects:0,getFloatTimeDomainData(samples){samples.fill(sampleLevel);},disconnect(){this.disconnects++;}};
  const context={state:resume?'suspended':'running',resume:()=>resume.promise,
    createMediaStreamSource:input=>{assert.equal(input,stream);return source;},createAnalyser:()=>analyser};
  const statuses=[];
  const monitor=new StandbyMonitor({context,detector:new DoubleClapDetector(),
    devices:{getUserMedia:()=>{requests++;return permission?permission.promise:Promise.resolve(stream);}},
    onTrigger:()=>triggers++,onStatus:(active,error)=>statuses.push({active,error}),isBusy:()=>busy,
    now:()=>clock,schedule:fn=>{callback=fn;return 0;},unschedule:id=>{assert.equal(id,0);clears++;callback=null;}});
  return {monitor,track,stream,source,analyser,context,statuses,listeners,
    get requests(){return requests;},get triggers(){return triggers;},get clears(){return clears;},
    set busy(value){busy=value;},sample(level,time){sampleLevel=level;clock=time;callback?.();}};
}

(async()=>{
  // A pending permission request is shared; stopping cancels its eventual result.
  const permission=deferred(),cancelled=fixture({permission});
  const first=cancelled.monitor.start(),second=cancelled.monitor.start();
  assert.equal(first,second);assert.equal(cancelled.requests,1);
  cancelled.monitor.stop();permission.resolve(cancelled.stream);
  assert.equal(await first,false);assert.equal(cancelled.track.stops,1);
  assert.equal(cancelled.monitor.active,false);assert.equal(cancelled.source.connections.length,0);
  assert.equal(cancelled.statuses.some(item=>item.active),false);

  // Restarting during a cancelled permission request waits for cleanup rather than
  // opening simultaneous microphones, then creates a fresh activation.
  const pending=deferred(),restarted=fixture({permission:pending});
  const obsolete=restarted.monitor.start();restarted.monitor.stop();
  const latest=restarted.monitor.start();assert.equal(restarted.requests,1);
  pending.resolve(restarted.stream);
  assert.equal(await obsolete,false);assert.equal(await latest,true);
  assert.equal(restarted.requests,2);assert.equal(restarted.track.stops,1);
  restarted.monitor.stop();

  const resume=deferred(),suspended=fixture({resume});
  const starting=suspended.monitor.start();await Promise.resolve();
  suspended.monitor.stop();resume.resolve();assert.equal(await starting,false);
  assert.equal(suspended.track.stops,1);assert.equal(suspended.source.connections.length,0);

  const live=fixture();assert.equal(await live.monitor.start(),true);
  assert.equal(await live.monitor.start(),true);assert.equal(live.requests,1);
  assert.deepEqual(live.source.connections,[live.analyser]);
  // Busy audio is ignored; a clap before busy cannot combine with a clap after.
  live.sample(.2,0);live.busy=true;live.sample(.001,.1);live.sample(.2,.2);
  assert.equal(live.triggers,0);live.busy=false;live.sample(.2,.3);
  assert.equal(live.triggers,0);live.sample(.001,.4);live.sample(.2,.5);
  assert.equal(live.triggers,1);
  live.sample(.001,.6);live.sample(.2,.7);assert.equal(live.triggers,1);
  live.context.state='suspended';live.sample(.001,2);live.sample(.2,2.1);
  assert.equal(live.triggers,1);live.context.state='running';
  live.sample(.001,2.2);live.sample(.2,2.3);live.sample(.001,2.4);live.sample(.2,2.5);
  assert.equal(live.triggers,2);
  live.monitor.stop();assert.equal(live.track.stops,1);assert.equal(live.clears,1);
  assert.equal(live.source.disconnects,1);assert.equal(live.analyser.disconnects,1);
  assert.equal(live.listeners.size,0);assert.equal(live.monitor.active,false);
  live.monitor.stop();assert.equal(live.track.stops,1);assert.equal(live.clears,1);

  const disconnected=fixture();await disconnected.monitor.start();
  [...disconnected.listeners][0]();assert.equal(disconnected.monitor.active,false);
  assert.match(disconnected.statuses.at(-1).error,/disconnected/);

  const denied=deferred(),failed=fixture({permission:denied});
  const failure=failed.monitor.start();denied.reject(Object.assign(new Error('denied'),{name:'NotAllowedError'}));
  assert.equal(await failure,false);assert.match(failed.statuses.at(-1).error,/Allow microphone/);
  assert.equal(failed.monitor.wanted,false);

  const cases={
    'Mute.':'mute','Hey IRIS, please turn the audio off.':'mute','Stop speaking!':'mute',
    'Unmute':'unmute','iris, audio on please.':'unmute','Start a new conversation.':'newchat',
    'show me my memories':'memories','Show tasks':'tasks','View the council review':'council',
    'show voice commands':'help','close the panel':'close','approve this action':'approve',
    'Cancel that action.':'decline'
  };
  for(const [input,expected] of Object.entries(cases))assert.equal(parseVoiceCommand(input),expected,input);
  for(const input of ['Should I mute my phone?','Tell me about audio on Windows','How do I start a new chat?',
    'I approve of the idea','What are my tasks for tomorrow?','Remember that I mute notifications at work',
    'Can you explain the council decision?','yes','no','',null,42])assert.equal(parseVoiceCommand(input),null,String(input));
  console.log('Standby permission races, local detection, busy suppression, cleanup, and precise voice commands passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
