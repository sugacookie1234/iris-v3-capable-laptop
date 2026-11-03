'use strict';
const assert=require('node:assert/strict');
const {renderBusiness}=require('../web/business.js');
const {parseVoiceCommand}=require('../web/standby.js');
class Element{
  constructor(tag){this.tag=tag;this.children=[];this.textContent='';this.value='';}
  append(...v){this.children.push(...v);}
  replaceChildren(...v){this.children=v;}
  setAttribute(){}
  set innerHTML(value){throw new Error('HTML rendering forbidden');}
}
const document={createElement:tag=>new Element(tag)};
function descendants(e){return [e,...e.children.flatMap(descendants)];}
function find(root,text){const found=descendants(root).find(e=>e.textContent===text);assert.ok(found,text);return found;}
(async()=>{
  assert.equal(parseVoiceCommand('show business'),'business');
  assert.notEqual(parseVoiceCommand('buy inventory for my business'),'business');
  const root=new Element('div'),calls=[];let release;
  renderBusiness(root,{document,items:[],onSave:async value=>{calls.push(value);await new Promise(resolve=>release=resolve);throw new Error('Synthetic network loss');}});
  find(root,'Project name').children[0].value='Synthetic project';
  find(root,'Starting budget').children[0].value='500';
  find(root,'Product name').children[0].value='<script>unsafe</script>';
  find(root,'Add product to compare').onclick();
  assert.equal(descendants(root).filter(e=>e.textContent==='Product name').length,2);
  const save=find(root,'Save and evaluate');
  const first=save.onclick();await save.onclick();assert.equal(calls.length,1);
  assert.equal(save.disabled,true);assert.equal(calls[0].project.products[0].unit_cost,'');
  assert.equal(calls[0].project.products[0].name,'<script>unsafe</script>');
  release();await first;assert.equal(save.disabled,false);
  const second=save.onclick();assert.equal(calls[1].request_id,calls[0].request_id);release();await second;
  find(root,'Starting budget').children[0].value='700';
  const third=save.onclick();assert.notEqual(calls[2].request_id,calls[1].request_id);release();await third;
  renderBusiness(root,{document,items:[{id:'a',revision:1,project:{name:'<img onerror=attack>',currency:'CAD',budget:'500'},report:{currency:'CAD',evaluations:[{name:'kit',recommendation:'Gather costs',confidence:'unverified assumptions',missing_research:['supplier'],economics:{status:'incomplete',missing:['unit_cost']}}],limitations:['No purchases']}}],onSave:async()=>{}});
  assert.ok(descendants(root).some(e=>e.textContent.includes('<img onerror=attack>')));
  console.log('Business forms, unknown costs, text safety, duplicate suppression, retry IDs and voice routing passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
