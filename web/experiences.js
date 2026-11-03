'use strict';

const EXPERIENCE_STATES={pending:'Needs review · excluded from reuse',kept:'Kept · available in local notes plan previews',dismissed:'Dismissed · excluded from reuse',disputed:'Marked incorrect · reuse revoked'};
const EXPERIENCE_VERIFICATION={source_revision_and_excerpt_match:'Source revisions and excerpts checked; note claims were not fact-checked.',unverified:'Source verification unavailable.'};

function experienceSnapshot(value){
  if(!value||typeof value.id!=='string'||!value.id||value.id.length>100||!Number.isSafeInteger(value.revision)||value.revision<1||!Object.hasOwn(EXPERIENCE_STATES,value.state))return null;
  const text=(key,max=1000)=>typeof value[key]==='string'?value[key].slice(0,max):'';
  return {id:value.id,revision:value.revision,state:value.state,summary:text('summary'),lesson:text('lesson'),
    job_id:text('job_id',100),attempt:Number.isSafeInteger(value.attempt)&&value.attempt>0?value.attempt:null,
    completed_at:text('completed_at',60),expires_at:text('expires_at',60),
    outcome:value.outcome==='completed'?'completed':'partial',
    source_count:Number.isSafeInteger(value.source_count)&&value.source_count>=0?value.source_count:null,
    verification:Object.hasOwn(EXPERIENCE_VERIFICATION,value.verification)?value.verification:'unverified'};
}

function renderExperiences(container,items,{document,onAction,pending=new Set()}){
  container.replaceChildren();
  const text=(parent,value,tag='p',className='')=>{const element=document.createElement(tag);element.textContent=value;element.className=className;parent.append(element);return element;};
  const date=value=>{const parsed=new Date(value);return value&&!Number.isNaN(parsed.valueOf())?parsed.toLocaleString():'Unavailable';};
  text(container,'Metadata-only summaries stay local. They do not contain source paths, note topics or excerpts. Nothing here automatically changes code, models or permissions.','p','experience-guidance');
  text(container,'Keep allows reuse in local notes plan previews; limited coverage adds a coverage caution. Dismiss excludes a summary. Mark incorrect revokes reuse. Forget removes the summary; a temporary fingerprint prevents immediate reimport.','p','experience-guidance');
  const valid=items.map(experienceSnapshot).filter(Boolean);
  if(!valid.length){text(container,'No task memory to review yet. Eligible completed jobs will appear here.');return;}
  for(const item of valid){
    const row=document.createElement('section');row.className='experience-item';
    text(row,item.summary||'Local task summary','h3');
    text(row,EXPERIENCE_STATES[item.state],'p','experience-state');
    if(item.lesson)text(row,item.lesson);
    text(row,(item.outcome==='completed'?'Completed':'Completed with limited coverage')+(item.source_count===null?'':' · '+item.source_count+' source'+(item.source_count===1?'':'s')),'p','experience-outcome');
    text(row,EXPERIENCE_VERIFICATION[item.verification]);
    text(row,'Source job: '+(item.job_id||'Unavailable')+' · Attempt '+(item.attempt??'Unavailable')+' · Completed: '+date(item.completed_at),'p','experience-stamp');
    text(row,'Expires: '+date(item.expires_at),'p','experience-stamp');
    const controls=document.createElement('div');controls.className='experience-controls';
    const button=(label,action)=>{const control=document.createElement('button');control.textContent=label;control.disabled=pending.has(item.id);control.onclick=()=>{if(!control.disabled)return onAction(action,item.id,item.revision);};controls.append(control);};
    if(item.state!=='kept')button('Keep','keep');
    if(item.state==='pending')button('Dismiss','dismiss');
    if(item.state==='kept')button('Mark incorrect','dispute');
    if(item.state!=='pending')button('Forget','forget');
    row.append(controls);container.append(row);
  }
}

if(typeof module!=='undefined')module.exports={experienceSnapshot,renderExperiences};
