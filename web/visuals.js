'use strict';
function renderVisual(parent,spec){
  if(!spec||typeof spec!=='object'||Array.isArray(spec)||Object.keys(spec).sort().join(',')!=='kind,labels,points,summary,title,version'||spec.version!==1||spec.kind!=='line'||!Array.isArray(spec.labels)||spec.labels.length<1||spec.labels.length>4||spec.labels.some(x=>typeof x!=='string'||x.length>80)||!Array.isArray(spec.points)||!spec.points.length||spec.points.length>100||spec.points.some(p=>!Array.isArray(p)||p.length!==spec.labels.length+1||p.some(x=>typeof x!=='number'||!Number.isFinite(x)||Math.abs(x)>1e30))||typeof spec.title!=='string'||spec.title.length>300||typeof spec.summary!=='string'||spec.summary.length>300)throw new Error('Invalid visual');
  const box=document.createElement('section');
  const title=document.createElement('h3');title.textContent=spec.title;box.append(title);
  const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 600 300');svg.setAttribute('role','img');svg.setAttribute('aria-label',spec.title);svg.style.width='100%';
  const max=Math.max(1,...spec.points.flatMap(p=>p.slice(1))), min=Math.min(0,...spec.points.flatMap(p=>p.slice(1)));
  const low=Math.min(...spec.points.map(p=>p[0])),high=Math.max(low+1,...spec.points.map(p=>p[0]));
  const colors=['#55ddff','#f2ba63','#92df9d','#dd92ff'];
  const path=(d,color)=>{const p=document.createElementNS('http://www.w3.org/2000/svg','path');p.setAttribute('d',d);p.setAttribute('fill','none');p.setAttribute('stroke',color);p.setAttribute('stroke-width','2');svg.append(p);};
  path('M 45 15 L 45 260 L 585 260','#8899aa');
  const label=(value,x,y)=>{const node=document.createElementNS('http://www.w3.org/2000/svg','text');node.textContent=String(value);node.setAttribute('x',x);node.setAttribute('y',y);node.setAttribute('fill','#adc7d4');node.setAttribute('font-size','11');svg.append(node);};
  label('Units',48,12);label('Year',540,293);
  for(let n=0;n<=4;n++){label(Math.round(min+(max-min)*n/4).toLocaleString(),2,260-n*60);label((low+(high-low)*n/4).toFixed(1),45+n*135,278);}

  spec.labels.forEach((label,i)=>{path(spec.points.map((p,n)=>(n?'L':'M')+' '+(45+(p[0]-low)/(high-low)*540)+' '+(260-(p[i+1]-min)/(max-min)*240)).join(' '),colors[i]);const legend=document.createElement('p');legend.textContent=label;legend.style.color=colors[i];box.append(legend);});
  box.append(svg);const summary=document.createElement('p');summary.textContent=spec.summary;box.append(summary);
  const details=document.createElement('details'),caption=document.createElement('summary');caption.textContent='Accessible data table';details.append(caption);
  const table=document.createElement('table');
  for(const row of [['Year',...spec.labels],...spec.points]){const tr=document.createElement('tr');for(const value of row){const td=document.createElement('td');td.textContent=String(value);tr.append(td);}table.append(tr);}details.append(table);box.append(details);parent.append(box);
}
if(typeof module!=='undefined')module.exports={renderVisual};

if(typeof window!=='undefined'&&typeof window.dispatchEvent==='function')window.dispatchEvent(new Event('iris-renderer-ready'));
