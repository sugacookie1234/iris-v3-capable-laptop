"use strict";
function visualUpdatePayload(state,values){
  if(!state||typeof state.id!=="string"||!Number.isInteger(state.revision))throw Error("No current visual.");
  const changes={};
  for(const name of ['principal','rate','years','contribution','compared_rate']){
    const raw=values[name];
    if(name==='compared_rate'&&raw===''){changes[name]=null;continue;}
    if(typeof raw!=='string'||!raw.trim()||!Number.isFinite(Number(raw)))throw Error('Enter valid numeric values.');
    changes[name]=Number(raw);
  }
  return {id:state.id,revision:state.revision,changes};
}
function ensureVisualRenderer(doc,scope){
  if(typeof scope.renderVisual==='function')return Promise.resolve(scope.renderVisual);
  return new Promise((resolve,reject)=>{
    const script=doc.createElement('script');
    script.src='/visuals.js';script.async=false;
    script.onload=()=>{if(typeof scope.renderVisual==='function')resolve(scope.renderVisual);else reject(Error('Chart renderer did not initialize.'));};
    script.onerror=()=>reject(Error('Chart renderer could not load.'));
    doc.head.append(script);
  });
}
function newerVisual(current,next){return !!next&&Number.isInteger(next.sequence)&&(!current||next.sequence>=current.sequence)&&(!current||next.id!==current.id||next.revision>=current.revision);}
if(typeof module!=='undefined')module.exports={visualUpdatePayload,newerVisual,ensureVisualRenderer};
if(typeof window!=='undefined'&&document.getElementById('controls')){
  let state=null,editState=null,stopped=false,busy=false,dirty=false,timer,renderer;
  const readiness=value=>{document.documentElement.dataset.visualState=value;};
  const abort=new AbortController(),get=id=>document.getElementById(id);
  let lease;
  async function request(path,value){
    const response=await fetch(path,{method:value?'POST':'GET',signal:abort.signal,headers:{'Content-Type':'application/json','X-IRIS-Request':'1','X-IRIS-Visual':lease||''},...(value?{body:JSON.stringify(value)}:{})});
    const body=await response.json();
    if(!response.ok){if(response.status===403||response.status===400&&String(body.error).startsWith('No active visual')){stopped=response.status===403;readiness(stopped?'expired':'no-example');get('chart').replaceChildren();get('totals').textContent='';get('explanation').textContent='';}const error=Error(body.error||'Visual update failed.');error.status=response.status;throw error;}
    return body;
  }
  function display(next){
    if(!newerVisual(state,next))return;
    const box=document.createElement('div');renderer(box,next.visual);readiness('rendered');
    get('chart').replaceChildren(...box.childNodes);state=next;
    get('explanation').textContent=next.summary;
    get('totals').textContent=`Final: ${next.totals.final.toLocaleString()} units · Contributed: ${next.totals.contributed.toLocaleString()} · Growth: ${next.totals.growth.toLocaleString()}`;
    if(!dirty)for(const [key,value] of Object.entries(next.parameters))if(get(key))get(key).value=value===null?'':String(value);
    get('status').textContent=`Active example · revision ${next.revision}`;
  }
  async function poll(){
    if(stopped)return;
    if(!busy)try{const next=await request('/api/visual/state');if(!state||next.id!==state.id||next.revision!==state.revision)display(next);}catch(error){get('status').textContent=error.message;}
    if(!stopped)timer=setTimeout(poll,1500);
  }
  async function update(reset=false){
    if(busy||!state||stopped)return;
    busy=true;get('apply').disabled=true;get('reset').disabled=true;
    try{
      const values=Object.fromEntries(['principal','rate','years','contribution','compared_rate'].map(key=>[key,get(key).value]));
      const payload=reset?{id:state.id,revision:state.revision,changes:{reset:true}}:visualUpdatePayload(editState||state,values);
      const next=await request('/api/visual/update',payload);dirty=false;editState=null;display(next);
    }catch(error){if(error.status===409){dirty=false;editState=null;try{display(await request('/api/visual/state'));}catch{}}get('status').textContent=error.message;}finally{busy=false;get('apply').disabled=false;get('reset').disabled=false;}
  }
  get('controls').addEventListener('input',()=>{if(!dirty)editState=state;dirty=true;});
  get('controls').addEventListener('submit',event=>{event.preventDefault();update();});
  get('reset').addEventListener('click',()=>update(true));
  window.addEventListener('pagehide',()=>{stopped=true;clearTimeout(timer);abort.abort();});
  async function initialize(){
    get('apply').disabled=true;get('reset').disabled=true;get('retry').hidden=true;
    readiness('authenticating');
    const paired=await (window.irisPairing||Promise.resolve('ready'));
    if(stopped||paired!=='ready')return;
    lease=sessionStorage.getItem('iris.visual.lease');
    readiness('loading-renderer');
    try{
      renderer=await ensureVisualRenderer(document,window);
      if(stopped)return;
      readiness('ready');get('apply').disabled=false;get('reset').disabled=false;
      await poll();
    }catch(error){if(stopped)return;readiness('asset-error');get('status').textContent=error.message+' Retry loading the chart.';get('retry').hidden=false;}
  }
  get('retry').addEventListener('click',()=>initialize());
  initialize();
}
