'use strict';
const $=id=>document.getElementById(id);
const voice=$('voice'),reactor=$('reactor'),logEl=$('log'),typeBox=$('typeBox');
let busy=false,muted=false,micPaused=false,listening=false,activated=false,activating=false;
let speechToken=0,audioCtx=null,analyser=null,speechDone=null,monitor=null;
let toastTimer=null,pendingId=null,latestCouncil=null,status=null,state='idle';
let recordingApprovalId=null;
let conversationVersion=0,followUpTimer=null,followUpListening=false;
let activationVersion=0,disposed=false,approvalTimer=null;
let latestActivity=null;
let jobPanelView=null,panelVersion=0;
const pendingJobs=new Set();
let experiencePanelView=false,experienceItems=[],experienceLoad=null,experienceError='';
const pendingExperiences=new Set();
const detector=new DoubleClapDetector();
const recordedInput=typeof MediaRecorder!=='undefined'&&navigator.mediaDevices?new RecordedVoiceInput({
  onState:value=>{listening=value!=='idle';setState(value);},
  onBackend:speech=>{if(status)status.speech=speech;renderSpeechStatus();if(speech.fallback)toast(speech.fallback);},
  onText:text=>{const approvalId=recordingApprovalId;recordingApprovalId=null;return send(text,{spoken:true,approvalId});},
  onSilence:()=>{followUpListening=false;recordingApprovalId=null;setState('idle');},
  onError:message=>{cancelFollowUp();toast(message);addLine('IRIS',message);}
}):null;
async function api(path,data,signal){
  const options=data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-IRIS-Request':'1'},body:JSON.stringify(data)};
  const controller=path==='/api/clap'||path==='/api/jobs'?new AbortController():null;
  const timeout=controller?setTimeout(()=>controller.abort(),path==='/api/jobs'?5000:2000):null;
  const abort=()=>controller?.abort();
  if(signal?.aborted)abort();else signal?.addEventListener('abort',abort,{once:true});
  if(controller){options.signal=controller.signal;options.keepalive=data?.action==='stop';}
  try{
    const response=await fetch(path,options);
    const result=await response.json();if(!response.ok)throw new Error(result.error||'IRIS could not complete the request.');return result;
  }catch(error){if(controller?.signal.aborted)throw new Error(path==='/api/jobs'?'The jobs connection timed out.':'The local microphone connection timed out. Tap the core to retry.');throw error;}
  finally{if(timeout!==null)clearTimeout(timeout);signal?.removeEventListener('abort',abort);}
}
const widgets=new DashboardWidgets({api});widgets.start();
const organization=typeof OrganizationFeed==='undefined'?null:new OrganizationFeed({api,
  isBusy:()=>busy||listening||Boolean(pendingId)||state==='speaking'||state==='preparing',
  onSnapshot:data=>{latestActivity=data;const info=data.status||{};
    $('organizationHint').textContent=info.error||(info.processing||info.queued?'Organizing your conversation…':info.enabled?'Automatic organization on · '+info.notes_location:'Automatic organization paused');
  },
  onActivity:item=>{if(item.kind!=='clarification'){const summary=item.title+': '+item.detail;toast(summary);addLine('SAVED',summary);}},
  onReminder:async item=>{if(disposed)return;cancelFollowUp(true);toast(item.message);addLine(item.clarification?'IRIS':'REMINDER',item.message);await speak(item.message);}
});
const jobs=typeof JobsFeed==='undefined'?null:new JobsFeed({api,
  isBusy:()=>busy||listening||Boolean(pendingId)||state==='speaking'||state==='preparing',
  onSnapshot:items=>{
    const active=items.filter(item=>['queued','running','cancelling'].includes(item.status));
    const attention=items.filter(item=>['interrupted','failed'].includes(item.status));
    const ready=items.filter(item=>item.result_available);
    $('jobsBtn').textContent='Jobs'+(active.length?' · '+active.length:attention.length?' · !':'');
    $('jobsHint').textContent=active.length?(active.length===1?jobStage(active[0]):active.length+' jobs in progress'):attention.length?attention.length+' job'+(attention.length===1?' needs':'s need')+' attention':ready.length?ready.length+' briefing'+(ready.length===1?'':'s')+' ready in Jobs':'';
    renderJobPanel();
  },
  onNotice:item=>toast({completed:'Briefing ready. Open Jobs to view it.',partial:'Briefing ready with limited coverage. Open Jobs to view it.',no_matches:'No matching notes for your briefing. See Jobs for details.',failed:'The briefing could not finish. Open Jobs for details.',interrupted:'The briefing was interrupted. Open Jobs to resume it.',cancelled:'Briefing cancelled.'}[item.status]||'Jobs updated.'),
  onUnavailable:()=>{$('jobsHint').textContent='Jobs connection unavailable · retrying';}
});
function toast(text){$('toast').textContent=text;$('toast').style.display='block';clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').style.display='none',9000);}
function setState(value){
  state=value;document.body.className='state-'+value;
  const ready=monitor?.active;
  const idle=micPaused?'Microphone paused':ready?'Standing by':monitor?.active?'Audio paused':'Ready when you are';
  $('status').textContent={idle,listening:followUpListening?'Anything else?':'Listening',thinking:'Thinking',speaking:'Speaking',preparing:'Preparing voice',Transcribing:'Understanding'}[value]||value;
  $('wakeHint').textContent=micPaused||monitor?.active&&!ready?'Tap the core to resume standby.':pendingId?'Double clap, then approve or cancel.':ready?(muted?'Double clap to wake · replies muted':'Double clap to wake · or hold Space'):'One click to enable your microphone.';
  if(value==='listening')$('wakeHint').textContent=followUpListening?'Speak to continue · silence returns to standby':'Speak naturally · pause to send · Escape to cancel';
}
function cancelFollowUp(cancelRecording=false){
  conversationVersion++;clearTimeout(followUpTimer);followUpTimer=null;
  const wasFollowUp=followUpListening;followUpListening=false;
  if(cancelRecording&&wasFollowUp)recordedInput?.cancel();
  return conversationVersion;
}
function scheduleFollowUp(version,context){
  if(!context.spoken||context.approvalId||version!==conversationVersion||disposed||micPaused||muted||!activated||!monitor?.active||busy||listening||pendingId||state!=='idle')return;
  // Leave a short gap for speaker echo to fade. Only a completed spoken turn
  // opens this bounded window; reminders, typed replies and approvals do not.
  followUpTimer=setTimeout(()=>{
    followUpTimer=null;
    if(version===conversationVersion&&!disposed&&!micPaused&&!muted&&!busy&&!listening&&!pendingId&&monitor?.active&&state==='idle')startListening(true,true);
  },600);
}
function standbyStatus(active,error){
  $('standbyDot').className='signal-dot '+(active?'on':'off');
  $('standbyLabel').textContent=active?'STANDBY ENABLED':micPaused?'MICROPHONE PAUSED':'MICROPHONE INACTIVE';
  if(error)toast(error);setState(state);
}
function addLine(who,text){
  $('emptyLog')?.remove();const line=document.createElement('div');line.className='line '+(who==='YOU'?'you':'jarvis');
  const label=document.createElement('span');label.className='who';label.textContent=who;
  const content=document.createElement('span');content.className='txt';content.textContent=text;
  line.append(label,content);logEl.append(line);logEl.scrollTop=logEl.scrollHeight;return content;
}
function addSources(answer,sources){
  const list=document.createElement('span');list.className='web-sources';
  for(const source of (sources||[]).slice(0,5)){
    try{const url=new URL(source.url);if(!['http:','https:'].includes(url.protocol)||url.username||url.password)continue;
      const link=document.createElement('a');link.href=url.href;link.target='_blank';link.rel='noopener noreferrer';link.textContent=source.title||url.hostname;list.append(link);
    }catch{}
  }
  if(list.children.length)answer.append(list);
}
async function loadStatus(){try{status=await api('/api/status');if(disposed)return;renderSpeechStatus();organization?.start();jobs?.start();await restoreStandby();}catch(error){if(!disposed)toast(error.message);}}
function saveStandby(value){try{globalThis.localStorage?.setItem('iris.standby',value);}catch{}}
async function restoreStandby(){
  if(!status?.desktop_window||!window.chrome?.webview||!recordedInput||disposed||activated||activating)return;
  const version=activationVersion;
  try{
    if(globalThis.localStorage?.getItem('iris.standby')==='paused'){pauseMic();return;}
    const permission=await navigator.permissions?.query({name:'microphone'});
    if(permission?.state==='granted'&&version===activationVersion&&!disposed&&!micPaused&&!activated&&!activating)await activate();
  }catch{} // Unsupported permission queries retain the visible Start standby button.
}
function renderSpeechStatus(){
  const speech=status?.speech||{};let label='Fish voice · local fallback';
  if(speech.configured_provider==='local')label='Local voice recognition';
  if(speech.engine==='fish')label='Voice connected · Fish Audio';
  else if(speech.engine==='faster-whisper')label='Local voice · '+(speech.device==='cuda'?'NVIDIA GPU':'CPU')+(speech.fallback?' fallback':'');
  $('details').textContent=label;$('details').title=speech.fallback||'Recognition uses Fish Audio, with local Whisper when needed.';
}
function updateClock(){const now=new Date();$('clock').textContent=now.toLocaleTimeString([],{hour:'2-digit',minute:'2-digit',hourCycle:'h23'});$('clockSeconds').textContent=String(now.getSeconds()).padStart(2,'0');$('clockDate').textContent=now.toLocaleDateString([],{weekday:'long',month:'short',day:'numeric'});}
loadStatus();updateClock();const clockTimer=setInterval(updateClock,1000);
function initAudio(){
  if(audioCtx)return;audioCtx=new(window.AudioContext||window.webkitAudioContext)();
  audioCtx.onstatechange=()=>{if(!disposed)standbyStatus(Boolean(monitor?.active));};
  const source=audioCtx.createMediaElementSource(voice);analyser=audioCtx.createAnalyser();analyser.fftSize=512;
  source.connect(analyser);analyser.connect(audioCtx.destination);const samples=new Uint8Array(analyser.fftSize);
  function meter(){let level=0;if(!voice.paused){analyser.getByteTimeDomainData(samples);level=Math.min(1,Math.sqrt(samples.reduce((s,v)=>s+((v-128)/128)**2,0)/samples.length)*4);}reactor.style.setProperty('--level',level.toFixed(3));requestAnimationFrame(meter);}requestAnimationFrame(meter);
  monitor=new NativeStandbyMonitor({api,onTrigger:()=>startListening(true),onStatus:standbyStatus,
    isBusy:()=>micPaused||listening||(busy&&!pendingId)||state==='speaking'||state==='preparing'});
}
async function activate(){
  if(activating||disposed)return;const version=++activationVersion;activating=true;micPaused=false;$('wake').disabled=true;
  try{initAudio();if(audioCtx.state==='suspended')await audioCtx.resume();
    if(version!==activationVersion||disposed||micPaused)return;
    // Grant the request recorder permission before local Python standby starts.
    // Stop this temporary stream immediately; only the native listener stays open.
    if(!recordedInput)throw new Error('Microphone recording is unavailable. Update IRIS with setup.bat or use Google Chrome.');
    if(!monitor.active){const stream=await navigator.mediaDevices.getUserMedia({audio:true});stream.getTracks().forEach(track=>track.stop());}
    if(version!==activationVersion||disposed||micPaused)return;
    const started=await monitor.start();if(version!==activationVersion||disposed||micPaused)return;
    if(started){activated=true;saveStandby('enabled');$('wake').hidden=true;$('muteBtn').textContent='Pause mic';$('muteBtn').setAttribute('aria-pressed','false');setState('idle');}
  }catch(error){if(version===activationVersion&&!disposed)toast('Could not start audio: '+error.message);}
  finally{if(version===activationVersion){activating=false;$('wake').disabled=false;}}
}
function stopSpeaking(){
  speechToken++;
  // Audio support can disappear after a device change or be only partially
  // exposed by the desktop renderer. Each cleanup must leave text chat usable.
  for(const stop of [()=>speechDone?.(),()=>voice.pause(),()=>voice.removeAttribute('src'),()=>voice.load(),()=>window.speechSynthesis?.cancel?.()]){
    try{stop();}catch(error){console.warn('IRIS audio cleanup unavailable:',error.name);}
  }
}
async function speak(text){
  stopSpeaking();
  if(disposed)return;if(muted||!activated){setState('idle');return;}const token=++speechToken;setState('preparing');
  let fallbackText=null;
  try{const ticket=await api('/api/voice',{text});if(token!==speechToken||muted)return;
    fallbackText=typeof ticket.fallback_text==='string'?ticket.fallback_text:null;
    if(fallbackText!==null&&!fallbackText.trim())return;
    initAudio();if(audioCtx.state==='suspended')await audioCtx.resume();
    if(token!==speechToken||muted||disposed)return;
    await new Promise((resolve,reject)=>{let complete;const clean=()=>{if(speechDone!==complete)return;voice.onended=null;voice.onerror=null;voice.onplaying=null;speechDone=null;};
      complete=()=>{clean();resolve();};speechDone=complete;voice.onended=complete;voice.onerror=()=>{clean();reject(new Error('Fish Audio is unavailable; trying the device voice.'));};
      voice.onplaying=()=>{if(token===speechToken)setState('speaking');};voice.src=ticket.url;voice.play().catch(error=>{clean();reject(error);});});
  }catch(error){if(token!==speechToken||muted)return;toast(error.message);
    if(fallbackText!==null&&typeof window.speechSynthesis?.speak==='function'&&typeof window.SpeechSynthesisUtterance==='function')await new Promise(resolve=>{const utterance=new window.SpeechSynthesisUtterance(fallbackText);setState('speaking');speechDone=resolve;utterance.onend=resolve;utterance.onerror=resolve;window.speechSynthesis.speak(utterance);});
  }finally{if(token===speechToken){speechDone=null;setState('idle');detector.reset();}}
}
async function reply(text){if(disposed)return;addLine('IRIS',text);await speak(text);}
async function voiceCommand(text,context={}){
  const simple=text.toLowerCase().trim().replace(/[.!?]+$/,'');
  let command=parseVoiceCommand(text);if(pendingId&&simple==='cancel')command='decline';
  if(command){
    if(command==='approve'||command==='decline'){
      if(context.spoken&&(!context.approvalId||context.approvalId!==pendingId)){await reply('That confirmation no longer matches the action on screen. Double clap and confirm the current action again.');return true;}
      if(pendingId)await answerApproval(command==='approve');else await reply('There is no action waiting for approval.');return true;
    }
    if(command==='mute'){muted=true;stopSpeaking();setState('idle');toast('Replies muted. Double clap and say unmute to restore speech.');return true;}
    if(command==='unmute'){muted=false;await reply('Voice replies are on.');return true;}
    if(command==='close'){if($('panel').open)$('panel').close();return true;}
    if(command==='pausemic'){pauseMic();return true;}
    if(command==='standby'){cancelFollowUp(true);stopSpeaking();setState(busy?'thinking':'idle');toast('Standing by. Double clap when you need me.');return true;}
    if(busy){toast(pendingId?'I’m waiting for your approval.':'IRIS is finishing your request.');return true;}
    if(command==='time'){await reply('It’s '+new Date().toLocaleTimeString([],{hour:'numeric',minute:'2-digit'})+'.');return true;}
    if(command==='weather'){
      const data=await widgets.locate();
      let report=widgets.weatherMessage||'Weather is unavailable right now. Try again shortly.';
      if(Number.isFinite(data?.temperature_c)){
        report=`${data.stale?'The cached weather report says':'Near you, it’s'} ${Math.round(data.temperature_c)} degrees Celsius`;
        if(data.condition)report+=`, ${data.condition.toLowerCase()}`;report+='.';
        if(Number.isFinite(data.feels_like_c))report+=` Feels like ${Math.round(data.feels_like_c)} degrees.`;
      }
      await reply(report);return true;
    }
    if(command==='markets'){
      const data=await widgets.loadMarkets();const rows=(data?.items||[]).filter(row=>Number.isFinite(row.value));
      await reply(rows.length?(data.stale?'These are cached daily closes, not live prices. ':'These are the latest available daily closes, not live prices. ')+rows.map(row=>{
        const change=Number.isFinite(row.change_percent)?`, ${row.change_percent>=0?'up':'down'} ${Math.abs(row.change_percent).toFixed(2)} percent`:'';
        return `${row.symbol}: ${row.value.toFixed(2)} dollars${change}${row.as_of?', as of '+row.as_of:''}.`;
      }).join(' '):'Market prices are unavailable right now.');return true;
    }
    if(command==='newchat')await resetChat();
    if(command==='memories')await showMemories();if(command==='tasks')await showTasks();
    if(command==='goals')await showGoals();if(command==='notes')await showNotes();
    if(command==='jobs')showJobs();if(command==='experiences')await showExperiences();
    if(command==='activity')await showActivity();if(command==='undo')await undoLastAutomatic();
    if(command==='council')showCouncil();if(command==='help')showHelp();return true;
  }
  return false;
}
async function send(text,context={}){
  text=text.trim();if(!text||disposed)return;
  const turn=cancelFollowUp();
  let answer=null,ownsRequest=false,spokenReply=null;
  try{
    if(recordedInput?.active)recordedInput.cancel();
    if(await voiceCommand(text,context)){context.onAccepted?.();scheduleFollowUp(turn,context);return;}
    if(busy){toast('IRIS is finishing your request.');return;}
    stopSpeaking();busy=true;ownsRequest=true;$('typeForm').querySelector('button').disabled=true;
    addLine('YOU',text);answer=addLine('IRIS','…');context.onAccepted?.();setState('thinking');
    const data=await api('/api/chat',{text,mode:'auto'});answer.textContent=data.reply;logEl.scrollTop=logEl.scrollHeight;
    if(data.job)jobs?.record(data.job);
    addSources(answer,data.sources);
    latestCouncil=data.council||null;$('routeLabel').textContent=data.route==='LOCAL'?'LOCAL ACTION':data.route==='WEB'?'WEB SEARCH':data.route==='COUNCIL'?'COUNCIL CONSULTED':data.route==='DEEP'?'DEEP REASONING':'AUTOMATIC REASONING';
    spokenReply=typeof data.spoken_reply==='string'&&data.spoken_reply.trim()?data.spoken_reply:data.reply;
  }catch(error){
    const message=error.message||'IRIS could not send your message. Please try again.';
    if(answer)answer.textContent=message;else addLine('IRIS',message);
    toast(message);if(ownsRequest||!busy)setState('idle');
  }finally{if(ownsRequest){busy=false;$('typeForm').querySelector('button').disabled=false;}}
  if(spokenReply!==null&&!disposed){try{await speak(spokenReply);}catch{toast('Your reply is ready, but audio playback is unavailable.');setState('idle');}}
  if(spokenReply!==null)scheduleFollowUp(turn,context);
}
function startListening(timed=false,followUp=false){
  if(disposed||(busy&&!pendingId)||listening||micPaused)return;
  if(!recordedInput){toast('This interface cannot record microphone audio. Update IRIS with setup.bat or try Google Chrome.');return;}
  cancelFollowUp();followUpListening=followUp;
  recordingApprovalId=pendingId;stopSpeaking();recordedInput.start(30000,monitor?.device||null,{autoStop:timed,initialSilenceMs:followUp?5000:6000});
}
function stopListening(){if(recordedInput?.active)recordedInput.stop();}
function pauseMic(){cancelFollowUp();activationVersion++;activating=false;$('wake').disabled=false;micPaused=true;saveStandby('paused');recordedInput?.cancel();monitor?.stop();stopSpeaking();$('muteBtn').textContent='Resume mic';$('muteBtn').setAttribute('aria-pressed','true');setState(busy?'thinking':'idle');}
function editable(target){return target!==reactor&&(target.closest('input,textarea,select,button,dialog')||target.isContentEditable);}
document.addEventListener('keydown',event=>{if(event.code==='Space'&&!event.repeat&&!editable(event.target)&&activated){event.preventDefault();startListening();}if(event.code==='Escape'){cancelFollowUp();stopSpeaking();recordedInput?.cancel();setState(busy?'thinking':'idle');}});
document.addEventListener('keyup',event=>{if(event.code==='Space'&&!editable(event.target)){event.preventDefault();stopListening();}});
function coreAction(){if(!activated||micPaused||!monitor?.active||audioCtx?.state!=='running')activate();else if(listening)stopListening();else startListening(true);}
reactor.addEventListener('click',coreAction);reactor.addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();coreAction();}});
let typedSubmission=null;
$('typeForm').addEventListener('submit',async event=>{
  event.preventDefault();if(typedSubmission)return;
  const text=typeBox.value,submission={};typedSubmission=submission;
  try{await send(text,{onAccepted:()=>{
    // Clear only an accepted draft, without deleting anything typed since Send.
    if(typeBox.value===text)typeBox.value='';
    if(typedSubmission===submission)typedSubmission=null;
  }});}catch{toast('IRIS could not send your message. Your draft is still here.');}
  finally{if(typedSubmission===submission)typedSubmission=null;}
});
$('wake').onclick=activate;$('muteBtn').onclick=()=>micPaused?activate():pauseMic();
window.addEventListener('pagehide',()=>{disposed=true;cancelFollowUp();activationVersion++;activating=false;monitor?.stop();stopSpeaking();recordedInput?.cancel();widgets.stop();organization?.stop();jobs?.stop();clearInterval(clockTimer);clearTimeout(approvalTimer);clearTimeout(toastTimer);});
function panel(title){panelVersion++;jobPanelView=title==='Jobs'?'list':null;experiencePanelView=title==='Task memory';$('panelTitle').textContent=title;$('panelBody').replaceChildren();if(!$('panel').open)$('panel').showModal();return $('panelBody');}
function paragraph(parent,text){const p=document.createElement('p');p.textContent=text;parent.append(p);return p;}
$('closePanel').onclick=()=>$('panel').close();
function renderJobPanel(){if(jobs&&jobPanelView==='list'&&$('panel').open){
  const body=$('panelBody');renderJobs(body,jobs.jobs,{document,onAction:jobAction,pending:pendingJobs});
  const memory=document.createElement('button');memory.textContent='Task memory';memory.onclick=showExperiences;body.append(memory);
}}
function showJobs(){
  if(!jobs){toast('Jobs controls are unavailable. Restart IRIS to load them.');return;}
  if(pendingId){toast('Finish the confirmation first.');return;}
  panel('Jobs');renderJobPanel();jobs.refresh();
}
async function jobAction(action,id){
  if(disposed||pendingJobs.has(id)||pendingId||!['read','cancel','resume','delete'].includes(action))return;
  const version=panelVersion;pendingJobs.add(id);renderJobPanel();
  try{
    const data=await api('/api/jobs/'+action,{id});if(disposed)return;
    if(action==='read'){
      if(pendingId||!$('panel').open||jobPanelView!=='list'||version!==panelVersion)return;
      if(!data.result||typeof data.result.reply!=='string')throw new Error('This result is not available yet.');
      const body=panel('Briefing result'),back=document.createElement('button');
      back.textContent='Back to jobs';back.onclick=showJobs;body.append(back);
      const result=document.createElement('pre');result.className='note-content';result.textContent=data.result.reply;body.append(result);
    }else if(action==='delete'){
      jobs.forget(id);
    }else jobs.record(data);
  }catch(error){if(!disposed)toast(error.message||'The job could not be updated.');}
  finally{pendingJobs.delete(id);if(!disposed)renderJobPanel();}
}
$('jobsBtn').onclick=showJobs;
function currentExperiencePanel(version=panelVersion){return !disposed&&!pendingId&&experiencePanelView&&$('panel').open&&version===panelVersion;}
function renderExperiencePanel(){
  if(!currentExperiencePanel())return;
  const body=$('panelBody');body.replaceChildren();
  const controls=document.createElement('div');controls.className='experience-navigation';
  const back=document.createElement('button');back.textContent='Back to jobs';back.onclick=showJobs;controls.append(back);
  const refresh=document.createElement('button');refresh.textContent='Refresh';refresh.disabled=Boolean(experienceLoad?.version===panelVersion)||pendingExperiences.size>0;refresh.onclick=showExperiences;controls.append(refresh);body.append(controls);
  if(experienceLoad?.version===panelVersion){paragraph(body,'Loading task memory…');return;}
  if(experienceError){paragraph(body,experienceError);return;}
  const list=document.createElement('div');body.append(list);renderExperiences(list,experienceItems,{document,onAction:experienceAction,pending:pendingExperiences});
}
async function showExperiences(){
  if(disposed)return;
  if(pendingId){toast('Finish the confirmation first.');return;}
  if(typeof renderExperiences==='undefined'){toast('Task memory controls are unavailable. Restart IRIS to load them.');return;}
  if(currentExperiencePanel()&&experienceLoad?.version===panelVersion)return;
  panel('Task memory');experienceItems=[];experienceError='';
  const request={version:panelVersion};experienceLoad=request;renderExperiencePanel();
  try{
    const data=await api('/api/experiences');
    if(!currentExperiencePanel(request.version))return;
    if(!Array.isArray(data?.items))throw new Error('Invalid task memory response');
    const unique=new Map();for(const raw of data.items.slice(0,100)){const item=experienceSnapshot(raw);if(item)unique.set(item.id,item);}
    experienceItems=[...unique.values()];
  }catch{if(currentExperiencePanel(request.version))experienceError='Task memory could not be loaded. Use Refresh to try again.';}
  finally{if(experienceLoad===request)experienceLoad=null;if(currentExperiencePanel(request.version))renderExperiencePanel();}
}
async function experienceAction(action,id,revision){
  if(!currentExperiencePanel()||pendingExperiences.has(id)||!['keep','dismiss','dispute','forget'].includes(action))return;
  if(!experienceItems.some(item=>item.id===id&&item.revision===revision))return;
  const version=panelVersion;pendingExperiences.add(id);renderExperiencePanel();
  try{
    const data=await api('/api/experiences/'+(action==='forget'?'forget':'review'),{id,revision,...(action==='forget'?{}:{decision:action})});
    if(!currentExperiencePanel(version))return;
    if(action==='forget'){
      if(data?.ok!==true)throw new Error('Invalid task memory response');
      experienceItems=experienceItems.filter(item=>item.id!==id);
    }else{
      const item=experienceSnapshot(data);
      if(!item||item.id!==id||item.revision<=revision)throw new Error('Invalid task memory response');
      experienceItems=experienceItems.map(previous=>previous.id===id?item:previous);
    }
  }catch{if(currentExperiencePanel(version))experienceError='That change could not be confirmed. Use Refresh to check the latest task memory before trying again.';}
  finally{pendingExperiences.delete(id);if(currentExperiencePanel())renderExperiencePanel();}
}
async function showMemories(){try{const data=await api('/api/memories'),body=panel('Memories');if(!data.items.length)paragraph(body,'No saved memories yet. Say “remember that…” to add one.');for(const item of data.items)paragraph(body,item.summary);await speak(data.items.length?'Your saved memories. '+data.items.slice(0,5).map(item=>item.summary).join('. '):'No saved memories yet.');}catch(error){toast(error.message);}}
async function showTasks(){try{const data=await api('/api/tasks'),body=panel('Tasks');if(!data.items.length)paragraph(body,'No tasks yet. With automatic organization on, tell me what you need to get done.');for(const task of data.items)paragraph(body,task.title+' · '+task.status+(task.due_at?' · '+new Date(task.due_at).toLocaleString():''));await speak(data.items.length?'Your tasks. '+data.items.slice(0,5).map(task=>task.title+', '+task.status).join('. '):'No tasks yet.');}catch(error){toast(error.message);}}
async function showGoals(){try{const data=await api('/api/goals'),body=panel('Goals');if(!data.items.length)paragraph(body,'Tell me what you are working towards. Clear long-term goals can be saved automatically.');for(const goal of data.items)paragraph(body,goal.title+' · '+goal.status+' · '+goal.progress+'%'+(goal.target_date?' · '+goal.target_date:''));}catch(error){toast(error.message);}}
async function showNotes(){try{const data=await api('/api/notes'),body=panel('Notes');if(!data.items.length)paragraph(body,'Useful notes from conversation will appear here.');for(const item of data.items){const button=document.createElement('button');button.className='note-link';button.textContent=item.title||item.path;button.onclick=async()=>{try{const note=await api('/api/notes/read',{path:item.path});const pre=document.createElement('pre');pre.className='note-content';pre.textContent=note.text;panel(note.path||item.title).append(pre);}catch(error){toast(error.message);}};body.append(button);}}catch(error){toast(error.message);}}
async function undoAutomatic(id){try{await api('/api/activity/undo',{id});toast('Automatic change undone.');await showActivity();}catch(error){toast(error.message);}}
async function undoLastAutomatic(){try{const data=await api('/api/activity');const item=data.activity.find(row=>row.undoable&&row.state==='applied');if(item)await undoAutomatic(item.id);else await reply('There is no automatic change available to undo.');}catch(error){toast(error.message);}}
async function showActivity(){try{const data=await api('/api/activity'),body=panel('Activity');latestActivity=data;
  paragraph(body,data.status.enabled?'IRIS picks up clear commitments, goals and useful notes as you talk.':'Automatic organization is paused.');
  const controls=document.createElement('div');controls.className='activity-controls';
  for(const [label,callback] of [['Tasks',showTasks],['Goals',showGoals],['Notes',showNotes]]){const button=document.createElement('button');button.textContent=label;button.onclick=callback;controls.append(button);}
  const toggle=document.createElement('button');toggle.textContent=data.status.enabled?'Pause organization and reminders':'Resume organization and reminders';toggle.onclick=async()=>{toggle.disabled=true;try{await api('/api/organization',{enabled:!data.status.enabled});await showActivity();}catch(error){toast(error.message);}finally{toggle.disabled=false;}};controls.append(toggle);body.append(controls);
  if(data.status.error)paragraph(body,data.status.error);
  const sms=data.status.reminders||{};if(data.status.sms_requested)paragraph(body,sms.sms_enabled?'SMS reminders are enabled for your own number.':'SMS reminders are waiting for Twilio setup and a desktop restart.');
  if(!data.activity.length)paragraph(body,'Automatic changes will appear here with an undo button.');
  for(const item of data.activity){const row=document.createElement('section');row.className='activity-item';paragraph(row,item.title);paragraph(row,item.detail);paragraph(row,new Date(item.created_at).toLocaleString()+' · '+item.state);
    if(item.undoable&&item.state==='applied'){const button=document.createElement('button');button.textContent='Undo';button.onclick=()=>undoAutomatic(item.id);row.append(button);}body.append(row);}
}catch(error){toast(error.message);}}
$('activityBtn').onclick=showActivity;
function showCouncil(){if(!latestCouncil){toast('There is no council review in this conversation yet.');return;}const body=panel('Council review');for(const candidate of latestCouncil.candidates)paragraph(body,candidate.seat+' · '+candidate.model+'\n'+candidate.text);for(const ranking of latestCouncil.rankings)paragraph(body,ranking.reviewer+' review\n'+ranking.text);if(latestCouncil.failures.length)paragraph(body,'Partial failures: '+latestCouncil.failures.join(', '));}
function showHelp(){const body=panel('Just ask IRIS');const list=document.createElement('div');list.className='command-list';body.append(list);
  for(const text of ['“Show my tasks”','“Show my goals”','“Show my notes”','“Show jobs”','“Show task memory”','“Show activity”','“Undo the last change”','“Pause automatic organization”','“Show my memories”','“Start a new chat”','“Weather update”','“Market update”','“What time is it?”','“Mute” / “Unmute”','“Show council review”','“Close the panel”','“Approve” / “Cancel”'])paragraph(list,text);
  paragraph(body,'Double clap to wake, then speak naturally. A pause sends your request. After a spoken reply, “Anything else?” opens five seconds to begin a follow-up without clapping again. Silence returns to standby without an upload. Say “That’s all” to finish, or hold Space for manual recording. Click the core or hold Space to interrupt a spoken reply.');
  paragraph(body,'IRIS chooses how deeply to reason from your request. You can also ask it to consult the council explicitly.');
  paragraph(body,'“Check Obsidian” checks vault access. “Search my notes for …”, “Read note …”, and “Read next page” display notes locally without a model request. Use the relative note path if titles are ambiguous. “Make a briefing from my notes on …” runs in the background, reads up to three matching notes and checks source excerpts without a model call. “Show jobs” opens progress, Cancel, Resume and results. Interrupted jobs stay paused after a restart; Resume reads current notes again. “Cancel briefing” stops the active briefing. “Plan a briefing from my notes on …” previews the steps.');
  paragraph(body,'Ask “What can you do?” for the current capability list, or “What have you done today?” for local action receipts. “Show action history” includes earlier retained records. Outcomes distinguish verified, partial and unverified results. “Clear action history” asks before erasing receipts. These commands use no model call.');
  paragraph(body,'Say “Start my workspace” to open Chrome, Obsidian and your workspace folder. “Open Calculator”, “Set volume to 40 percent”, “Mute my computer”, “Find files named report”, and “Give me my daily briefing” run locally without a model call. “Mute” by itself only silences IRIS. Search and briefing details stay on screen with a shorter spoken summary.');
  paragraph(body,'With automatic organization on, describe your plans naturally: “I need to submit the report tomorrow at 3 PM.” Tasks, goals and useful notes are saved in the background. Activity shows the result and Undo. Dates without a time use the end of that day; unclear deadlines need a follow-up. Keep IRIS open for desktop and configured SMS reminders.');
  paragraph(body,'Say “Search the web for…” to research a public question online and show source links. Search uses OpenRouter credit; ordinary conversation does not automatically browse. Source links open in Google Chrome from the desktop app.');
  paragraph(body,'The local microphone listener checks consecutive 40 ms sound levels for your double clap. Only a request you start is sent for transcription. Keep IRIS open and the laptop awake. Pause mic stops monitoring; tap the core to resume.');
  paragraph(body,'Fish Audio handles recognition with local Whisper fallback. “Mute” silences replies while keeping double-clap available. The first local fallback may take longer to load.');
  paragraph(body,'Weather uses your device location, rounded to about a kilometre before it reaches Open-Meteo. Markets show completed daily ETF closes from Yahoo Finance, not a live trading feed.');
  if(status?.speech?.fallback)paragraph(body,status.speech.fallback);
}
$('infoBtn').onclick=showHelp;
async function resetChat(){try{await api('/api/reset',{});stopSpeaking();logEl.replaceChildren();latestCouncil=null;$('routeLabel').textContent='AUTOMATIC REASONING';if($('panel').open)$('panel').close();await reply('New conversation. Your saved memories and tasks are still here.');}catch(error){toast(error.message);}}
async function pollApproval(){if(disposed)return;try{const data=await api('/api/approval');if(disposed)return;
  if(data.pending&&data.pending.id!==pendingId){cancelFollowUp(true);pendingId=data.pending.id;$('approvalText').textContent=data.pending.summary;if($('panel').open)$('panel').close();if(!$('approval').open)$('approval').showModal();speak('Please confirm. '+data.pending.summary+'. Double clap, then say approve or cancel.');}
  else if(!data.pending&&pendingId){pendingId=null;$('approval').close();}
}catch{}finally{if(!disposed)approvalTimer=setTimeout(pollApproval,600);}}
async function answerApproval(approved){if(!pendingId)return;const id=pendingId;pendingId=null;$('approval').close();recordedInput?.cancel();stopSpeaking();try{await api('/api/approval',{id,approved});setState(busy?'thinking':'idle');}catch(error){toast(error.message);}}
$('approveBtn').onclick=()=>answerApproval(true);$('declineBtn').onclick=()=>answerApproval(false);$('approval').addEventListener('cancel',event=>{event.preventDefault();answerApproval(false);});
pollApproval();
