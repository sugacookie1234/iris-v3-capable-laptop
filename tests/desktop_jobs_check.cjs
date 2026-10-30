const assert=require('node:assert/strict');
const {JobsFeed,renderJobs,jobSnapshot}=require('../web/jobs.js');
const {parseVoiceCommand}=require('../web/standby.js');
const job=(status='running',extra={})=>({id:'brief-1',kind:'notes_briefing',topic:'Project Orion',status,stage:'search',completed_steps:[],attempts:1,created_at:'2026-10-29T12:00:00Z',can_cancel:['queued','running'].includes(status),can_resume:status==='interrupted',result_available:status==='completed',...extra});
const flush=async()=>{for(let i=0;i<8;i++)await Promise.resolve();};
class Element{
  constructor(tag){this.tag=tag;this.children=[];this.textContent='';}
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this.children=children;}
  set innerHTML(_){throw Error('Job content must never be rendered as HTML');}
}
const buttons=root=>root.children.flatMap(child=>child.tag==='button'?[child]:buttons(child));

(async()=>{
  let data={jobs:[job('completed')]},busy=false,requests=0,snapshots=0;
  const notices=[],timers=new Map();let next=0;
  const feed=new JobsFeed({api:async()=>{requests++;return data;},isBusy:()=>busy,
    onSnapshot:()=>snapshots++,onNotice:item=>notices.push(item),
    schedule:(fn,delay)=>{timers.set(++next,{fn,delay});return next;},cancel:id=>timers.delete(id)});
  await feed.start();assert.equal(notices.length,0,'Reloading completed work must not replay completion');
  assert.equal([...timers.values()][0].delay,2000);
  await feed.poll();assert.equal(snapshots,1,'Unchanged polling must not replace focused controls');
  assert.equal(timers.size,1,'Only one future poll is scheduled');
  data={jobs:[job('running'),job('running')]};await feed.poll();assert.equal(feed.jobs.length,1);
  data={jobs:[job('completed',{result:{reply:'PRIVATE RESULT'}})]};busy=true;await feed.poll();
  assert.equal(notices.length,0,'Wait for active conversation or approval to finish');
  assert.equal(feed.jobs[0].result,undefined,'Lists must discard result bodies');
  busy=false;await feed.poll();await feed.poll();assert.equal(notices.length,1);
  data={jobs:[job('queued',{attempts:2}),job('completed',{id:'old-result'})]};await feed.poll();
  data={jobs:[job('completed',{attempts:2}),job('completed',{id:'old-result'})]};await feed.poll();
  assert.equal(notices.length,2,'A resumed attempt can notify once; unseen old results stay quiet');
  feed.stop();await feed.poll();assert.equal(timers.size,0);assert.equal(requests,8);

  let staleState=job(),quiet=false;
  const staleNotices=new JobsFeed({api:async()=>({jobs:[staleState]}),isBusy:()=>!quiet,onNotice:()=>assert.fail('Obsolete terminal notice'),schedule:()=>1,cancel:()=>{}});
  await staleNotices.start();staleState=job('failed',{can_resume:true});await staleNotices.poll();
  staleState=job('queued',{attempts:2});await staleNotices.poll();quiet=true;await staleNotices.poll();staleNotices.stop();

  let resolve,loads=0;
  const raced=new JobsFeed({api:()=>{loads++;return new Promise(done=>resolve=done);},schedule:(fn,delay)=>{timers.set(++next,{fn,delay});return next;},cancel:id=>timers.delete(id)});
  const poll=raced.start();assert.equal(raced.poll(),poll);await flush();assert.equal(loads,1);
  raced.record(job('cancelling'));resolve({jobs:[job('running')]});await poll;
  assert.equal(raced.jobs[0].status,'cancelling','An older poll cannot overwrite a confirmed action');
  assert.equal(timers.size,1);assert.equal([...timers.values()][0].delay,0);
  raced.stop();assert.equal(timers.size,0);

  let lateResolve;const late=new JobsFeed({api:()=>new Promise(done=>lateResolve=done),onSnapshot:()=>assert.fail('late snapshot'),schedule:()=>assert.fail('late schedule')});
  const waiting=late.start();await flush();late.stop();lateResolve({jobs:[job()]});await waiting;
  const neverStarted=new JobsFeed({api:()=>assert.fail('No request may start after unload'),schedule:()=>assert.fail('No timer after unload')});
  const never=neverStarted.start();neverStarted.stop();await never;
  let signal;
  const aborted=new JobsFeed({api:(_path,_body,value)=>{signal=value;return new Promise(resolve=>value.addEventListener('abort',()=>resolve({jobs:[]})));},schedule:()=>assert.fail('No timer after abort')});
  const aborting=aborted.start();await flush();aborted.stop();await aborting;assert.equal(signal.aborted,true);
  let failed=0,healthy=false,recovered=0;
  const retry=new JobsFeed({api:()=>{if(!healthy)throw Error('offline');return {jobs:[]};},onUnavailable:()=>failed++,onSnapshot:()=>recovered++,schedule:(_fn,delay)=>{assert.equal(delay,healthy?2000:5000);return 1;},cancel:()=>{}});
  await retry.start();assert.equal(failed,1);assert.equal(retry.pending,null);
  healthy=true;await retry.poll();assert.equal(recovered,1);retry.stop();

  const document={createElement:tag=>new Element(tag)},body=new Element('div'),actions=[];
  const draw=(items,pending=new Set())=>{renderJobs(body,items,{document,pending,onAction:(action,id)=>actions.push([action,id])});return buttons(body);};
  let controls=draw([job('running',{topic:'<img src=x onerror=bad()>'})]);
  assert.deepEqual(controls.map(button=>button.textContent),['Cancel']);controls[0].onclick();assert.deepEqual(actions,[['cancel','brief-1']]);
  assert.equal(body.children[1].children[0].textContent,'<img src=x onerror=bad()>');
  controls=draw([job('interrupted')]);assert.deepEqual(controls.map(button=>button.textContent),['Resume','Delete']);
  controls=draw([job('failed',{can_resume:true})]);assert.deepEqual(controls.map(button=>button.textContent),['Resume','Delete']);
  controls=draw([job('interrupted',{can_resume:false})]);assert.deepEqual(controls.map(button=>button.textContent),['Delete']);
  controls=draw([job('completed')],new Set(['brief-1']));assert.deepEqual(controls.map(button=>button.textContent),['View result','Delete']);assert(controls.every(button=>button.disabled));
  controls=draw([job('cancelling',{can_cancel:false})]);assert.equal(controls.length,0);
  assert.equal(jobSnapshot({id:'x',status:'unexpected'}),null);
  assert.equal(jobSnapshot({id:'x',status:'constructor'}),null);
  assert.equal(parseVoiceCommand('IRIS, please show my jobs'),'jobs');
  assert.equal(parseVoiceCommand('job status'),'jobs');
  assert.equal(parseVoiceCommand('cancel briefing'),null,'Briefing cancellation goes to the runtime');
  assert.equal(parseVoiceCommand('cancel'),null,'Generic cancellation remains approval-scoped');
  assert.equal(parseVoiceCommand('My jobs have been stressful'),null);
  console.log('Job polling, deduplication, reload, races, recovery, cleanup, controls and text-only rendering passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
