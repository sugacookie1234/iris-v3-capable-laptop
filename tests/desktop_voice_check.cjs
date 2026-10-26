const assert=require('node:assert/strict');
const {RecordedVoiceInput,encodeWav,resolveInputDevice}=require('../web/voice-input.js');
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

  const devices=[
    {kind:'audioinput',deviceId:'default',label:'Default - Microphone Array (Realtek(R) Audio)'},
    {kind:'audioinput',deviceId:'communications',label:'Communications - Microphone Array (Realtek(R) Audio)'},
    {kind:'audioinput',deviceId:'realtek',label:'Microphone Array (Realtek(R) Audio)'},
    {kind:'audioinput',deviceId:'webcam',label:'Microphone (HD Webcam C615) (046d:082c)'},
    {kind:'audiooutput',deviceId:'speaker',label:'Microphone Array (Realtek(R) Audio)'}
  ];
  assert.equal(resolveInputDevice(' Microphone Array (Realtek(R) Audio) ',devices),'realtek');
  assert.equal(resolveInputDevice('Microphone Array (Realtek(R) Aud',devices),'realtek');
  assert.equal(resolveInputDevice('Microphone (HD Webcam C615)',devices),'webcam');
  assert.equal(resolveInputDevice('Communications - Microphone (HD Webcam C615)',devices),'webcam');
  assert.equal(resolveInputDevice('Microphone Array (Realtek(R) Audio)',[...devices,devices[2]]),'realtek');
  for(const name of ['Microsoft Sound Mapper - Input','Primary Sound Capture Driver'])
    assert.equal(resolveInputDevice(name,devices),'default');
  for(const name of ['Microphone','Missing USB Input','',null])
    assert.throws(()=>resolveInputDevice(name,devices),/could not be matched.*IRIS_INPUT_DEVICE/);
  const ambiguous=[...devices,{kind:'audioinput',deviceId:'other-realtek',label:'Microphone Array (Realtek(R) Audio)'}];
  assert.throws(()=>resolveInputDevice('Microphone Array (Realtek(R) Audio)',ambiguous),/More than one/);
  assert.throws(()=>resolveInputDevice('Microphone Array (Realtek(R) Aud',ambiguous),/More than one/);
  assert.throws(()=>resolveInputDevice('Microphone Array (Realtek(R) Audio)',devices.filter(device=>device.deviceId!=='realtek')),/could not be matched/);
  // A unique exact match wins over another device that extends its label.
  assert.equal(resolveInputDevice('Microphone Array (Realtek(R) Audio)',[...devices,
    {kind:'audioinput',deviceId:'external',label:'Microphone Array (Realtek(R) Audio) External'}]),'realtek');

  let selected=null,enumerations=0;
  const matched=fixture({devices:{enumerateDevices:async()=>{enumerations++;return devices;},getUserMedia:async options=>{
    selected=options;return {getTracks:()=>[{stop:()=>{}}]};
  }}});
  await matched.input.start(8000,'Microphone Array (Realtek(R) Aud');
  assert.deepEqual(selected.audio.deviceId,{exact:'realtek'});assert.equal(enumerations,1);
  assert.equal(matched.input.active,true);matched.input.cancel();
  selected=null;await matched.input.start();assert.equal(enumerations,1);
  assert.equal(Object.hasOwn(selected.audio,'deviceId'),false);matched.input.cancel();
  await matched.input.start(8000,'Microsoft Sound Mapper - Input');
  assert.deepEqual(selected.audio.deviceId,{exact:'default'});matched.input.cancel();

  let captureRequests=0,enumerate;
  const matchingCancelled=fixture({devices:{enumerateDevices:()=>new Promise(resolve=>enumerate=resolve),
    getUserMedia:async()=>{captureRequests++;return {getTracks:()=>[]};}}});
  const resolving=matchingCancelled.input.start(8000,'Microphone Array (Realtek(R) Aud');
  matchingCancelled.input.cancel();enumerate(devices);await resolving;
  assert.equal(captureRequests,0);assert.deepEqual(matchingCancelled.errors,[]);assert.equal(matchingCancelled.input.active,false);

  const unmatched=fixture({devices:{enumerateDevices:async()=>devices,
    getUserMedia:async()=>{captureRequests++;return {getTracks:()=>[]};}}});
  await unmatched.input.start(8000,'Missing USB Input');assert.equal(captureRequests,0);
  assert.match(unmatched.errors[0],/could not be matched/);assert.equal(unmatched.input.active,false);
  const unplugged=fixture({devices:{enumerateDevices:async()=>devices,getUserMedia:async()=>{throw {name:'OverconstrainedError'};}}});
  await unplugged.input.start(8000,'Microphone Array (Realtek(R) Aud');assert.match(unplugged.errors[0],/no longer available/);
  const wav=await encodeWav(new Float32Array([-2,0,2])).arrayBuffer();const view=new DataView(wav);
  assert.equal(view.getUint32(24,true),16000);assert.equal(view.getUint16(22,true),1);
  assert.equal(view.getInt16(44,true),-32768);assert.equal(view.getInt16(48,true),32767);
  console.log('Voice capture, exact native microphone matching, WAV encoding, permission, release, and cancellation checks passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
