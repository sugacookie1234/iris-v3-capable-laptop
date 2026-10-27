const assert=require('node:assert/strict');
const {OrganizationFeed}=require('../web/organizer.js');
const {parseVoiceCommand}=require('../web/standby.js');

(async()=>{
  let data={status:{enabled:true},activity:[],reminders:[]},busy=false,failAck=false,failDisplay=false;
  const spoken=[],seen=[],acks=[],scheduled=[];
  const feed=new OrganizationFeed({
    api:async(path,value)=>{if(path==='/api/activity')return data;acks.push(value.id);if(failAck)throw Error('offline');return {};},
    onActivity:item=>seen.push(item.id),onReminder:async item=>{if(failDisplay)throw Error('not displayed');spoken.push(item.id);},
    isBusy:()=>busy,schedule:fn=>{scheduled.push(fn);return scheduled.length;},cancel:()=>{}
  });
  await feed.poll();
  data.activity=[{id:'saved',kind:'task',state:'applied'}];
  data.reminders=[{id:'due',message:'Deadline'}];busy=true;
  await feed.poll();assert.deepEqual(seen,['saved']);assert.deepEqual(spoken,[]);
  busy=false;failAck=true;await feed.poll();assert.deepEqual(spoken,['due']);
  failAck=false;await feed.poll();assert.deepEqual(spoken,['due']);assert.equal(acks.length,2);
  data.reminders=[{id:'later'}];data.status.enabled=false;await feed.poll();assert.deepEqual(spoken,['due']);
  data.status.enabled=true;failDisplay=true;await feed.poll();assert.equal(feed.delivered.has('later'),false);
  failDisplay=false;await feed.poll();assert.deepEqual(spoken,['due','later']);
  data.activity=[{id:'ask',kind:'clarification',state:'applied',detail:'When?'}];data.reminders=[];
  busy=true;await feed.poll();assert.equal(feed.questions.length,1);
  data.activity[0].state='resolved';await feed.poll();assert.equal(feed.questions.length,0);
  data.activity=[{id:'ask2',kind:'clarification',state:'applied',detail:'Which date?'}];await feed.poll();assert.equal(feed.questions.length,1);
  data.status.enabled=false;await feed.poll();assert.equal(feed.questions.length,0);
  feed.stop();await feed.poll();assert.deepEqual(spoken,['due','later']);

  let resolve;const late=new OrganizationFeed({api:()=>new Promise(done=>resolve=done),onSnapshot:()=>assert.fail('late display'),schedule:()=>assert.fail('late timer')});
  const pending=late.poll();late.stop();resolve({status:{enabled:true},activity:[],reminders:[]});await pending;
  assert.equal(parseVoiceCommand('Iris, please show my goals'),'goals');
  assert.equal(parseVoiceCommand('Show my notes'),'notes');
  assert.equal(parseVoiceCommand('Undo the last change'),'undo');
  assert.equal(parseVoiceCommand('activity is something I want to discuss'),null);
  console.log('Automatic activity, paused reminders, delayed speech, acknowledgement retries, cleanup and commands passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
