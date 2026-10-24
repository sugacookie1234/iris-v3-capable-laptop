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
function app({recording=true}={}){
  const elements={};
  for(const match of fs.readFileSync(path.join(__dirname,'../web/index.html'),'utf8').matchAll(/id="([^"]+)"/g))elements[match[1]]=new Element(match[1]);
  const document={body:new Element('body'),events:{},getElementById:id=>elements[id]||null,createElement:()=>new Element(),addEventListener:Element.prototype.addEventListener,emit:Element.prototype.emit};
  const window={events:{},addEventListener:Element.prototype.addEventListener,emit:Element.prototype.emit};
  const requests=[],timeouts=new Map(),intervals=new Map();let nextTimer=1,monitor,input,autoEnd=true;
  const responses={'/api/status':{model:'example',speech:{}},'/api/approval':{},'/api/chat':{reply:'Hello.',route:'DEEP'},'/api/voice':{url:'/voice-test'},'/api/reset':{},'/api/memories':{items:[]},'/api/tasks':{items:[]}};
  const voice=elements.voice;
  voice.play=function(){this.paused=false;this.onplaying?.();if(autoEnd)queueMicrotask(()=>{this.paused=true;this.onended?.();});return Promise.resolve();};
  class AudioContext {
    constructor(){this.state='running';this.destination={};}
    resume(){this.state='running';return Promise.resolve();}
    createMediaElementSource(){return {connect(){}};}
    createAnalyser(){return {connect(){},getByteTimeDomainData(samples){samples.fill(128);}};}
  }
  class Monitor {
    constructor(options){this.options=options;this.starts=0;this.stops=0;this.active=false;monitor=this;}
    async start(){this.starts++;this.active=true;this.options.onStatus(true,null);return true;}
    stop(){this.stops++;this.active=false;this.options.onStatus(false,null);}
  }
  class Input {
    constructor(options){this.options=options;this.active=false;this.starts=[];this.cancels=0;input=this;}
    start(duration){this.active=true;this.starts.push(duration);this.options.onState('listening');}
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
  const sandbox={document,window,navigator:{mediaDevices:{}},DoubleClapDetector,StandbyMonitor:Monitor,
    RecordedVoiceInput:Input,DashboardWidgets:Widgets,parseVoiceCommand,console,Date,Uint8Array,
    requestAnimationFrame:()=>1,
    setTimeout:(fn,delay)=>{const id=nextTimer++;timeouts.set(id,{fn,delay});return id;},clearTimeout:id=>timeouts.delete(id),
    setInterval:(fn,delay)=>{const id=nextTimer++;intervals.set(id,{fn,delay});return id;},clearInterval:id=>intervals.delete(id),
    fetch:async(url,options={})=>{const body=options.body?JSON.parse(options.body):undefined;requests.push({url,body});
      const response=typeof responses[url]==='function'?await responses[url](body):responses[url];
      if(response===undefined)throw new Error('Unexpected request '+url);
      return {ok:true,json:async()=>response};}
  };
  if(recording)sandbox.MediaRecorder=function(){};
  const context=vm.createContext(sandbox);vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/app.js'),'utf8'),context);
  return {elements,document,window,requests,responses,intervals,
    get monitor(){return monitor;},get input(){return input;},set autoEnd(value){autoEnd=value;},
    run:code=>vm.runInContext(code,context),
    flush:async()=>{for(let i=0;i<12;i++)await Promise.resolve();},
    heard:async text=>{input.active=false;input.options.onState('idle');await input.options.onText(text);},
    finishSpeech:()=>{voice.paused=true;voice.onended?.();}
  };
}

(async()=>{
  const main=app();await main.flush();assert.equal(main.monitor,undefined,'Standby waits for a user activation');
  await main.elements.wake.onclick();assert.equal(main.monitor.active,true);assert.equal(main.elements.wake.hidden,true);
  assert.equal(main.monitor.options.isBusy(),false);
  await main.run('send("Help me plan a trip")');
  assert.deepEqual(main.requests.find(item=>item.url==='/api/chat').body,{text:'Help me plan a trip',mode:'auto'});
  assert.equal(main.elements.routeLabel.textContent,'DEEP REASONING');

  await main.run('send("mute")');assert.equal(main.monitor.active,true);assert.equal(main.monitor.stops,0);
  assert.equal(main.monitor.options.isBusy(),false,'Muted replies do not disable clap wake');
  main.monitor.options.onTrigger();assert.equal(main.input.starts.at(-1),8000);assert.equal(main.monitor.options.isBusy(),true);
  await main.heard('unmute');assert.equal(main.monitor.active,true);assert.equal(main.monitor.options.isBusy(),false);
  await main.run('send("pause mic")');assert.equal(main.monitor.active,false);assert.equal(main.monitor.stops,1);
  const captures=main.input.starts.length;main.run('startListening(true)');assert.equal(main.input.starts.length,captures);
  await main.elements.muteBtn.onclick();assert.equal(main.monitor.active,true);

  // Existing reply playback must settle before an immediate spoken-control reply.
  main.autoEnd=false;const oldSpeech=main.run('speak("An older response")');await main.flush();
  assert.equal(main.monitor.options.isBusy(),true,'IRIS cannot trigger itself while speaking');
  const newSpeech=main.run('send("what time is it")');await main.flush();
  let oldSettled=false;oldSpeech.then(()=>oldSettled=true);await main.flush();assert.equal(oldSettled,true,'Replacing speech resolves its prior completion');
  main.finishSpeech();await newSpeech;assert.equal(main.monitor.options.isBusy(),false,'Standby resumes after speech');
  main.autoEnd=true;

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

  const unsupported=app({recording:false});await unsupported.flush();await unsupported.elements.wake.onclick();
  unsupported.run('startListening(true)');assert.match(unsupported.elements.toast.textContent,/cannot record/);
  unsupported.document.emit('keydown',{code:'Escape',target:unsupported.elements.reactor});
  await unsupported.run('send("pause mic")');assert.equal(unsupported.monitor.active,false);
  console.log('Desktop automatic routing, standby activation, mute/pause, echo suppression, scoped approvals, and unsupported-browser controls passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
