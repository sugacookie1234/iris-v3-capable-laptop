'use strict';
const $ = id => document.getElementById(id);
const voice = $('voice'), reactor = $('reactor'), logEl = $('log'), typeBox = $('typeBox');
let busy = false, muted = false, listening = false, rec = null, speechToken = 0;
let audioCtx = null, analyser = null, audioSamples = null, speechDone = null;
let clapStream = null, clapTimer = null, clapSource = null, micAnalyser = null;
let captureTimer = null, toastTimer = null, pendingId = null, latestCouncil = null, status = null;
let state = 'idle', statusLoaded = false;
const detector = new DoubleClapDetector();
const recordedInput = typeof MediaRecorder!=='undefined' && navigator.mediaDevices ? new RecordedVoiceInput({
  onState:value=>{listening=value!=='idle';setState(value);},
  onText:text=>send(text),onError:message=>{toast(message);addLine('IRIS',message);}
}) : null;

async function api(path, data) {
  const response = await fetch(path, data === undefined ? {} : {
    method:'POST', headers:{'Content-Type':'application/json','X-IRIS-Request':'1'}, body:JSON.stringify(data)
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'IRIS could not complete the request.');
  return result;
}
function toast(text) {
  $('toast').textContent = text; $('toast').style.display = 'block';
  clearTimeout(toastTimer); toastTimer = setTimeout(() => $('toast').style.display = 'none', 9000);
}
function setState(value) {
  state = value; document.body.className = 'state-' + value;
  const labels = {idle:muted?'Audio muted · typing available':'Standing by',listening:'Listening',
    thinking:$('mode').value==='council'?'Council deliberating':'Thinking', speaking:'Speaking',preparing:'Preparing voice'};
  $('status').textContent = labels[value] || value;
}
function addLine(who, text) {
  const line=document.createElement('div'); line.className='line ' + (who==='YOU'?'you':'jarvis');
  const label=document.createElement('span'); label.className='who'; label.textContent=who;
  const content=document.createElement('span'); content.className='txt'; content.textContent=text;
  line.append(label,content); logEl.append(line); logEl.scrollTop=logEl.scrollHeight;
  return content;
}
async function loadStatus() {
  try {
    status=await api('/api/status'); statusLoaded=true;
    $('dotBrain').className='dot '+(status.brain?'on':'off');
    $('dotVoice').className='dot '+(status.voice?'on':'off');
    $('details').textContent='IRIS · '+status.model+' · voice input processed locally';
  } catch(err) { toast(err.message); }
}
loadStatus();
setInterval(() => { $('clock').textContent=new Date().toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}); },1000);

function initAudio() {
  if (audioCtx) return;
  audioCtx=new (window.AudioContext||window.webkitAudioContext)();
  const source=audioCtx.createMediaElementSource(voice);
  analyser=audioCtx.createAnalyser(); analyser.fftSize=512;
  audioSamples=new Uint8Array(analyser.fftSize); source.connect(analyser); analyser.connect(audioCtx.destination);
  function meter() {
    let level=0;
    if (!voice.paused) {
      analyser.getByteTimeDomainData(audioSamples);
      level=Math.min(1,Math.sqrt(audioSamples.reduce((s,v)=>s+((v-128)/128)**2,0)/audioSamples.length)*4);
    }
    reactor.style.setProperty('--level',level.toFixed(3)); requestAnimationFrame(meter);
  }
  requestAnimationFrame(meter);
}
function stopSpeaking() {
  speechToken++; if (speechDone) speechDone();
  voice.pause(); voice.removeAttribute('src'); voice.load();
  if ('speechSynthesis' in window) speechSynthesis.cancel();
}
async function speak(text) {
  if (muted) { setState('idle'); return; }
  const token=++speechToken; setState('preparing');
  try {
    const ticket=await api('/api/voice',{text});
    if (token!==speechToken || muted) return;
    initAudio(); if (audioCtx.state==='suspended') await audioCtx.resume();
    await new Promise((resolve,reject) => {
      const clean=()=>{voice.onended=null;voice.onerror=null;voice.onplaying=null;speechDone=null;};
      speechDone=()=>{clean();resolve();};
      voice.onended=speechDone;
      voice.onerror=()=>{clean();reject(new Error('Fish Audio is unavailable; using the browser voice.'));};
      voice.onplaying=()=>{if(token===speechToken)setState('speaking');};
      voice.src=ticket.url;
      voice.play().catch(err=>{clean();reject(err);});
    });
  } catch(err) {
    if(token!==speechToken || muted)return;
    toast(err.message);
    if ('speechSynthesis' in window) await new Promise(resolve=>{
      const utterance=new SpeechSynthesisUtterance(text); setState('speaking');
      speechDone=resolve;utterance.onend=resolve;utterance.onerror=resolve;speechSynthesis.speak(utterance);
    });
  } finally {
    if(token===speechToken){speechDone=null;setState('idle');detector.reset();}
  }
}
async function send(text) {
  text=text.trim(); if (!text || busy) return;
  if(recordedInput&&recordedInput.active)recordedInput.cancel();
  if(listening){rec.onend=null;rec.abort();listening=false;clearTimeout(captureTimer);}
  stopSpeaking();busy=true;$('typeForm').querySelector('button').disabled=true;
  addLine('YOU',text);const answer=addLine('IRIS','…');setState('thinking');
  try {
    const data=await api('/api/chat',{text,mode:$('mode').value});
    answer.textContent=data.reply;logEl.scrollTop=logEl.scrollHeight;
    latestCouncil=data.council||null;$('councilBtn').hidden=!latestCouncil;
    busy=false;$('typeForm').querySelector('button').disabled=false;
    await speak(data.reply);
  } catch(err) { answer.textContent=err.message;toast(err.message);setState('idle'); }
  finally {busy=false;$('typeForm').querySelector('button').disabled=false;}
}

function startListening(timed=false) {
  if(busy||listening||muted)return;
  if(!recordedInput){toast('This browser cannot record microphone audio. Open IRIS in Edge or Chrome.');return;}
  stopSpeaking();recordedInput.start(timed?8000:30000);
}
function stopListening(){if(recordedInput&&recordedInput.active){recordedInput.stop();return;}if(rec&&listening){try{rec.stop();}catch{}}}
function editable(target){return target!==reactor&&(target.closest('input,textarea,select,button,dialog')||target.isContentEditable);}
document.addEventListener('keydown',e=>{
  if(e.code==='Space'&&!e.repeat&&!editable(e.target)&&!$('wake')){e.preventDefault();startListening();}
  if(e.code==='Escape'){stopSpeaking();if(recordedInput)recordedInput.cancel();if(rec)rec.abort();setState(busy?'thinking':'idle');}
});
document.addEventListener('keyup',e=>{if(e.code==='Space'&&!editable(e.target)){e.preventDefault();stopListening();}});
reactor.addEventListener('click',()=>listening?stopListening():startListening(true));
reactor.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();listening?stopListening():startListening(true);}});
$('typeForm').addEventListener('submit',e=>{e.preventDefault();if(busy)return;const text=typeBox.value;typeBox.value='';send(text);});
$('wake').addEventListener('click',()=>{
  $('wake').remove();initAudio();
  const greeting='Iris here. What would you like to do?';addLine('IRIS',greeting);speak(greeting);
});

function stopClap() {
  clearInterval(clapTimer);clapTimer=null;
  if(clapSource)clapSource.disconnect();clapSource=null;
  if(clapStream)clapStream.getTracks().forEach(t=>t.stop());clapStream=null;
  $('clapBtn').textContent='Double clap: off';$('clapBtn').setAttribute('aria-pressed','false');detector.reset();
}
$('clapBtn').addEventListener('click',async()=>{
  if(clapStream){stopClap();return;}
  if(muted){toast('Unmute before enabling double clap.');return;}
  try {
    initAudio();await audioCtx.resume();
    clapStream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:false,autoGainControl:false}});
    if(muted){stopClap();return;}
    clapSource=audioCtx.createMediaStreamSource(clapStream);micAnalyser=audioCtx.createAnalyser();micAnalyser.fftSize=1024;clapSource.connect(micAnalyser);
    const samples=new Float32Array(micAnalyser.fftSize);detector.reset();
    clapTimer=setInterval(()=>{
      if(state!=='idle'||busy||muted||document.hidden){detector.reset();return;}
      micAnalyser.getFloatTimeDomainData(samples);
      const rms=Math.sqrt(samples.reduce((s,v)=>s+v*v,0)/samples.length);
      if(detector.feed(rms,performance.now()/1000))startListening(true);
    },20);
    $('clapBtn').textContent='Double clap: on';$('clapBtn').setAttribute('aria-pressed','true');
    toast('Clap monitoring is on in this tab. Two claps start an 8-second listening window. Mute stops microphone monitoring.');
  } catch(err){stopClap();toast('Could not enable clap detection: '+err.message);}
});
$('muteBtn').addEventListener('click',()=>{
  if(recordedInput)recordedInput.cancel();
  muted=!muted;stopSpeaking();stopClap();if(rec){rec.onend=null;rec.abort();}listening=false;clearTimeout(captureTimer);
  $('muteBtn').textContent=muted?'Unmute':'Mute';$('muteBtn').setAttribute('aria-pressed',String(muted));setState(busy?'thinking':'idle');
});
window.addEventListener('pagehide',()=>{stopClap();stopSpeaking();if(recordedInput)recordedInput.cancel();if(rec)rec.abort();});
window.addEventListener('blur',()=>{if(recordedInput&&recordedInput.active)return;if(listening)stopListening();});

function panel(title){$('panelTitle').textContent=title;$('panelBody').replaceChildren();$('panel').showModal();return $('panelBody');}
function paragraph(parent,text){const p=document.createElement('p');p.textContent=text;parent.append(p);return p;}
$('closePanel').onclick=()=>$('panel').close();
$('memoriesBtn').onclick=async()=>{
  try {
    const data=await api('/api/memories');const body=panel('Memories');
    paragraph(body,'Saved facts are retrieved when relevant. They are separate from the current chat.');
    const form=document.createElement('form'),input=document.createElement('input'),save=document.createElement('button');
    input.placeholder='A preference or fact to remember';input.required=true;save.textContent='Propose memory';form.append(input,save);body.append(form);
    form.onsubmit=e=>{e.preventDefault();if(busy){toast('Wait for the current response.');return;}$('panel').close();send('/remember '+input.value);};
    if(!data.items.length)paragraph(body,'No saved memories yet.');
    for(const item of data.items){const row=document.createElement('div');row.className='record';const label=document.createElement('span');label.textContent=item.summary;const btn=document.createElement('button');btn.textContent='Forget';btn.onclick=()=>{if(busy)return;$('panel').close();send('/forget '+item.id);};row.append(label,btn);body.append(row);}
  }catch(err){toast(err.message);}
};
$('tasksBtn').onclick=async()=>{
  try {
    const data=await api('/api/tasks'),body=panel('Tasks');
    paragraph(body,'Ask IRIS to add, complete, or remove a task. Changes are shown for approval.');
    if(!data.items.length)paragraph(body,'No tasks yet. Try “Add a task to test IRIS on my OMEN.”');
    for(const task of data.items){const row=document.createElement('div');row.className='record';const label=document.createElement('span');label.textContent=task.title+' · '+task.status+(task.due_at?' · '+new Date(task.due_at).toLocaleString():'');row.append(label);body.append(row);}
  }catch(err){toast(err.message);}
};
$('councilBtn').onclick=()=>{
  if(!latestCouncil)return;const body=panel('Council review');
  for(const candidate of latestCouncil.candidates)paragraph(body,candidate.seat+' · '+candidate.model+'\n'+candidate.text);
  for(const ranking of latestCouncil.rankings)paragraph(body,ranking.reviewer+' review\n'+ranking.text);
  if(latestCouncil.failures.length)paragraph(body,'Partial failures: '+latestCouncil.failures.join(', '));
};
$('infoBtn').onclick=()=>{
  const body=panel('Your IRIS setup');
  paragraph(body,'Target: HP OMEN 16 · Core 7 240H · 16 GB RAM · RTX 5060 · 1 TB SSD. The default uses cloud inference; no GPU model is installed.');
  paragraph(body,'Run setup.bat to change models, voice, keys, timezone, or Obsidian path. Windows keys are encrypted for this account and excluded from GitHub.');
  paragraph(body,'Council runs five requests and may take longer. It uses the models you configure; the initial seats can share one model.');
  paragraph(body,'Microphone recordings are transcribed locally with Vosk, then the transcript is sent to your configured chat provider. Audio recordings are not saved. Fish Audio receives reply text for spoken output.');
  paragraph(body,'Connected here: IRIS reasoning, council, memory, tasks, goals, and optional read-only Obsidian. External Google accounts and general desktop control are not connected.');
  if(statusLoaded)paragraph(body,'Model: '+status.model+'\nVoice: '+status.voice_id);
};
$('resetBtn').onclick=async()=>{if(recordedInput)recordedInput.cancel();try{await api('/api/reset',{});stopSpeaking();logEl.replaceChildren();latestCouncil=null;$('councilBtn').hidden=true;setState('idle');toast('Conversation cleared. Saved memories and tasks are retained.');}catch(err){toast(err.message);}};

async function pollApproval(){
  try {
    const data=await api('/api/approval');
    if(data.pending&&data.pending.id!==pendingId){
      pendingId=data.pending.id;$('approvalText').textContent=data.pending.summary;
      if($('panel').open)$('panel').close();if(!$('approval').open)$('approval').showModal();
    } else if(!data.pending&&pendingId){pendingId=null;$('approval').close();}
  }catch{}finally{setTimeout(pollApproval,600);}
}
async function answerApproval(approved){
  if(!pendingId)return;const id=pendingId;pendingId=null;$('approval').close();
  try{await api('/api/approval',{id,approved});}catch(err){toast(err.message);}
}
$('approveBtn').onclick=()=>answerApproval(true);$('declineBtn').onclick=()=>answerApproval(false);
$('approval').addEventListener('cancel',e=>{e.preventDefault();answerApproval(false);});
pollApproval();
