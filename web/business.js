'use strict';
const BUSINESS_COST_FIELDS={price:'Selling price (excluding tax)',unit_cost:'Product cost per unit',inbound_shipping:'Inbound shipping per unit',packaging:'Packaging per unit',fulfilment:'Fulfilment per unit',outbound_shipping:'Outbound shipping per unit',transaction_fixed:'Fixed transaction fee per sale',transaction_percent:'Transaction percentage',advertising:'Advertising per sale',returns_allowance:'Returns allowance per sale',duties:'Duties per unit',fixed_costs:'Total fixed setup costs'};
const BUSINESS_RESEARCH_FIELDS={customer:'Target customer',problem:'Problem solved',competitors:'Competitors (supplied evidence only)',differentiation:'Differentiation',supplier:'Supplier feasibility and missing terms',fulfilment_plan:'Fulfilment plan',risks:'Risks and operational complexity'};

function renderBusiness(container,{document,items,onSave}){
  container.replaceChildren();
  const add=(parent,tag,value='')=>{const e=document.createElement(tag);e.textContent=value;parent.append(e);return e;};
  add(container,'p','Local feasibility workspace. Inputs are assumptions until checked. No live research, supplier contact, purchases or payments. Blank costs remain unknown; enter 0 only when justified.');
  const list=add(container,'div'),editor=add(container,'div');editor.className='business-editor';
  const button=(parent,label,action)=>{const b=add(parent,'button',label);b.type='button';b.onclick=action;return b;};
  const display=item=>{
    const section=add(list,'section');section.className='experience-item';
    add(section,'h3',item.project.name+' · '+item.project.currency+' '+item.project.budget+' budget');
    button(section,'Edit and compare',()=>edit(item));
    for(const result of item.report.evaluations){
      add(section,'h4',result.name);add(section,'p',result.recommendation);
      add(section,'p','Confidence: '+result.confidence+'. Missing research: '+(result.missing_research.join(', ')||'none specified; claims still unverified'));
      const costs=result.economics;
      if(costs.status==='incomplete')add(section,'p','Missing costs: '+costs.missing.map(k=>BUSINESS_COST_FIELDS[k]||k).join(', '));
      else{
        const labels={revenue:'Scenario revenue',gross_profit:'Gross profit',contribution_per_unit:'Contribution per unit',contribution_total:'Total contribution',operating_profit_before_tax:'Operating profit before tax',conservative_cash_required:'Conservative cash required',budget_gap:'Budget gap'};
        for(const [key,label] of Object.entries(labels))add(section,'p',label+': '+item.report.currency+' '+costs[key]);
        add(section,'p','Break-even units: '+(costs.break_even_units??'not achievable with nonpositive contribution')+' · Net profit: unknown');
        add(section,'p','Sensitivity — contribution with price down 10%: '+costs.sensitivity.price_minus_10_percent_contribution+'; shipping up 25%: '+costs.sensitivity.shipping_plus_25_percent_contribution+' '+item.report.currency);
      }
    }
    for(const limitation of item.report.limitations)add(section,'p',limitation);
  };
  function edit(item=null){
    editor.replaceChildren();
    const p=item?.project||{currency:'CAD',products:[{name:'',quantity:1,evidence:[]}]};
    add(editor,'h3',item?'Edit business project':'New business project');
    const input=(parent,label,value='',multiline=false)=>{const wrap=add(parent,'label',label);const node=add(wrap,multiline?'textarea':'input');node.value=value??'';node.maxLength=multiline?3000:150;return node;};
    const name=input(editor,'Project name',p.name),currency=input(editor,'Currency',p.currency),budget=input(editor,'Starting budget',p.budget);
    const context=input(editor,'Context and constraints',p.context,true),goals=input(editor,'Goals',p.goals,true);
    const status=add(editor,'select');status.setAttribute('aria-label','Project status');
    for(const state of ['research','paused','archived']){const option=add(status,'option',state);option.value=state;}
    status.value=p.status||'research';
    const products=add(editor,'div'),entries=[];
    function product(raw={name:'',quantity:1,evidence:[]}){
      if(entries.length>=10)return;
      const box=add(products,'fieldset');add(box,'legend','Product scenario '+(entries.length+1));
      const fields={name:input(box,'Product name',raw.name),quantity:input(box,'Scenario units (not a demand forecast)',raw.quantity)};
      for(const [key,label] of Object.entries(BUSINESS_COST_FIELDS))fields[key]=input(box,label,raw[key]);
      for(const [key,label] of Object.entries(BUSINESS_RESEARCH_FIELDS))fields[key]=input(box,label,raw[key],true);
      const evidenceBox=add(box,'div'),evidence=[];
      function evidenceEntry(value={claim:'',source:'',status:'assumption'}){
        if(evidence.length>=20)return;
        const row=add(evidenceBox,'fieldset');add(row,'legend','Supplied evidence');
        const claim=input(row,'Claim',value.claim,true),source=input(row,'Source / provenance (not fetched)',value.source);
        const state=add(row,'select');state.setAttribute('aria-label','Evidence status');
        for(const label of ['assumption','supplied','contradicted']){const option=add(state,'option',label);option.value=label;}
        state.value=value.status;evidence.push({claim,source,state});
      }
      for(const value of raw.evidence||[])evidenceEntry(value);
      button(box,'Add evidence',()=>evidenceEntry());
      entries.push({fields,evidence});
    }
    for(const raw of p.products)product(raw);
    button(editor,'Add product to compare',()=>product());
    const message=add(editor,'p');message.setAttribute('role','status');
    let pending=false,requestId=null,lastPayload=null;
    const save=button(editor,'Save and evaluate',async()=>{
      if(pending)return;
      const project={name:name.value,currency:currency.value,budget:budget.value,context:context.value,goals:goals.value,status:status.value,
        products:entries.map(({fields,evidence})=>({...Object.fromEntries(Object.entries(fields).map(([k,v])=>[k,v.value])),quantity:Number(fields.quantity.value),tax_status:'unresolved',
          evidence:evidence.map(v=>({claim:v.claim.value,source:v.source.value,status:v.state.value}))}))};
      const payload=JSON.stringify(project);
      if(payload!==lastPayload){requestId=globalThis.crypto.randomUUID();lastPayload=payload;}
      pending=true;save.disabled=true;message.textContent='Saving local evaluation…';
      try{await onSave({project,request_id:requestId,...(item?{id:item.id,revision:item.revision}:{})});message.textContent='Saved.';}
      catch{message.textContent='Could not save. Check amounts, missing project fields and source labels. If another window edited this project, reopen Business before retrying.';}
      finally{pending=false;save.disabled=false;}
    });
  }
  button(container,'New project',()=>edit());
  if(!items.length){add(list,'p','No saved projects. Create one with your own budget and supplied evidence.');edit();}
  for(const item of items)display(item);
}
if(typeof module!=='undefined')module.exports={renderBusiness,BUSINESS_COST_FIELDS};
