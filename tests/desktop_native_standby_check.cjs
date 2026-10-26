const assert=require('node:assert/strict');
const {NativeStandbyMonitor}=require('../web/native-standby.js');

function deferred(){let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};}
async function flush(){for(let index=0;index<12;index++)await Promise.resolve();}
function fixture({wakeSetsBusy=true,options={}}={}) {
  const calls=[],statuses=[],timers=new Map(),context={state:'running'};
  let clock=0,busy=false,wakes=0,owner=0,timer=0,inFlight=0,maxInFlight=0;
  const monitor=new NativeStandbyMonitor({context,api:(path,data)=>{
    assert.equal(path,'/api/clap');
    const result=deferred();inFlight++;maxInFlight=Math.max(maxInFlight,inFlight);
    calls.push({data,...result});return result.promise.finally(()=>inFlight--);
  },onTrigger:()=>{wakes++;if(wakeSetsBusy)busy=true;},onStatus:(active,error)=>statuses.push({active,error}),
  isBusy:()=>busy,now:()=>clock,ownerFactory:()=>`owner_${String(++owner).padStart(20,'0')}`,
  schedule:(callback,delay)=>{assert.equal(delay,250);const id=timer++;timers.set(id,callback);return id;},
  unschedule:id=>timers.delete(id),...options});
  return {monitor,calls,statuses,context,timers,
    get wakes(){return wakes;},get maxInFlight(){return maxInFlight;},
    set busy(value){busy=value;},advance(ms){clock+=ms;},
    async next(ms=250){clock+=ms;assert.equal(timers.size,1);const [id,callback]=timers.entries().next().value;timers.delete(id);callback();await flush();},
    async respond(sequence=0,extra={}){calls.at(-1).resolve({active:true,starting:false,sequence,error:null,device:'Microphone Array (Realtek Audio)',...extra});await flush();},
    async start(sequence=0){const pending=monitor.start();await flush();await this.respond(sequence);assert.equal(await pending,true);},
    async stop(){const stopping=monitor.stop();await flush();if(calls.at(-1)?.data.action==='stop'){calls.at(-1).resolve({active:false,sequence:0});await flush();}await stopping;}
  };
}

(async()=>{
  // Startup is asynchronous and shares a single request/promise. Existing
  // counter values never replay a clap on initial activation.
  const initial=fixture();const first=initial.monitor.start();assert.equal(initial.monitor.start(),first);
  await flush();assert.equal(initial.calls.length,1);
  await initial.respond(12,{active:false,starting:true});assert.equal(initial.monitor.active,false);
  await initial.next();await initial.respond(13);assert.equal(await first,true);
  assert.equal(initial.wakes,0);assert.equal(initial.monitor.active,true);
  assert.equal(initial.monitor.device,'Microphone Array (Realtek Audio)');
  assert.equal(await initial.monitor.start(),true);assert.equal(initial.calls.length,2);
  await initial.next();assert.equal(initial.calls.at(-1).data.busy,true);await initial.respond(13);
  await initial.next();await initial.respond(14);assert.equal(initial.wakes,1);
  await initial.next();assert.equal(initial.calls.at(-1).data.busy,true);await initial.respond(15);
  assert.equal(initial.wakes,1);initial.busy=false;
  await initial.next();await initial.respond(15);assert.equal(initial.wakes,1);
  await initial.next();await initial.respond(16);assert.equal(initial.wakes,2);
  await initial.stop();assert.equal(initial.monitor.active,false);assert.equal(initial.monitor.device,null);assert.equal(initial.timers.size,0);
  const stoppedCalls=initial.calls.length;initial.monitor.stop();await flush();assert.equal(initial.calls.length,stoppedCalls);
  assert.equal(initial.maxInFlight,1);

  // The local latch forces a busy acknowledgement even when a recording
  // callback has not yet updated application state.
  const latch=fixture({wakeSetsBusy:false});await latch.start();await latch.next();await latch.respond(1);
  assert.equal(latch.wakes,1);await latch.next();assert.equal(latch.calls.at(-1).data.busy,true);
  await latch.respond(2);assert.equal(latch.wakes,1);
  await latch.next();assert.equal(latch.calls.at(-1).data.busy,true);await latch.respond(2);
  await latch.next();assert.equal(latch.calls.at(-1).data.busy,false);await latch.respond(2);
  await latch.next();await latch.respond(3);assert.equal(latch.wakes,2);await latch.stop();

  // Both busy-at-send and busy-at-response discard a wake instead of saving it
  // for the next idle period. Suppressed events still acknowledge the native
  // detector so it can rearm on the following idle heartbeat.
  const suppression=fixture({wakeSetsBusy:false});await suppression.start();
  suppression.busy=true;await suppression.next();suppression.busy=false;await suppression.respond(1);
  assert.equal(suppression.wakes,0);
  await suppression.next();suppression.busy=true;await suppression.respond(2);suppression.busy=false;
  await suppression.next();await suppression.respond(2);assert.equal(suppression.wakes,0);
  await suppression.next();assert.equal(suppression.calls.at(-1).data.busy,false);await suppression.respond(2);
  suppression.context.state='suspended';await suppression.next();assert.equal(suppression.calls.at(-1).data.busy,false);
  await suppression.respond(3);assert.equal(suppression.wakes,1);
  await suppression.next();await suppression.respond(3);suppression.context.state='running';
  await suppression.next();await suppression.respond(4);assert.equal(suppression.wakes,2);await suppression.stop();

  // A slow response or resumed background timer cannot wake from an old clap.
  const delayed=fixture({wakeSetsBusy:false});await delayed.start();await delayed.next();
  delayed.advance(1500);await delayed.respond(1);assert.equal(delayed.wakes,0);
  await delayed.next(3500);assert.equal(delayed.calls.at(-1).data.busy,true);await delayed.respond(2);assert.equal(delayed.wakes,0);
  await delayed.next();assert.equal(delayed.calls.at(-1).data.busy,true);await delayed.respond(2);
  await delayed.next();await delayed.respond(3);assert.equal(delayed.wakes,1);
  await delayed.next();await delayed.respond(3); // Acknowledge the wake latch.
  await delayed.next();await delayed.respond(0);assert.equal(delayed.wakes,1); // Server counter reset.
  await delayed.stop();

  // If a suspended client loses its server lease, reopening the device gets
  // a fresh startup window and sequence baseline rather than a phantom wake.
  const recovered=fixture({wakeSetsBusy:false});await recovered.start(3);await recovered.next();await recovered.respond(3);
  await recovered.next(20000);await recovered.respond(4,{active:false,starting:true});
  assert.equal(recovered.monitor.active,false);assert.equal(recovered.monitor.wanted,true);
  await recovered.next();await recovered.respond(5);assert.equal(recovered.monitor.active,true);
  assert.equal(recovered.wakes,0);await recovered.next();await recovered.respond(5);
  await recovered.next();await recovered.respond(6);
  assert.equal(recovered.wakes,1);await recovered.stop();

  // Cancellation resolves start immediately. Cleanup and the next activation
  // serialize behind the in-flight request, with distinct ownership tokens.
  const race=fixture();const obsolete=race.monitor.start();await flush();const oldOwner=race.calls[0].data.owner;
  race.monitor.stop();assert.equal(await obsolete,false);const latest=race.monitor.start();await flush();
  assert.equal(race.calls.length,1);await race.respond(5);
  assert.equal(race.calls.at(-1).data.action,'stop');assert.equal(race.calls.at(-1).data.owner,oldOwner);
  race.calls.at(-1).resolve({active:false,sequence:5});await flush();
  assert.equal(race.calls.at(-1).data.action,'update');assert.notEqual(race.calls.at(-1).data.owner,oldOwner);
  await race.respond(6);assert.equal(await latest,true);assert.equal(race.wakes,0);assert.equal(race.maxInFlight,1);
  await race.stop();

  const immediate=fixture();const canceled=immediate.monitor.start();immediate.monitor.stop();
  assert.equal(await canceled,false);await flush();assert.equal(immediate.calls.length,1);
  assert.equal(immediate.calls[0].data.action,'stop');immediate.calls[0].resolve({active:false,sequence:0});await flush();

  // Backend and connection failures surface directly, without silently
  // replacing the tested native detector with browser signal processing.
  const unavailable=fixture();const missing=unavailable.monitor.start();await flush();
  await unavailable.respond(0,{active:false,error:'No default microphone. Choose an input in Windows.'});
  assert.equal(await missing,false);assert.match(unavailable.statuses.at(-1).error,/No default microphone/);
  assert.equal(unavailable.monitor.wanted,false);assert.equal(unavailable.calls.at(-1).data.action,'stop');
  unavailable.calls.at(-1).resolve({active:false,sequence:0});await flush();

  const disconnected=fixture();await disconnected.start();await disconnected.next();
  disconnected.calls.at(-1).reject(new Error('Local connection timed out.'));await flush();
  assert.equal(disconnected.monitor.active,false);assert.match(disconnected.statuses.at(-1).error,/timed out/);
  disconnected.calls.at(-1).reject(new Error('Server closed.'));await flush();assert.equal(disconnected.timers.size,0);

  const timeout=fixture({options:{startupTimeoutMs:500}});const starting=timeout.monitor.start();await flush();
  await timeout.respond(0,{active:false,starting:true});await timeout.next(500);
  await timeout.respond(0,{active:false,starting:true});assert.equal(await starting,false);
  assert.match(timeout.statuses.at(-1).error,/too long/);timeout.calls.at(-1).resolve({active:false,sequence:0});await flush();

  const invalid=fixture({options:{ownerFactory:()=>''}});assert.equal(await invalid.monitor.start(),false);
  assert.equal(invalid.calls.length,0);assert.match(invalid.statuses.at(-1).error,/ownership/);
  console.log('Native standby startup, heartbeat serialization, wake suppression, owner cleanup, cancellation, and failures passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
