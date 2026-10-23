const assert=require('node:assert/strict');
const {RecordedVoiceInput,encodeWav}=require('../web/voice-input.js');
class Recorder {
  static isTypeSupported(){return true;}
  constructor(){this.state='inactive';}
  start(){this.state='recording';}
  stop(){this.state='inactive';this.ondataavailable?.({data:new Blob(['x'.repeat(64)])});this.onstop?.();}
}
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function fixture(overrides={}) {
  const result={texts:[],errors:[],states:[],requests:[],stops:0};
  const stream={getTracks:()=>[{stop:()=>result.stops++}]};
  result.input=new RecordedVoiceInput({devices:{getUserMedia:async()=>stream},Recorder,
    request:async(path,options)=>{result.requests.push({path,options});return {ok:true,json:async()=>({text:'hello iris'})};},
    convert:async()=>encodeWav(new Float32Array(160)),
    onState:s=>result.states.push(s),onText:s=>result.texts.push(s),onError:s=>result.errors.push(s),...overrides});
  return result;
}
(async()=>{
  // Browser fetch requires Window as its receiver; a method on the recorder
  // must not pass the recorder instance as `this` to the native function.
  const originalFetch=globalThis.fetch;
  let nativeCalls=0;
  try {
    globalThis.fetch=async function(path,options){
      assert.equal(this,globalThis,'Native fetch must retain its global receiver');
      assert.equal(path,'/api/transcribe');assert.equal(options.method,'POST');nativeCalls++;
      return {ok:true,json:async()=>({text:'default transport works'})};
    };
    const native=fixture({request:undefined});await native.input.start();native.input.stop();await tick();
    assert.deepEqual(native.errors,[]);assert.deepEqual(native.texts,['default transport works']);
    assert.equal(nativeCalls,1);
  } finally {globalThis.fetch=originalFetch;}
  const f=fixture();await f.input.start();f.input.stop();await tick();
  assert.deepEqual(f.texts,['hello iris']);assert.equal(f.requests[0].path,'/api/transcribe');
  assert.equal(f.requests[0].options.headers['Content-Type'],'audio/wav');assert.ok(f.stops>0);
  assert.equal(f.input.active,false);assert.deepEqual(f.errors,[]);
  for(const speech of [{engine:'fish',device:'cloud'},{engine:'faster-whisper',device:'cpu',fallback:'Fish unavailable'}]){
    const order=[];
    const withStatus=fixture({request:async()=>({ok:true,json:async()=>({text:'recognized',speech})}),
      onBackend:s=>{assert.deepEqual(s,speech);order.push('backend');},onText:()=>order.push('text')});
    await withStatus.input.start();withStatus.input.stop();await tick();
    assert.deepEqual(order,['backend','text']);
  }
  let permission;const pending=fixture({devices:{getUserMedia:()=>new Promise(r=>permission=r)}});
  const starting=pending.input.start();pending.input.stop();let stopped=false;
  permission({getTracks:()=>[{stop:()=>stopped=true}]});await starting;
  assert.equal(stopped,true);assert.equal(pending.requests.length,0);
  let converted;const cancelled=fixture({convert:()=>new Promise(r=>converted=r)});
  await cancelled.input.start();cancelled.input.stop();cancelled.input.cancel();converted(new Blob(['audio']));await tick();
  assert.equal(cancelled.requests.length,0);assert.deepEqual(cancelled.texts,[]);
  const denied=fixture({devices:{getUserMedia:async()=>{throw {name:'NotAllowedError'};}}});
  await denied.input.start();assert.match(denied.errors[0],/denied/);assert.equal(denied.input.active,false);
  const wav=await encodeWav(new Float32Array([-2,0,2])).arrayBuffer();const view=new DataView(wav);
  assert.equal(view.getUint32(24,true),16000);assert.equal(view.getUint16(22,true),1);
  assert.equal(view.getInt16(44,true),-32768);assert.equal(view.getInt16(48,true),32767);
  console.log('Voice capture, WAV encoding, permission, release, and cancellation checks passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
