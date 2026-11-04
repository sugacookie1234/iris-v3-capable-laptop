'use strict';
const assert=require('node:assert/strict');
const {renderVisual}=require('../web/visuals.js');
class Element {
 constructor(tag){this.tag=tag;this.children=[];this.style={};this.attributes={};}
 append(...items){this.children.push(...items);}
 setAttribute(name,value){
  assert.ok(!/^on/i.test(name));assert.ok(!['href','src'].includes(name));
  this.attributes[name]=value;
 }
 set innerHTML(value){throw Error('HTML sink forbidden');}
}
global.document={createElement:tag=>new Element(tag),createElementNS:(ns,tag)=>new Element(tag)};
const hostile='<img src=x onerror=attack()> javascript:alert(1)';
const valid={version:1,kind:'line',title:hostile,summary:hostile,labels:[hostile],points:[[0,1],[1,2]]};
const root=new Element('div');renderVisual(root,valid);
const all=node=>[node,...node.children.flatMap(all)];
assert.ok(all(root).some(node=>node.textContent===hostile));
assert.ok(all(root).every(node=>!['script','img','iframe','a'].includes(node.tag)));
assert.ok(all(root).some(node=>node.tag==='table'));
for(const change of [{script:'attack()'},{kind:'html'},{version:2},{points:[]},
 {points:[[0,Infinity]]},{points:[[0,'<svg onload=attack()>']]},
 {points:Array.from({length:101},()=>[0,1])},{labels:['a','b','c','d','e']},
 {title:'x'.repeat(301)},{points:[[true,1]]}]){
 const parent=new Element('div');
 assert.throws(()=>renderVisual(parent,{...valid,...change}),/Invalid visual/);
 assert.equal(parent.children.length,0);
}
console.log('Visual text-only sinks, exact schema, bounded data and accessible table checks passed.');
