'use strict';
const assert=require('node:assert/strict');
const {visualUpdatePayload,newerVisual,ensureVisualRenderer}=require('../web/visual-workspace.js');
const state={id:'public-id',revision:2,sequence:4};
assert.deepEqual(visualUpdatePayload(state,{principal:'1000',rate:'7',years:'10',contribution:'200',compared_rate:''}),{id:'public-id',revision:2,changes:{principal:1000,rate:7,years:10,contribution:200,compared_rate:null}});
assert.throws(()=>visualUpdatePayload(state,{principal:'<script>'}));
assert.equal(newerVisual(state,{id:'public-id',revision:1,sequence:3}),false);
assert.equal(newerVisual(state,{id:'older-workflow',revision:99,sequence:2}),false);
assert.equal(newerVisual(state,{id:'new-workflow',revision:1,sequence:5}),true);
const fs=require('node:fs');
const source=fs.readFileSync(require.resolve('../web/visual-workspace.js'),'utf8');
assert.ok(!source.includes('innerHTML'));assert.ok(!source.includes('eval('));
assert.ok(source.includes('abort.abort()'));assert.ok(source.includes('if(busy||!state||stopped)return'));
const html=fs.readFileSync(require.resolve('../web/visual-workspace.html'),'utf8');
for(const field of ['principal','rate','years','contribution','compared_rate'])assert.ok(html.includes(`id="${field}"`));
console.log('Workspace typed updates, stale revision/workflow rejection, field labels and cleanup contracts passed.');

// Simulated DOM race: a dirty form must retain its starting revision even after
// a voice update arrives through polling. No real browser/hardware is implied.
(async()=>{
  const vm=require('node:vm'),elements={},sent=[];let timer;
  const element=id=>elements[id] ||= {value:'',childNodes:[],events:{},
    addEventListener(name,fn){this.events[name]=fn;},replaceChildren(){}};
  const fixture=revision=>({id:'public-id',revision,sequence:revision,
    parameters:{principal:1000,rate:revision===1?5:8,years:10,contribution:0,compared_rate:null},
    visual:{},summary:'Synthetic',totals:{final:2000,contributed:1000,growth:1000}});
  const responses=[{ok:true,status:200,body:fixture(1)},
    {ok:true,status:200,body:fixture(2)},
    {ok:false,status:409,body:{error:'Stale visual revision'}},
    {ok:true,status:200,body:fixture(2)}];
  const context={document:{documentElement:{dataset:{}},getElementById:element,createElement:()=>({childNodes:[]})},
    window:{addEventListener(){},renderVisual(){}},sessionStorage:{getItem:()=> 'synthetic-lease'},
    location:{hash:''},AbortController,renderVisual(){},
    setTimeout(fn){timer=fn;},clearTimeout(){},
    async fetch(path,options){sent.push({path,options});const r=responses.shift();
      assert.ok(r,'Unexpected extra request');return {...r,json:async()=>r.body};}};
  vm.runInNewContext(source,context);
  const flush=()=>new Promise(resolve=>setImmediate(resolve));
  await flush();
  element('principal').value='2000';element('controls').events.input();
  await timer();
  assert.equal(element('rate').value,'5'); // Keep the in-progress form visible.
  element('controls').events.submit({preventDefault(){}});await flush();
  const mutation=sent.find(item=>item.path==='/api/visual/update');
  assert.equal(JSON.parse(mutation.options.body).revision,1);
  assert.equal(element('rate').value,'8'); // Conflict refreshes authoritative values.
  assert.equal(sent.filter(item=>item.path==='/api/visual/update').length,1);
  console.log('Simulated DOM dirty-form/voice-update conflict rejects stale edits without retry.');
})().catch(error=>{console.error(error);process.exitCode=1;});

(async()=>{
 let script;
 const scope={},doc={createElement:()=>({}),head:{append(value){script=value;}}};
 const pending=ensureVisualRenderer(doc,scope);let ready=false;pending.then(()=>ready=true);
 await Promise.resolve();assert.equal(ready,false);assert.equal(script.src,'/visuals.js');
 scope.renderVisual=()=>{};script.onload();assert.equal(await pending,scope.renderVisual);
 const failure=ensureVisualRenderer(doc,{});script.onerror();await assert.rejects(failure,/could not load/);
 const missing=ensureVisualRenderer(doc,{});script.onload();await assert.rejects(missing,/did not initialize/);
 console.log('Renderer readiness waits for execution and rejects missing/failed assets.');
})().catch(error=>{console.error(error);process.exitCode=1;});

(async()=>{
 const vm=require('node:vm');let releasePair,script,requests=0,pagehide;
 const elements={};const element=id=>elements[id] ||= {childNodes:[],events:{},addEventListener(n,f){this.events[n]=f;},replaceChildren(){}};
 const context={document:{documentElement:{dataset:{}},head:{append(s){script=s;}},getElementById:element,createElement:()=>({})},
   window:{irisPairing:new Promise(resolve=>releasePair=resolve),addEventListener(n,f){if(n==='pagehide')pagehide=f;}},
   sessionStorage:{getItem:()=> 'synthetic'},AbortController,setTimeout(){},clearTimeout(){},fetch(){requests++;throw Error('Unexpected request');}};
 vm.runInNewContext(source,context);
 const flush=()=>new Promise(resolve=>setImmediate(resolve));await flush();
 assert.equal(context.document.documentElement.dataset.visualState,'authenticating');assert.equal(requests,0);assert.equal(script,undefined);
 releasePair('ready');await flush();assert.equal(context.document.documentElement.dataset.visualState,'loading-renderer');assert.equal(requests,0);
 pagehide();context.window.renderVisual=()=>{};script.onload();await flush();assert.equal(requests,0);
 console.log('Pairing completion and renderer readiness gate startup; closing during loading prevents requests.');
})().catch(error=>{console.error(error);process.exitCode=1;});
