const assert=require('node:assert/strict');
const {experienceSnapshot,renderExperiences}=require('../web/experiences.js');
const {parseVoiceCommand}=require('../web/standby.js');

const experience=(state='pending',extra={})=>({id:'experience-1',revision:1,state,summary:'Local briefing completed',lesson:'Review source coverage before reusing this procedure.',job_id:'briefing-1',attempt:2,completed_at:'2026-10-29T12:00:00Z',expires_at:'2026-11-28T12:00:00Z',outcome:'completed',source_count:3,verification:'source_revision_and_excerpt_match',...extra});
class Element{
  constructor(tag){this.tag=tag;this.children=[];this.textContent='';}
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this.children=children;}
  set innerHTML(_){throw Error('Task memory must never be rendered as HTML');}
}
const all=root=>[root,...root.children.flatMap(all)];
const document={createElement:tag=>new Element(tag)},body=new Element('div'),actions=[];
const draw=(items,pending=new Set())=>{renderExperiences(body,items,{document,pending,onAction:(...args)=>actions.push(args)});return all(body).filter(item=>item.tag==='button');};

let controls=draw([experience('pending',{summary:'<img src=x onerror=bad()>',lesson:'<script>bad()</script>',topic:'PRIVATE TOPIC',paths:['PRIVATE PATH']})]);
assert.deepEqual(controls.map(button=>button.textContent),['Keep','Dismiss']);
controls[0].onclick();assert.deepEqual(actions,[['keep','experience-1',1]]);
const content=all(body).map(item=>item.textContent).join('\n');
assert.match(content,/<img src=x onerror=bad\(\)>/);assert.match(content,/<script>bad\(\)<\/script>/);
assert.doesNotMatch(content,/PRIVATE TOPIC|PRIVATE PATH/);
assert.match(content,/Metadata-only/);assert.match(content,/automatically changes code, models or permissions/);
assert.match(content,/Source job: briefing-1 · Attempt 2/);assert.match(content,/Completed:/);assert.match(content,/Expires:/);
assert.match(content,/note claims were not fact-checked/);assert.match(content,/temporary fingerprint/);
controls=draw([experience('kept')]);assert.deepEqual(controls.map(button=>button.textContent),['Mark incorrect','Forget']);
controls[0].onclick();assert.deepEqual(actions.at(-1),['dispute','experience-1',1]);
for(const state of ['dismissed','disputed']){
  controls=draw([experience(state)]);assert.deepEqual(controls.map(button=>button.textContent),['Keep','Forget']);
}
controls=draw([experience('kept')],new Set(['experience-1']));assert(controls.every(button=>button.disabled));
const priorActions=actions.length;controls[0].onclick();assert.equal(actions.length,priorActions,'Disabled controls cannot submit review actions');
draw([experience('kept',{outcome:'partial',source_count:1})]);
assert.match(all(body).map(item=>item.textContent).join('\n'),/Completed with limited coverage · 1 source/);
draw([]);assert.match(all(body).map(item=>item.textContent).join('\n'),/No task memory to review/);
for(const patch of [{id:''},{revision:0},{revision:NaN},{state:'constructor'},{state:'unknown'}])assert.equal(experienceSnapshot(experience('pending',patch)),null);
const safe=experienceSnapshot(experience('pending',{verification:'private path',topic:'PRIVATE TOPIC',result:'PRIVATE RESULT'}));
assert.equal(safe.verification,'unverified');assert.equal(safe.result,undefined);assert.equal(safe.topic,undefined);
assert.equal(parseVoiceCommand('IRIS, please show task memory'),'experiences');
assert.equal(parseVoiceCommand('Show learned procedures.'),'experiences');
assert.equal(parseVoiceCommand('I learned procedures yesterday'),null);
assert.equal(parseVoiceCommand('show my memories'),'memories','Task memory remains distinct from conversational memories');
console.log('Task memory controls, metadata rendering, partial outcome, text safety and local voice routing passed.');
