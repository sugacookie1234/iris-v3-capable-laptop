'use strict';

// All content is rendered by the app as text. Only the loopback API owns writes.
class OrganizationFeed {
  constructor({api,onSnapshot=()=>{},onActivity=()=>{},onReminder=async()=>{},
    isBusy=()=>false,schedule=(fn,ms)=>setTimeout(fn,ms),cancel=id=>clearTimeout(id)}) {
    Object.assign(this,{api,onSnapshot,onActivity,onReminder,isBusy,schedule,cancel});
    this.seen=new Set();this.delivered=new Set();this.acknowledged=new Set();this.questions=[];this.started=false;
    this.stopped=false;this.primed=false;this.timer=null;this.pending=false;
  }
  start(){if(this.started)return;this.started=true;this.stopped=false;this.poll();}
  stop(){this.stopped=true;if(this.timer!==null)this.cancel(this.timer);this.timer=null;}
  async poll(){
    if(this.stopped||this.pending)return;this.pending=true;
    try {
      const data=await this.api('/api/activity');if(this.stopped)return;
      this.onSnapshot(data);
      const active=Boolean(data.status?.enabled);
      const openQuestions=new Set((data.activity||[]).filter(item=>item.kind==='clarification'&&item.state==='applied').map(item=>item.id));
      this.questions=active?this.questions.filter(item=>openQuestions.has(item.id)):[];
      for(const item of [...(data.activity||[])].reverse()) {
        if(this.seen.has(item.id))continue;this.seen.add(item.id);
        if(this.primed&&item.state==='applied') {
          this.onActivity(item);
          if(item.kind==='clarification'&&active&&item.state==='applied')this.questions.push(item);
        }
      }
      this.primed=true;
      if(this.seen.size>300)this.seen=new Set((data.activity||[]).map(item=>item.id));
      // Retry failed acknowledgements without playing the same reminder again.
      for(const item of data.reminders||[]) {
        if(this.delivered.has(item.id)&&!this.acknowledged.has(item.id)) {
          try {await this.api('/api/reminders/ack',{id:item.id});this.acknowledged.add(item.id);}catch{}
          if(this.stopped)return;
        }
      }
      if(active&&!this.isBusy()&&!this.stopped) {
        const reminder=(data.reminders||[]).find(item=>!this.delivered.has(item.id));
        if(reminder) {
          await this.onReminder(reminder);this.delivered.add(reminder.id);if(this.stopped)return;
          await this.api('/api/reminders/ack',{id:reminder.id});this.acknowledged.add(reminder.id);
        } else if(this.questions.length) {
          const item=this.questions.shift();
          await this.onReminder({id:item.id,title:'One detail',message:item.detail,clarification:true});
        }
      }
    } catch {} // An unavailable local connection is retried; it never authorizes an action.
    finally {this.pending=false;if(!this.stopped)this.timer=this.schedule(()=>this.poll(),3000);}
  }
}
if(typeof module!=='undefined')module.exports={OrganizationFeed};
