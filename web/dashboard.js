'use strict';
class DashboardWidgets {
  constructor({api,element=id=>document.getElementById(id),geolocation=globalThis.navigator?.geolocation}) {
    Object.assign(this,{api,element,geolocation});this.weather=null;this.markets=null;this.coords=null;this.locating=false;
  }
  async loadMarkets() {
    try {
      const data=await this.api('/api/markets');this.markets=data;
      const container=this.element('marketRows');container.replaceChildren();
      for(const item of data.items||[]) {
        const row=document.createElement('div');row.className='market-row';
        const add=(kind,text)=>{const node=document.createElement('span');node.className=kind;node.textContent=text;row.append(node);};
        add('market-name',item.symbol);
        add('market-value',Number.isFinite(item.value)?item.value.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2}):'—');
        add('market-sub',item.name);
        const change=item.change_percent;
        add('market-change '+(change>0?'positive':change<0?'negative':'neutral'),Number.isFinite(change)?(change>=0?'+':'')+change.toFixed(2)+'%':'Unavailable');
        add('market-sub',item.as_of?'As of '+item.as_of:'No close available');
        container.append(row);
      }
      if(!data.items?.length)container.textContent=data.message||'Market data is unavailable.';
      this.element('marketStamp').textContent='Daily closes · USD · not live'+(data.stale?' · cached':'')+(data.status==='unavailable'?' · unavailable':'');
      this.element('marketStamp').title=data.message||'';
    }catch{
      this.markets=null;
      this.element('marketRows').textContent='Market data is unavailable. Retrying later.';
      this.element('marketStamp').textContent='Daily closes · USD · not live · unavailable';
    }
    return this.markets;
  }
  async locate() {
    if(this.locating)return this.weather;
    if(!this.geolocation){this.element('weatherDetail').textContent='Location is unavailable on this device.';return null;}
    this.locating=true;this.element('locationBtn').disabled=true;
    this.element('weatherDetail').textContent='Finding weather near you…';
    try {
      const position=await new Promise((resolve,reject)=>this.geolocation.getCurrentPosition(resolve,reject,
        {enableHighAccuracy:false,timeout:12000,maximumAge:15*60*1000}));
      this.coords={latitude:Math.round(position.coords.latitude*100)/100,longitude:Math.round(position.coords.longitude*100)/100};
      return await this.loadWeather();
    }catch(error){
      this.element('weatherDetail').textContent=error.code===1?'Allow location for IRIS to show local weather.':'Your location is unavailable. Try again.';
      this.element('locationBtn').textContent='Try location again ↗';return null;
    }finally{this.locating=false;this.element('locationBtn').disabled=false;}
  }
  async loadWeather() {
    if(!this.coords)return null;
    try {
      const data=await this.api('/api/weather',this.coords);this.weather=data;
      this.element('weatherTemp').textContent=Number.isFinite(data.temperature_c)?Math.round(data.temperature_c):'—';
      this.element('weatherCondition').textContent=data.condition||'Weather unavailable';
      this.element('weatherDetail').textContent=Number.isFinite(data.feels_like_c)?'Feels like '+Math.round(data.feels_like_c)+'° · Wind '+Math.round(data.wind_kph)+' km/h':data.message||'Try again later.';
      this.element('locationBtn').textContent='Refresh location ↗';
      let when='';if(data.observed_at){const date=new Date(data.observed_at);if(!Number.isNaN(date.getTime()))when=date.toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'});}
      this.element('weatherStamp').textContent='Near you'+(when?' · '+when:'')+(data.stale?' · cached':'');
      this.element('weatherStamp').title=data.message||'';
    }catch{
      this.weather=null;
      this.element('weatherTemp').textContent='—';
      this.element('weatherCondition').textContent='Weather unavailable';
      this.element('weatherDetail').textContent='Weather is unavailable. Retrying later.';
      this.element('weatherStamp').textContent='Unable to refresh';
    }
    return this.weather;
  }
  async start() {
    this.element('locationBtn').onclick=()=>this.locate();this.loadMarkets();
    try {if((await navigator.permissions?.query({name:'geolocation'}))?.state==='granted')this.locate();}catch{}
    this.timer=setInterval(()=>{this.loadMarkets();if(this.coords)this.locate();},15*60*1000);
  }
  stop(){clearInterval(this.timer);}
}
if(typeof module!=='undefined')module.exports={DashboardWidgets};
