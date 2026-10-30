const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {DoubleClapDetector}=require('../web/clap.js');
const {parseVoiceCommand}=require('../web/standby.js');

class Element {
  constructor(id=''){this.id=id;this.children=[];this.events={};this.style={setProperty(){}};this.open=false;this.paused=true;this.textContent='';this.value='';this.attributes={};}
  addEventListener(name,callback){(this.events[name]??=[]).push(callback);}
  emit(name,event={}){for(const callback of this.events[name]||[])callback({target:this,preventDefault(){},...event});}
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this.children=children;}
  remove(){this.removed=true;}
  setAttribute(name,value){this.attributes[name]=value;}
  removeAttribute(name){delete this.attributes[name];}
  querySelector(selector){if(selector==='button')return this.button??=new Element('submit');throw new Error(selector);}
  closest(){return null;}
  showModal(){this.open=true;}
  close(){this.open=false;}
  pause(){this.paused=true;}
  load(){}
}
function app({recording=true,desktop=false,nativeWindow=desktop,microphonePermission,standbyPreference,jobs=false}={}){
  const elements={};
  for(const match of fs.readFileSync(path.join(__dirname,'../web/index.html'),'utf8').matchAll(/id="([^"]+)"/g))elements[match[1]]=new Element(match[1]);
  const document={body:new Element('body'),events:{},getElementById:id=>elements[id]||null,createElement:()=>new Element(),addEventListener:Element.prototype.addEventListener,emit:Element.prototype.emit};
  const window={events:{},addEventListener:Element.prototype.addEventListener,emit:Element.prototype.emit};
  const requests=[],timeouts=new Map(),intervals=new Map(),storage=new Map();let nextTimer=1,monitor,input,autoEnd=true,playCalls=0,permissionStops=0;
  if(standbyPreference!==undefined)storage.set('iris.standby',standbyPreference);
  const responses={'/api/status':{model:'example',speech:{},desktop_window:desktop},'/api/approval':{},'/api/chat':{reply:'Hello.',route:'DEEP'},'/api/voice':{url:'/voice-test'},'/api/reset':{},'/api/memories':{items:[]},'/api/tasks':{items:[]}};
  const voice=elements.voice;
  voice.play=function(){playCalls++;this.paused=false;this.onplaying?.();if(autoEnd)queueMicrotask(()=>{this.paused=true;this.onended?.();});return Promise.resolve();};
  class AudioContext {
    constructor(){this.state='running';this.destination={};}
    resume(){this.state='running';return Promise.resolve();}
    createMediaElementSource(){return {connect(){}};}
    createAnalyser(){return {connect(){},getByteTimeDomainData(samples){samples.fill(128);}};}
  }
  class Monitor {
    constructor(options){this.options=options;this.starts=0;this.stops=0;this.active=false;this.device='Microphone (Realtek Audio)';monitor=this;}
    async start(){this.starts++;this.active=true;this.options.onStatus(true,null);return true;}
    stop(){this.stops++;this.active=false;this.options.onStatus(false,null);}
  }
  class Input {
    constructor(options){this.options=options;this.active=false;this.starts=[];this.cancels=0;input=this;}
    start(duration,device,options){this.active=true;this.starts.push(duration);this.device=device;this.recordOptions=options;this.options.onState('listening');}
    stop(){this.active=false;this.options.onState('idle');}
    cancel(){this.cancels++;this.stop();}
  }
  class Widgets {
    start(){}
    stop(){this.stopped=true;}
    locate(){return Promise.resolve({temperature_c:12,feels_like_c:11,condition:'Clear'});}
    loadMarkets(){return Promise.resolve({items:[]});}
  }
  window.AudioContext=AudioContext;
  if(nativeWindow)window.chrome={webview:{}};
  const navigator={mediaDevices:{getUserMedia:async()=>({getTracks:()=>[{stop:()=>permissionStops++}]})}};
  if(microphonePermission!==undefined)navigator.permissions={query:async options=>{assert.equal(options.name,'microphone');return {state:microphonePermission};}};
  const localStorage={getItem:key=>storage.get(key)??null,setItem:(key,value)=>storage.set(key,String(value))};
  window.localStorage=localStorage;
  const sandbox={document,window,navigator,localStorage,DoubleClapDetector,NativeStandbyMonitor:Monitor,
    RecordedVoiceInput:Input,DashboardWidgets:Widgets,parseVoiceCommand,console,Date,Uint8Array,AbortController,URL,
    requestAnimationFrame:()=>1,
    setTimeout:(fn,delay)=>{const id=nextTimer++;timeouts.set(id,{fn,delay});return id;},clearTimeout:id=>timeouts.delete(id),
    setInterval:(fn,delay)=>{const id=nextTimer++;intervals.set(id,{fn,delay});return id;},clearInterval:id=>intervals.delete(id),
    fetch:async(url,options={})=>{const body=options.body?JSON.parse(options.body):undefined;requests.push({url,body});
      const response=typeof responses[url]==='function'?await responses[url](body):responses[url];
      if(response===undefined)throw new Error('Unexpected request '+url);
      return {ok:true,json:async()=>response};}
  };
  if(recording)sandbox.MediaRecorder=function(){};
  const context=vm.createContext(sandbox);
  if(jobs){responses['/api/jobs']={jobs:[]};vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/jobs.js'),'utf8'),context);}
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/app.js'),'utf8'),context);
  return {elements,document,window,requests,responses,intervals,storage,timeouts,
    get monitor(){return monitor;},get input(){return input;},set autoEnd(value){autoEnd=value;},
    get playCalls(){return playCalls;},
    get permissionStops(){return permissionStops;},
    run:code=>vm.runInContext(code,context),
    flush:async()=>{for(let i=0;i<12;i++)await Promise.resolve();},
    heard:async text=>{input.active=false;input.options.onState('idle');await input.options.onText(text);},
    finishSpeech:()=>{voice.paused=true;voice.onended?.();}
  };
}

(async()=>{
  // Submit through the actual form handler: native WebView can expose the
  // synthesis property without providing a usable speech service.
  const submit=(view,text)=>{
    view.elements.typeBox.value=text;let prevented=false;
    view.elements.typeForm.emit('submit',{preventDefault(){prevented=true;}});
    assert.equal(prevented,true,'Submitting must not reload the application');
  };
  const chatRequests=view=>view.requests.filter(item=>item.url==='/api/chat');
  const cleanVoice=app();await cleanVoice.flush();
  cleanVoice.run('activated=true;window.spoken=[];window.SpeechSynthesisUtterance=class {constructor(text){this.text=text;}};window.speechSynthesis={cancel(){},speak(value){window.spoken.push(value.text);value.onend();}};voice.play=()=>Promise.reject(new Error("Synthetic Fish failure"));');
  cleanVoice.responses['/api/voice']={url:'/voice-test',fallback_text:'Ready, Iris.'};
  await cleanVoice.run('speak("[sigh] Ready, IRIS.")');
  assert.equal(cleanVoice.window.spoken.join('|'),'Ready, Iris.','Device fallback must use the cleaned speech text');
  cleanVoice.responses['/api/voice']={url:null,fallback_text:''};
  await cleanVoice.run('speak("[sighing]")');
  assert.equal(cleanVoice.window.spoken.length,1,'Cue-only output must stay silent');
  cleanVoice.responses['/api/voice']=()=>{throw new Error('Synthetic ticket failure');};
  await cleanVoice.run('speak("[sigh] unsafe fallback")');
  assert.equal(cleanVoice.window.spoken.length,1,'Missing cleaned text must not resurrect raw acting cues');
  for(const synthesis of ['null','{cancel(){throw new Error("Device speech unavailable");}}']){
    const typed=app();await typed.flush();
    typed.run('window.speechSynthesis=globalThis.speechSynthesis='+synthesis);
    submit(typed,'Help me plan tomorrow');await typed.flush();
    assert.equal(chatRequests(typed).length,1,'Unavailable device speech must not block text chat');
    assert.equal(typed.elements.log.children[0].children[1].textContent,'Help me plan tomorrow');
    assert.equal(typed.elements.log.children.at(-1).children[1].textContent,'Hello.');
    assert.equal(typed.elements.typeBox.value,'','An accepted message clears its draft');
    assert.equal(typed.elements.typeForm.querySelector('button').disabled,false);
  }

  const blockedRecorder=app();await blockedRecorder.flush();
  blockedRecorder.input.active=true;
  blockedRecorder.input.cancel=()=>{throw new Error('Recorder could not stop');};
  submit(blockedRecorder,'Keep this draft');await blockedRecorder.flush();
  assert.equal(blockedRecorder.elements.typeBox.value,'Keep this draft');
  assert.equal(chatRequests(blockedRecorder).length,0,'Failed recorder cleanup must not send an unnoticed request');
  assert.match(blockedRecorder.elements.toast.textContent,/Recorder could not stop/);
  assert.equal(blockedRecorder.elements.toast.style.display,'block');
  blockedRecorder.input.active=false;
  submit(blockedRecorder,'Keep this draft');await blockedRecorder.flush();
  assert.equal(chatRequests(blockedRecorder).length,1,'A failed submission must allow a retry');

  const busyForm=app();await busyForm.flush();let finishBusy;
  busyForm.responses['/api/chat']=()=>new Promise(resolve=>finishBusy=resolve);
  const pendingChat=busyForm.run('send("Already processing a request")');await busyForm.flush();
  submit(busyForm,'Send this later');await busyForm.flush();
  assert.equal(busyForm.elements.typeBox.value,'Send this later','Busy submissions retain their draft');
  assert.equal(chatRequests(busyForm).length,1);
  finishBusy({reply:'Done.',route:'FAST'});await pendingChat;
  assert.equal(busyForm.elements.typeBox.value,'Send this later');

  const nextDraft=app();await nextDraft.flush();let finishTyped;
  nextDraft.responses['/api/chat']=()=>new Promise(resolve=>finishTyped=resolve);
  submit(nextDraft,'First typed question');await nextDraft.flush();
  nextDraft.elements.typeBox.value='A newer draft';
  finishTyped({reply:'First answer.',route:'FAST'});await nextDraft.flush();
  assert.equal(nextDraft.elements.typeBox.value,'A newer draft','Finishing chat must preserve newer typing');

  const failedCommand=app();await failedCommand.flush();
  failedCommand.run('globalThis.rejectWeather=null; globalThis.weatherCalls=0; widgets.locate=()=>{weatherCalls++;return new Promise((resolve,reject)=>rejectWeather=reject)}');
  submit(failedCommand,'Weather update');await failedCommand.flush();
  submit(failedCommand,'Weather update');await failedCommand.flush();
  assert.equal(failedCommand.run('weatherCalls'),1,'Repeated Send must not duplicate a pending local command');
  failedCommand.run('rejectWeather(new Error("Weather request failed"))');await failedCommand.flush();
  assert.equal(failedCommand.elements.typeBox.value,'Weather update');
  assert.match(failedCommand.elements.toast.textContent,/Weather request failed/);
  assert.equal(failedCommand.elements.toast.style.display,'block');
  assert.equal(chatRequests(failedCommand).length,0,'A failed local command must not fall through to the model');

  const commandDraft=app();await commandDraft.flush();
  commandDraft.run('globalThis.finishWeather=null; widgets.locate=()=>new Promise(resolve=>finishWeather=resolve)');
  submit(commandDraft,'Weather update');await commandDraft.flush();
  commandDraft.elements.typeBox.value='My next request';
  commandDraft.run('finishWeather({temperature_c:12,condition:"Clear"})');await commandDraft.flush();
  assert.equal(commandDraft.elements.typeBox.value,'My next request','Completing a local command must preserve newer typing');
  assert.match(commandDraft.elements.log.children.at(-1).children[1].textContent,/12 degrees Celsius/);
  assert.equal(chatRequests(commandDraft).length,0);

  const follow=app();await follow.flush();await follow.elements.wake.onclick();
  await follow.run('send("A typed question")');
  assert.equal(follow.run('followUpTimer'),null,'Typing never opens an automatic recording');
  await follow.heard('A spoken question');
  const followTimer=follow.run('followUpTimer');assert.ok(followTimer);
  assert.equal(follow.input.active,false,'Follow-up waits for playback and the echo gap');
  follow.timeouts.get(followTimer).fn();await follow.flush();
  assert.equal(follow.input.active,true);assert.equal(follow.input.recordOptions.autoStop,true);
  assert.equal(follow.input.recordOptions.initialSilenceMs,5000);
  assert.equal(follow.elements.status.textContent,'Anything else?');
  const beforeSilence=chatRequests(follow).length;
  follow.input.cancel();follow.input.options.onSilence();await follow.flush();
  assert.equal(chatRequests(follow).length,beforeSilence,'Quiet follow-up does not invoke the model');
  assert.equal(follow.run('followUpTimer'),null,'Quiet follow-up does not reopen itself');
  await follow.heard('That’s all');
  assert.equal(follow.monitor.active,true,'Ending the conversation keeps double-clap standby');
  assert.equal(follow.run('followUpTimer'),null);
  assert.equal(chatRequests(follow).length,beforeSilence,'Ending conversation is a local command');

  for(const action of ['pauseMic()','document.emit("keydown",{code:"Escape"})','send("A typed interruption")']){
    const interrupted=app();await interrupted.flush();await interrupted.elements.wake.onclick();
    await interrupted.heard('Start a conversation');
    const timer=interrupted.run('followUpTimer'),callback=interrupted.timeouts.get(timer).fn;
    await interrupted.run(action);callback();await interrupted.flush();
    assert.equal(interrupted.input.active,false,'Cancelled follow-up stays cancelled: '+action);
  }
  const approvalFollow=app();await approvalFollow.flush();await approvalFollow.elements.wake.onclick();
  await approvalFollow.heard('A normal question');
  approvalFollow.timeouts.get(approvalFollow.run('followUpTimer')).fn();
  assert.equal(approvalFollow.input.active,true);
  approvalFollow.responses['/api/approval']={pending:{id:'fresh-action',summary:'A new action'}};
  await approvalFollow.run('pollApproval()');await approvalFollow.flush();
  assert.equal(approvalFollow.input.active,false,'A new approval cancels automatic follow-up capture');
  assert.equal(approvalFollow.run('followUpTimer'),null,'Approval requires a deliberate wake');

  const main=app();await main.flush();assert.equal(main.monitor,undefined,'Standby waits for a user activation');
  await main.elements.wake.onclick();assert.equal(main.monitor.active,true);assert.equal(main.elements.wake.hidden,true);
  assert.equal(main.permissionStops,1,'Permission bootstrap releases its temporary microphone stream');
  assert.equal(main.monitor.options.isBusy(),false);
  await main.run('send("Help me plan a trip")');
  assert.deepEqual(main.requests.find(item=>item.url==='/api/chat').body,{text:'Help me plan a trip',mode:'auto'});
  assert.equal(main.elements.routeLabel.textContent,'DEEP REASONING');

  await main.run('send("mute")');assert.equal(main.monitor.active,true);assert.equal(main.monitor.stops,0);
  assert.equal(main.monitor.options.isBusy(),false,'Muted replies do not disable clap wake');
  main.monitor.options.onTrigger();assert.equal(main.input.starts.at(-1),30000);assert.equal(main.input.recordOptions.autoStop,true);assert.equal(main.monitor.options.isBusy(),true);
  assert.equal(main.input.device,main.monitor.device,'Speech uses the native clap listener microphone');
  await main.heard('unmute');assert.equal(main.monitor.active,true);assert.equal(main.monitor.options.isBusy(),false);
  await main.run('send("pause mic")');assert.equal(main.monitor.active,false);assert.equal(main.monitor.stops,1);
  const captures=main.input.starts.length;main.run('startListening(true)');assert.equal(main.input.starts.length,captures);
  await main.elements.muteBtn.onclick();assert.equal(main.monitor.active,true);

  const beforeRecovery=main.input.starts.length;
  main.run('audioCtx.state="suspended"; audioCtx.onstatechange()');
  assert.equal(main.elements.standbyLabel.textContent,'STANDBY ENABLED','Native clap detection is independent of playback audio');
  assert.match(main.elements.wakeHint.textContent,/Double clap/);
  main.run('coreAction()');await main.flush();
  assert.equal(main.run('audioCtx.state'),'running');
  assert.equal(main.elements.standbyLabel.textContent,'STANDBY ENABLED');
  assert.equal(main.input.starts.length,beforeRecovery,'The first core click restores suspended standby instead of recording a request');

  // Existing reply playback must settle before an immediate spoken-control reply.
  main.autoEnd=false;const oldSpeech=main.run('speak("An older response")');await main.flush();
  assert.equal(main.monitor.options.isBusy(),true,'IRIS cannot trigger itself while speaking');
  const newSpeech=main.run('send("what time is it")');await main.flush();
  let oldSettled=false;oldSpeech.then(()=>oldSettled=true);await main.flush();assert.equal(oldSettled,true,'Replacing speech resolves its prior completion');
  main.finishSpeech();await newSpeech;assert.equal(main.monitor.options.isBusy(),false,'Standby resumes after speech');
  main.autoEnd=true;

  // Interrupting playback with a new request must not let the older send()
  // release the busy state while the newer chat request is still pending.
  const overlapping=app();await overlapping.flush();await overlapping.elements.wake.onclick();
  overlapping.autoEnd=false;const firstRequest=overlapping.run('send("First question")');await overlapping.flush();
  let resolveChat;
  overlapping.responses['/api/chat']=()=>new Promise(resolve=>resolveChat=resolve);
  const nextRequest=overlapping.run('send("Next question")');await overlapping.flush();await firstRequest;
  assert.equal(overlapping.run('busy'),true,'The newer request owns the busy state');
  assert.equal(overlapping.monitor.options.isBusy(),true,'Clap cannot interrupt a pending chat request');
  assert.equal(overlapping.elements.typeForm.querySelector('button').disabled,true);
  overlapping.autoEnd=true;resolveChat({reply:'Second response.',route:'FAST'});await nextRequest;
  assert.equal(overlapping.run('busy'),false);

  const approvalPosts=()=>main.requests.filter(item=>item.url==='/api/approval'&&item.body);
  await main.run('send("approve")');assert.equal(approvalPosts().length,0,'Approval is scoped to a visible pending action');
  main.responses['/api/approval']={pending:{id:'action-a',summary:'Open a test document'}};
  await main.run('pollApproval()');await main.flush();assert.equal(main.elements.approval.open,true);
  main.run('startListening(true)');
  main.responses['/api/approval']={pending:{id:'action-b',summary:'A different action'}};
  await main.run('pollApproval()');await main.flush();
  await main.heard('approve');assert.equal(approvalPosts().length,0,'Delayed recognition for A must not approve B');
  main.run('startListening(true)');await main.heard('approve');
  assert.deepEqual(approvalPosts().at(-1).body,{id:'action-b',approved:true});

  // A recording started before any approval appeared cannot approve a later action.
  main.responses['/api/approval']={};await main.run('pollApproval()');
  main.run('startListening(true)');
  main.responses['/api/approval']={pending:{id:'action-c',summary:'One more action'}};
  await main.run('pollApproval()');await main.flush();const before=approvalPosts().length;
  await main.heard('approve');assert.equal(approvalPosts().length,before);
  await main.elements.declineBtn.onclick();assert.deepEqual(approvalPosts().at(-1).body,{id:'action-c',approved:false});

  main.window.emit('pagehide');assert.equal(main.monitor.active,false);assert.equal(main.input.active,false);assert.equal(main.intervals.size,0);

  // AudioContext.resume may wait for a gesture or device recovery. A pause or
  // page exit while it is pending must invalidate the activation it belongs to.
  for(const cancel of ['pause','pagehide']){
    const deferred=app();await deferred.flush();
    deferred.run('initAudio(); audioCtx.state="suspended"; globalThis.releaseResume=null; audioCtx.resume=()=>new Promise(resolve=>releaseResume=resolve)');
    const activating=deferred.run('activate()');await deferred.flush();
    if(cancel==='pause')deferred.run('pauseMic()');else deferred.window.emit('pagehide');
    deferred.run('audioCtx.state="running"; releaseResume()');await activating;
    assert.equal(deferred.monitor.active,false,cancel+' must cancel activation before resume completes');
    assert.equal(deferred.monitor.starts,0,cancel+' must not reopen the microphone');
    if(cancel==='pause'){
      assert.equal(deferred.run('micPaused'),true,'The paused preference survives a delayed resume');
      assert.equal(deferred.storage.get('iris.standby'),'paused');
    }
  }

  // A voice response cancelled during resume must never begin playback later.
  for(const cancel of ['pause','pagehide']){
    const pendingPermission=app();await pendingPermission.flush();
    pendingPermission.run('globalThis.allowMic=null; globalThis.releasedTracks=0; navigator.mediaDevices.getUserMedia=()=>new Promise(resolve=>allowMic=resolve)');
    const enabling=pendingPermission.run('activate()');await pendingPermission.flush();
    if(cancel==='pause')pendingPermission.run('pauseMic()');else pendingPermission.window.emit('pagehide');
    pendingPermission.run('allowMic({getTracks:()=>[{stop:()=>releasedTracks++}]})');await enabling;
    assert.equal(pendingPermission.run('releasedTracks'),1,'A late permission result always releases its stream');
    assert.equal(pendingPermission.monitor.starts,0,'Canceled permission cannot enable native capture');
  }

  // A voice response cancelled during resume must never begin playback later.
  const cancelledSpeech=app();await cancelledSpeech.flush();await cancelledSpeech.elements.wake.onclick();
  cancelledSpeech.run('audioCtx.state="suspended"; globalThis.releaseResume=null; audioCtx.resume=()=>new Promise(resolve=>releaseResume=resolve)');
  const abandoned=cancelledSpeech.run('speak("Do not play this response")');await cancelledSpeech.flush();
  assert.equal(cancelledSpeech.run('typeof releaseResume'),'function');
  cancelledSpeech.run('pauseMic(); audioCtx.state="running"; releaseResume()');await abandoned;
  assert.equal(cancelledSpeech.playCalls,0,'Cancelled speech stays cancelled after audio resumes');

  const replacedSpeech=app();await replacedSpeech.flush();await replacedSpeech.elements.wake.onclick();
  replacedSpeech.run('audioCtx.state="suspended"; globalThis.resumes=[]; audioCtx.resume=()=>new Promise(resolve=>resumes.push(resolve))');
  const older=replacedSpeech.run('speak("Old response")');await replacedSpeech.flush();
  const newer=replacedSpeech.run('speak("Current response")');await replacedSpeech.flush();
  assert.equal(replacedSpeech.run('resumes.length'),2);
  replacedSpeech.run('audioCtx.state="running"; resumes[0]()');await older;
  assert.equal(replacedSpeech.playCalls,0,'Replacing a response invalidates its pending resume');
  replacedSpeech.run('resumes[1]()');await newer;
  assert.equal(replacedSpeech.playCalls,1,'Only the current response may start playback');

  // Replacing a media source can reject the old play() promise after the new
  // speech has installed handlers. Its cleanup must belong only to itself.
  const stalePlayback=app();await stalePlayback.flush();await stalePlayback.elements.wake.onclick();
  let rejectOldPlay;
  stalePlayback.elements.voice.play=()=>new Promise((resolve,reject)=>rejectOldPlay=reject);
  const oldPlayback=stalePlayback.run('speak("Obsolete playback")');await stalePlayback.flush();
  stalePlayback.elements.voice.play=()=>Promise.resolve();
  const currentPlayback=stalePlayback.run('speak("Current playback")');await stalePlayback.flush();
  const currentCompletion=stalePlayback.elements.voice.onended;
  assert.equal(typeof currentCompletion,'function');
  rejectOldPlay(new Error('The obsolete playback was interrupted'));await stalePlayback.flush();
  assert.equal(stalePlayback.elements.voice.onended,currentCompletion,'A stale play rejection must preserve current playback handlers');
  stalePlayback.finishSpeech();await Promise.all([oldPlayback,currentPlayback]);
  assert.equal(stalePlayback.monitor.options.isBusy(),false,'Current speech completes and returns to standby');

  // Native launches can restore standby only after microphone consent was
  // already granted. A deliberate pause survives a new application launch.
  const restored=app({desktop:true,microphonePermission:'granted',standbyPreference:'enabled'});await restored.flush();
  assert.equal(restored.monitor?.active,true,'Native standby restores after existing microphone consent');
  assert.equal(restored.storage.get('iris.standby'),'enabled');
  const previouslyConsented=app({desktop:true,microphonePermission:'granted'});await previouslyConsented.flush();
  assert.equal(previouslyConsented.monitor?.active,true,'An existing native permission is sufficient when no pause preference exists');
  for(const options of [
    {desktop:true,microphonePermission:'prompt'},
    {desktop:true,microphonePermission:'denied'},
    {desktop:true},
    {desktop:true,microphonePermission:'granted',standbyPreference:'paused'},
    {desktop:true,nativeWindow:false,microphonePermission:'granted',standbyPreference:'enabled'},
    {desktop:false,microphonePermission:'granted',standbyPreference:'enabled'}
  ]){
    const manual=app(options);await manual.flush();
    assert.equal(manual.monitor?.active??false,false,'Standby must wait for activation: '+JSON.stringify(options));
    assert.equal(manual.monitor?.starts??0,0);
  }
  restored.run('pauseMic()');assert.equal(restored.storage.get('iris.standby'),'paused');
  await restored.elements.muteBtn.onclick();assert.equal(restored.storage.get('iris.standby'),'enabled');

  // Local commands use the same normalized wording as their voice parser and
  // report widget failures without inventing permission or numeric readings.
  const local=app();await local.flush();
  await local.run('send("Iris, please, what time is it?")');
  assert.match(local.elements.log.children.at(-1).children[1].textContent,/It’s/);
  assert.equal(local.requests.filter(item=>item.url==='/api/chat').length,0);
  local.run('widgets.weatherMessage="Weather service is temporarily unavailable."; widgets.locate=async()=>null');
  await local.run('send("Please Iris, weather update")');
  assert.equal(local.elements.log.children.at(-1).children[1].textContent,'Weather service is temporarily unavailable.');
  local.run('widgets.locate=async()=>({temperature_c:12,feels_like_c:null})');
  await local.run('send("Weather update")');
  assert.equal(local.elements.log.children.at(-1).children[1].textContent,'Near you, it’s 12 degrees Celsius.');
  local.run('widgets.loadMarkets=async()=>({stale:true,items:[{symbol:"SPY",value:123.45,change_percent:null,as_of:"2026-10-23"}]})');
  await local.run('send("Iris, market update, please")');
  const marketReply=local.elements.log.children.at(-1).children[1].textContent;
  assert.match(marketReply,/cached daily closes/);assert.match(marketReply,/as of 2026-10-23/);
  assert.doesNotMatch(marketReply,/0\.00 percent|NaN/);
  assert.equal(local.requests.filter(item=>item.url==='/api/chat').length,0);

  const unsupported=app({recording:false});await unsupported.flush();await unsupported.elements.wake.onclick();
  unsupported.run('startListening(true)');assert.match(unsupported.elements.toast.textContent,/cannot record/);
  unsupported.document.emit('keydown',{code:'Escape',target:unsupported.elements.reactor});
  await unsupported.run('send("pause mic")');assert.equal(unsupported.monitor.active,false);
  const web=app();await web.flush();
  web.responses['/api/chat']={reply:'Sourced answer.',route:'WEB',sources:[
    {title:'<img src=x onerror=bad()>',url:'https://example.com/article'},
    {title:'Unsafe',url:'javascript:bad()'}]};
  await web.run('send("Search the web for a public question")');
  assert.equal(web.elements.routeLabel.textContent,'WEB SEARCH');
  const sources=web.elements.log.children.at(-1).children[1].children[0];
  assert.equal(sources.children.length,1,'Only safe source schemes become links');
  assert.equal(sources.children[0].textContent,'<img src=x onerror=bad()>','Source titles are text, never HTML');
  assert.equal(sources.children[0].href,'https://example.com/article');
  assert.equal(sources.children[0].target,'_blank');
  assert.equal(sources.children[0].rel,'noopener noreferrer');
  const localReply=app();await localReply.flush();await localReply.elements.wake.onclick();
  localReply.responses['/api/chat']={reply:'Found files: report.md, report-two.md.',spoken_reply:'Found two files. They are listed on screen.',route:'LOCAL'};
  await localReply.run('send("Find files named report")');
  assert.equal(localReply.elements.log.children.at(-1).children[1].textContent,'Found files: report.md, report-two.md.');
  assert.equal(localReply.elements.routeLabel.textContent,'LOCAL ACTION');
  assert.equal(localReply.requests.find(item=>item.url==='/api/voice').body.text,'Found two files. They are listed on screen.','Local detail stays visible without reading every filename aloud');
  const background=app({jobs:true});await background.flush();
  let backgroundJob={id:'test-briefing',kind:'notes_briefing',topic:'Orion',status:'queued',stage:'queued',attempts:1,completed_steps:[],can_cancel:true,can_resume:false,result_available:false};
  background.responses['/api/jobs']=()=>({jobs:[backgroundJob]});
  background.responses['/api/chat']={reply:'Started your briefing.',spoken_reply:'Started.',route:'LOCAL',job:backgroundJob};
  await background.run('send("Make a briefing from my notes on Orion")');await background.flush();
  assert.match(background.elements.jobsBtn.textContent,/1/);
  const lines=background.elements.log.children.length,plays=background.playCalls;
  background.run('listening=true;state="listening"');
  backgroundJob={...backgroundJob,status:'completed',stage:'done',can_cancel:false,result_available:true,result:{reply:'PRIVATE note detail'}};
  await background.run('jobs.poll()');assert.doesNotMatch(background.elements.toast.textContent,/Briefing ready/);
  background.run('listening=false;state="idle"');await background.run('jobs.poll()');
  assert.match(background.elements.toast.textContent,/Briefing ready/);
  assert.equal(background.elements.log.children.length,lines,'Background results must not enter conversation history');
  assert.equal(background.playCalls,plays,'Completion must not speak');
  await background.run('send("show jobs")');await background.flush();
  assert.equal(background.elements.panelTitle.textContent,'Jobs');
  assert.equal(background.requests.filter(item=>item.url==='/api/jobs/read').length,0,'Opening the list must not fetch private result text');
  const privateResult='<script>bad()</script> Private source excerpts.';
  background.responses['/api/jobs/read']={...backgroundJob,result:{reply:privateResult}};
  await background.run('jobAction("read","test-briefing")');
  assert.equal(background.elements.panelTitle.textContent,'Briefing result');
  assert.equal(background.elements.panelBody.children.at(-1).textContent,privateResult);
  assert.equal(background.elements.panelBody.children.at(-1).innerHTML,undefined);
  assert.equal(background.elements.log.children.length,lines);
  assert.equal(background.playCalls,plays);
  let finishRead;await background.run('showJobs()');await background.flush();
  background.responses['/api/jobs/read']=()=>new Promise(done=>finishRead=done);
  const reading=background.run('jobAction("read","test-briefing")');await background.flush();
  await background.run('jobAction("read","test-briefing")');
  assert.equal(background.requests.filter(item=>item.url==='/api/jobs/read').length,2,'A double click must not start another result request');
  background.elements.panel.close();finishRead({result:{reply:privateResult}});await reading;
  assert.equal(background.elements.panel.open,false,'A late result must not reopen a closed panel');
  background.run('pendingId="approval-test"');background.elements.jobsBtn.onclick();
  assert.equal(background.elements.panel.open,false,'Jobs must not replace an approval');
  assert.equal(background.run('pendingId'),'approval-test');
  background.run('pendingId=null');
  backgroundJob={...backgroundJob,status:'interrupted',stage:'interrupted',can_resume:true,result_available:false};
  background.responses['/api/jobs/resume']=body=>{assert.equal(body.id,'test-briefing');backgroundJob={...backgroundJob,status:'queued',stage:'queued',attempts:2,can_cancel:true,can_resume:false};return backgroundJob;};
  await background.run('jobAction("resume","test-briefing")');await background.flush();
  assert.equal(background.run('jobs.jobs[0].status'),'queued');
  background.responses['/api/jobs/cancel']=body=>{assert.equal(body.id,'test-briefing');backgroundJob={...backgroundJob,status:'cancelling',stage:'cancelling',can_cancel:false};return backgroundJob;};
  await background.run('jobAction("cancel","test-briefing")');await background.flush();
  assert.equal(background.run('jobs.jobs[0].status'),'cancelling');
  background.responses['/api/jobs/delete']={...backgroundJob,status:'deleted'};
  background.responses['/api/jobs']={jobs:[]};await background.run('jobAction("delete","test-briefing")');await background.flush();
  assert.equal(background.run('jobs.jobs.length'),0);assert.equal(background.elements.jobsHint.textContent,'');
  background.window.emit('pagehide');await background.flush();
  assert.equal(background.run('jobs.stopped'),true);assert.equal(background.timeouts.size,0);
  const missingJobs=app();await missingJobs.flush();missingJobs.elements.jobsBtn.onclick();
  assert.match(missingJobs.elements.toast.textContent,/Restart IRIS/);
  console.log('Desktop routing, standby, speech, approvals, background jobs, explicit private-result viewing and cleanup passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
