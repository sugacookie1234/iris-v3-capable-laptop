'use strict';

const JOB_ACTIVE=new Set(['queued','running','cancelling']);
const JOB_TERMINAL=new Set(['completed','partial','no_matches','failed','cancelled','interrupted']);
const JOB_LABELS={queued:'Queued',running:'Working',cancelling:'Stopping',completed:'Completed',partial:'Completed · limited coverage',no_matches:'No matching notes',failed:'Could not finish',cancelled:'Cancelled',interrupted:'Interrupted'};
const JOB_STAGES={queued:'Waiting to start',search:'Searching notes',read_1:'Reading note 1',read_2:'Reading note 2',read_3:'Reading note 3',draft:'Checking sources and preparing brief',done:'Finished'};

function jobStage(job){return Object.hasOwn(JOB_STAGES,job.stage)?JOB_STAGES[job.stage]:Object.hasOwn(JOB_LABELS,job.status)?JOB_LABELS[job.status]:'Status unavailable';}
function jobSnapshot(value){
  if(!value||typeof value.id!=='string'||!value.id||value.id.length>80||!Object.hasOwn(JOB_LABELS,value.status))return null;
  return {id:value.id,kind:'notes_briefing',topic:typeof value.topic==='string'?value.topic.slice(0,200):'Notes briefing',
    status:value.status,stage:typeof value.stage==='string'?value.stage:'',
    completed_steps:Array.isArray(value.completed_steps)?value.completed_steps.filter(id=>typeof id==='string').slice(0,5):[],
    created_at:typeof value.created_at==='string'?value.created_at:'',updated_at:typeof value.updated_at==='string'?value.updated_at:'',
    attempts:Number.isInteger(value.attempts)?value.attempts:0,result_available:value.result_available===true,
    can_cancel:value.can_cancel===true,can_resume:value.can_resume===true};
}

class JobsFeed {
  constructor({api,onSnapshot=()=>{},onNotice=()=>{},onUnavailable=()=>{},isBusy=()=>false,
    schedule=(fn,ms)=>setTimeout(fn,ms),cancel=id=>clearTimeout(id)}){
    Object.assign(this,{api,onSnapshot,onNotice,onUnavailable,isBusy,schedule,cancel});
    this.jobs=[];this.known=new Map();this.notified=new Set();this.notices=[];
    this.started=false;this.stopped=false;this.primed=false;this.pending=null;this.timer=null;this.generation=0;this.again=false;
  }
  start(){if(this.started||this.stopped)return;this.started=true;return this.poll();}
  stop(){this.stopped=true;this.generation++;this.controller?.abort();if(this.timer!==null)this.cancel(this.timer);this.timer=null;this.notices=[];}
  refresh(){
    if(this.stopped)return Promise.resolve();
    this.generation++;if(this.timer!==null)this.cancel(this.timer);this.timer=null;
    if(this.pending){this.again=true;return this.pending;}
    return this.poll();
  }
  record(value){
    const job=jobSnapshot(value);if(!job||this.stopped)return;
    this.generation++;this._accept([job,...this.jobs.filter(item=>item.id!==job.id)].slice(0,100));
    this.refresh();
  }
  forget(id){if(this.stopped)return;this.generation++;this._accept(this.jobs.filter(job=>job.id!==id));this.refresh();}
  _accept(jobs){
    const known=new Map();
    for(const job of jobs){
      const previous=this.known.get(job.id),key=job.id+':'+job.attempts+':'+job.status;
      if(this.primed&&previous&&JOB_ACTIVE.has(previous.status)&&JOB_TERMINAL.has(job.status)&&!this.notified.has(key)){
        this.notified.add(key);this.notices.push({id:job.id,status:job.status,attempts:job.attempts});
      }
      known.set(job.id,{status:job.status,attempts:job.attempts});
    }
    this.notices=this.notices.filter(item=>known.get(item.id)?.status===item.status&&known.get(item.id)?.attempts===item.attempts).slice(-100);
    if(this.notified.size>500)this.notified=new Set([...this.notified].slice(-300));
    const changed=!this.primed||this.unavailable||JSON.stringify(jobs)!==JSON.stringify(this.jobs);
    this.jobs=jobs;this.known=known;this.primed=true;
    this.unavailable=false;
    if(changed)this.onSnapshot(this.jobs);
    if(!this.isBusy()&&this.notices.length)this.onNotice(this.notices.shift());
  }
  poll(){
    if(this.stopped)return Promise.resolve();
    if(this.pending)return this.pending;
    if(this.timer!==null)this.cancel(this.timer);this.timer=null;
    const generation=this.generation;
    const controller=new AbortController();this.controller=controller;
    let delay=2000;
    this.pending=(async()=>{
      try{
        const data=await Promise.resolve().then(()=>this.stopped?null:this.api('/api/jobs',undefined,controller.signal));
        if(this.stopped||generation!==this.generation)return;
        if(!Array.isArray(data.jobs))throw new Error('Invalid jobs response');
        const unique=new Map();for(const value of data.jobs.slice(0,100)){const job=jobSnapshot(value);if(job)unique.set(job.id,job);}
        this._accept([...unique.values()]);
      }catch{
        delay=5000;if(!this.stopped&&generation===this.generation){this.unavailable=true;this.onUnavailable();}
      }finally{
        this.pending=null;
        if(this.controller===controller)this.controller=null;
        if(!this.stopped){const next=this.again?0:delay;this.again=false;this.timer=this.schedule(()=>this.poll(),next);}
      }
    })();
    return this.pending;
  }
}

function renderJobs(container,jobs,{document,onAction,pending=new Set()}){
  container.replaceChildren();
  const text=(parent,value,tag='p')=>{const item=document.createElement(tag);item.textContent=value;parent.append(item);return item;};
  text(container,'Briefings run locally while you keep chatting. Open a finished job to view its result. Resume starts again using current notes.');
  if(!jobs.length){text(container,'No background jobs yet. Say “Make a briefing from my notes on …”.');return;}
  for(const raw of jobs){
    const job=jobSnapshot(raw);if(!job)continue;
    const row=document.createElement('section');row.className='job-item';
    text(row,job.topic||'Notes briefing','h3');
    text(row,JOB_LABELS[job.status]+' · '+jobStage(job)).className='job-state';
    if(job.status==='interrupted')text(row,job.can_resume?'IRIS stopped before this job finished. Resume will read current sources again.':'IRIS stopped before this job finished. This job cannot be resumed; start a new briefing if needed.');
    const stamp=new Date(job.created_at);if(!Number.isNaN(stamp.valueOf()))text(row,stamp.toLocaleString()+' · Attempt '+job.attempts).className='job-stamp';
    const controls=document.createElement('div');controls.className='job-controls';
    const button=(label,action)=>{const control=document.createElement('button');control.textContent=label;control.disabled=pending.has(job.id);control.onclick=()=>onAction(action,job.id);controls.append(control);};
    if(JOB_ACTIVE.has(job.status)&&job.can_cancel)button('Cancel','cancel');
    if(['interrupted','failed'].includes(job.status)&&job.can_resume)button('Resume','resume');
    if(JOB_TERMINAL.has(job.status)&&job.result_available)button('View result','read');
    if(JOB_TERMINAL.has(job.status))button('Delete','delete');
    row.append(controls);container.append(row);
  }
}
if(typeof module!=='undefined')module.exports={JobsFeed,renderJobs,jobStage,jobSnapshot};
