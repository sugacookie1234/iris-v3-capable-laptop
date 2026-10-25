'use strict';
const $=id=>document.getElementById(id);
const voice=$('voice'),reactor=$('reactor'),logEl=$('log'),typeBox=$('typeBox');
let busy=false,muted=false,micPaused=false,listening=false,activated=false,activating=false;
let speechToken=0,audioCtx=null,analyser=null,speechDone=null,monitor=null;
let toastTimer=null,pendingId=null,latestCouncil=null,status=null,state='idle';
let recordingApprovalId=null;
let activationVersion=0,disposed=false,approvalTimer=null;
const detector=new DoubleClapDetector();
const recordedInput=typeof MediaRecorder!=='undefined'&&navigator.mediaDevices?new RecordedVoiceInput({
  onState:value=>{listening=value!=='idle';setState(value);},
  onBackend:speech=>{if(status)status.speech=speech;renderSpeechStatus();if(speech.fallback)toast(speech.fallback);},
  onText:text=>{const approvalId=recordingApprovalId;recordingApprovalId=null;return send(text,{spoken:true,approvalId});},onError:message=>{toast(message);addLine('IRIS',message);}
}):null;
async function api(path,data){
  const response=await fetch(path,data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-IRIS-Request':'1'},body:JSON.stringify(data)});
  const result=await response.json();if(!response.ok)throw new Error(result.error||'IRIS could not complete the request.');return result;
}
const widgets=new DashboardWidgets({api});widgets.start();
function toast(text){$('toast').textContent=text;$('toast').style.display='block';clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').style.display='none',9000);}
function setState(value){
  state=value;document.body.className='state-'+value;
  const ready=monitor?.active&&audioCtx?.state==='running';
  const idle=micPaused?'Microphone paused':ready?'Standing by':monitor?.active?'Audio paused':'Ready when you are';
  $('status').textContent={idle,listening:'Listening',thinking:'Thinking',speaking:'Speaking',preparing:'Preparing voice',Transcribing:'Understanding'}[value]||value;
  $('wakeHint').textContent=micPaused||monitor?.active&&!ready?'Tap the core to resume standby.':pendingId?'Double clap, then approve or cancel.':ready?(muted?'Double clap to wake · replies muted':'Double clap to wake · or hold Space'):'One click to enable your microphone.';
}
function standbyStatus(active,error){
  active=active&&audioCtx?.state==='running';
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
async function loadStatus(){try{status=await api('/api/status');if(disposed)return;renderSpeechStatus();await restoreStandby();}catch(error){if(!disposed)toast(error.message);}}
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
  monitor=new StandbyMonitor({context:audioCtx,detector,onTrigger:()=>startListening(true),onStatus:standbyStatus,
    isBusy:()=>micPaused||listening||(busy&&!pendingId)||state==='speaking'||state==='preparing'});
}
async function activate(){
  if(activating||disposed)return;const version=++activationVersion;activating=true;micPaused=false;$('wake').disabled=true;
  try{initAudio();if(audioCtx.state==='suspended')await audioCtx.resume();
    if(version!==activationVersion||disposed||micPaused)return;
    const started=await monitor.start();if(version!==activationVersion||disposed||micPaused)return;
    if(started){activated=true;saveStandby('enabled');$('wake').hidden=true;$('muteBtn').textContent='Pause mic';$('muteBtn').setAttribute('aria-pressed','false');setState('idle');}
  }catch(error){if(version===activationVersion&&!disposed)toast('Could not start audio: '+error.message);}
  finally{if(version===activationVersion){activating=false;$('wake').disabled=false;}}
}
function stopSpeaking(){speechToken++;if(speechDone)speechDone();voice.pause();voice.removeAttribute('src');voice.load();if('speechSynthesis'in window)speechSynthesis.cancel();}
async function speak(text){
  stopSpeaking();
  if(disposed)return;if(muted||!activated){setState('idle');return;}const token=++speechToken;setState('preparing');
  try{const ticket=await api('/api/voice',{text});if(token!==speechToken||muted)return;
    initAudio();if(audioCtx.state==='suspended')await audioCtx.resume();
    if(token!==speechToken||muted||disposed)return;
    await new Promise((resolve,reject)=>{let complete;const clean=()=>{if(speechDone!==complete)return;voice.onended=null;voice.onerror=null;voice.onplaying=null;speechDone=null;};
      complete=()=>{clean();resolve();};speechDone=complete;voice.onended=complete;voice.onerror=()=>{clean();reject(new Error('Fish Audio is unavailable; trying the device voice.'));};
      voice.onplaying=()=>{if(token===speechToken)setState('speaking');};voice.src=ticket.url;voice.play().catch(error=>{clean();reject(error);});});
  }catch(error){if(token!==speechToken||muted)return;toast(error.message);
    if('speechSynthesis'in window)await new Promise(resolve=>{const utterance=new SpeechSynthesisUtterance(text);setState('speaking');speechDone=resolve;utterance.onend=resolve;utterance.onerror=resolve;speechSynthesis.speak(utterance);});
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
    if(command==='council')showCouncil();if(command==='help')showHelp();return true;
  }
  return false;
}
async function send(text,context={}){
  text=text.trim();if(!text||disposed)return;if(recordedInput?.active)recordedInput.cancel();
  if(await voiceCommand(text,context))return;if(busy){toast('IRIS is finishing your request.');return;}
  stopSpeaking();busy=true;$('typeForm').querySelector('button').disabled=true;addLine('YOU',text);const answer=addLine('IRIS','…');setState('thinking');
  let spokenReply=null;
  try{const data=await api('/api/chat',{text,mode:'auto'});answer.textContent=data.reply;logEl.scrollTop=logEl.scrollHeight;
    latestCouncil=data.council||null;$('routeLabel').textContent=data.route==='COUNCIL'?'COUNCIL CONSULTED':data.route==='DEEP'?'DEEP REASONING':'AUTOMATIC REASONING';
    spokenReply=data.reply;
  }catch(error){answer.textContent=error.message;toast(error.message);setState('idle');}
  finally{busy=false;$('typeForm').querySelector('button').disabled=false;}
  if(spokenReply!==null&&!disposed)await speak(spokenReply);
}
function startListening(timed=false){
  if(disposed||(busy&&!pendingId)||listening||micPaused)return;
  if(!recordedInput){toast('This interface cannot record microphone audio. Update IRIS with setup.bat or try Google Chrome.');return;}
  recordingApprovalId=pendingId;stopSpeaking();recordedInput.start(timed?8000:30000);
}
function stopListening(){if(recordedInput?.active)recordedInput.stop();}
function pauseMic(){activationVersion++;activating=false;$('wake').disabled=false;micPaused=true;saveStandby('paused');recordedInput?.cancel();monitor?.stop();stopSpeaking();$('muteBtn').textContent='Resume mic';$('muteBtn').setAttribute('aria-pressed','true');setState(busy?'thinking':'idle');}
function editable(target){return target!==reactor&&(target.closest('input,textarea,select,button,dialog')||target.isContentEditable);}
document.addEventListener('keydown',event=>{if(event.code==='Space'&&!event.repeat&&!editable(event.target)&&activated){event.preventDefault();startListening();}if(event.code==='Escape'){stopSpeaking();recordedInput?.cancel();setState(busy?'thinking':'idle');}});
document.addEventListener('keyup',event=>{if(event.code==='Space'&&!editable(event.target)){event.preventDefault();stopListening();}});
function coreAction(){if(!activated||micPaused||!monitor?.active||audioCtx?.state!=='running')activate();else if(listening)stopListening();else startListening(true);}
reactor.addEventListener('click',coreAction);reactor.addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();coreAction();}});
$('typeForm').addEventListener('submit',event=>{event.preventDefault();const text=typeBox.value;typeBox.value='';send(text);});
$('wake').onclick=activate;$('muteBtn').onclick=()=>micPaused?activate():pauseMic();
window.addEventListener('pagehide',()=>{disposed=true;activationVersion++;activating=false;monitor?.stop();stopSpeaking();recordedInput?.cancel();widgets.stop();clearInterval(clockTimer);clearTimeout(approvalTimer);});
function panel(title){$('panelTitle').textContent=title;$('panelBody').replaceChildren();if(!$('panel').open)$('panel').showModal();return $('panelBody');}
function paragraph(parent,text){const p=document.createElement('p');p.textContent=text;parent.append(p);return p;}
$('closePanel').onclick=()=>$('panel').close();
async function showMemories(){try{const data=await api('/api/memories'),body=panel('Memories');if(!data.items.length)paragraph(body,'No saved memories yet. Say “remember that…” to add one.');for(const item of data.items)paragraph(body,item.summary);await speak(data.items.length?'Your saved memories. '+data.items.slice(0,5).map(item=>item.summary).join('. '):'No saved memories yet.');}catch(error){toast(error.message);}}
async function showTasks(){try{const data=await api('/api/tasks'),body=panel('Tasks');if(!data.items.length)paragraph(body,'No tasks yet. Ask me to add one.');for(const task of data.items)paragraph(body,task.title+' · '+task.status);await speak(data.items.length?'Your tasks. '+data.items.slice(0,5).map(task=>task.title+', '+task.status).join('. '):'No tasks yet.');}catch(error){toast(error.message);}}
function showCouncil(){if(!latestCouncil){toast('There is no council review in this conversation yet.');return;}const body=panel('Council review');for(const candidate of latestCouncil.candidates)paragraph(body,candidate.seat+' · '+candidate.model+'\n'+candidate.text);for(const ranking of latestCouncil.rankings)paragraph(body,ranking.reviewer+' review\n'+ranking.text);if(latestCouncil.failures.length)paragraph(body,'Partial failures: '+latestCouncil.failures.join(', '));}
function showHelp(){const body=panel('Just ask IRIS');const list=document.createElement('div');list.className='command-list';body.append(list);
  for(const text of ['“Show my tasks”','“Show my memories”','“Start a new chat”','“Weather update”','“Market update”','“What time is it?”','“Mute” / “Unmute”','“Show council review”','“Close the panel”','“Approve” / “Cancel”'])paragraph(list,text);
  paragraph(body,'Double clap to wake, then speak. IRIS chooses how deeply to reason from your request. You can also ask it to consult the council explicitly.');
  paragraph(body,'Standby checks sound levels locally. Only a request you start is sent for transcription. Keep this page open and the laptop awake. Pause mic stops monitoring; tap the core to resume.');
  paragraph(body,'Fish Audio handles recognition with local Whisper fallback. “Mute” silences replies while keeping double-clap available. The first local fallback may take longer to load.');
  paragraph(body,'Weather uses your device location, rounded to about a kilometre before it reaches Open-Meteo. Markets show completed daily ETF closes from Yahoo Finance, not a live trading feed.');
  if(status?.speech?.fallback)paragraph(body,status.speech.fallback);
}
$('infoBtn').onclick=showHelp;
async function resetChat(){try{await api('/api/reset',{});stopSpeaking();logEl.replaceChildren();latestCouncil=null;$('routeLabel').textContent='AUTOMATIC REASONING';if($('panel').open)$('panel').close();await reply('New conversation. Your saved memories and tasks are still here.');}catch(error){toast(error.message);}}
async function pollApproval(){if(disposed)return;try{const data=await api('/api/approval');if(disposed)return;
  if(data.pending&&data.pending.id!==pendingId){pendingId=data.pending.id;$('approvalText').textContent=data.pending.summary;if($('panel').open)$('panel').close();if(!$('approval').open)$('approval').showModal();speak('Please confirm. '+data.pending.summary+'. Double clap, then say approve or cancel.');}
  else if(!data.pending&&pendingId){pendingId=null;$('approval').close();}
}catch{}finally{if(!disposed)approvalTimer=setTimeout(pollApproval,600);}}
async function answerApproval(approved){if(!pendingId)return;const id=pendingId;pendingId=null;$('approval').close();recordedInput?.cancel();stopSpeaking();try{await api('/api/approval',{id,approved});setState(busy?'thinking':'idle');}catch(error){toast(error.message);}}
$('approveBtn').onclick=()=>answerApproval(true);$('declineBtn').onclick=()=>answerApproval(false);$('approval').addEventListener('cancel',event=>{event.preventDefault();answerApproval(false);});
pollApproval();
