'use strict';
class DashboardWidgets {
  constructor({api,element=id=>document.getElementById(id),geolocation=globalThis.navigator?.geolocation}) {
    Object.assign(this,{api,element,geolocation});this.weather=null;this.markets=null;this.coords=null;this.locating=false;
    this.weatherMessage='Use your location to see the local weather.';this.weatherVersion=0;this.startVersion=0;this.lifecycleVersion=0;this.stopped=false;
  }
  loadMarkets() {
    if(this.marketRequest)return this.marketRequest;
    this.marketRequest=this.fetchMarkets().finally(()=>{this.marketRequest=null;});
    return this.marketRequest;
  }
  async fetchMarkets() {
    try {
      const result=await this.api('/api/markets');
      if(!result||result.status==='unavailable')throw Error('Market data unavailable');
      const data={...result,items:(result.items||[]).map(item=>item.status==='unavailable'?{...item,value:null,change_percent:null}:item)};
      this.markets=data;
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
  locate() {
    if(this.stopped)return Promise.resolve(null);
    if(this.locationRequest)return this.locationRequest;
    // A new location request must not leave an old location readable as current.
    ++this.weatherVersion;this.coords=null;
    if(!this.geolocation){this.weatherUnavailable('Location is unavailable on this device.');return Promise.resolve(null);}
    this.locating=true;this.element('locationBtn').disabled=true;
    this.weatherUnavailable('Finding weather near you…','Locating…');
    const lifecycle=this.lifecycleVersion;
    this.locationRequest=this.resolveLocation(lifecycle).finally(()=>{
      if(lifecycle===this.lifecycleVersion){this.locating=false;this.element('locationBtn').disabled=false;this.locationRequest=null;}
    });
    return this.locationRequest;
  }
  async resolveLocation(lifecycle) {
    try {
      const position=await new Promise((resolve,reject)=>this.geolocation.getCurrentPosition(resolve,reject,
        {enableHighAccuracy:false,timeout:12000,maximumAge:15*60*1000}));
      if(lifecycle!==this.lifecycleVersion)return null;
      const {latitude,longitude}=position?.coords||{};
      if(!Number.isFinite(latitude)||!Number.isFinite(longitude)||Math.abs(latitude)>90||Math.abs(longitude)>180)throw Error('Invalid location');
      this.coords={latitude:Math.round(latitude*100)/100,longitude:Math.round(longitude*100)/100};
      return await this.loadWeather();
    }catch(error){
      if(lifecycle!==this.lifecycleVersion)return null;
      this.coords=null;
      const message=error?.code===1?'Allow location for IRIS to show local weather.':error?.code===3?'Finding your location timed out. Try again.':'Your location is unavailable. Try again.';
      this.weatherUnavailable(message,'Location unavailable');
      this.element('locationBtn').textContent='Try location again ↗';return null;
    }
  }
  weatherUnavailable(message,stamp='Unavailable') {
    this.weather=null;this.weatherMessage=message;
    this.element('weatherTemp').textContent='—';
    this.element('weatherCondition').textContent='Weather unavailable';
    this.element('weatherDetail').textContent=message;
    this.element('weatherStamp').textContent=stamp;
    this.element('weatherStamp').title=message;
  }
  async loadWeather() {
    if(this.stopped||!this.coords)return null;
    const version=++this.weatherVersion;
    try {
      const data=await this.api('/api/weather',{...this.coords});
      if(version!==this.weatherVersion)return null;
      if(!data||data.status==='unavailable'||!Number.isFinite(data.temperature_c)){
        this.weatherUnavailable(data?.message||'Weather is temporarily unavailable. Try again later.','Unable to refresh');
        return null;
      }
      this.weather=data;this.weatherMessage=data.message||'';
      this.element('weatherTemp').textContent=Number.isFinite(data.temperature_c)?Math.round(data.temperature_c):'—';
      this.element('weatherCondition').textContent=data.condition||'Weather unavailable';
      const detail=[];
      if(Number.isFinite(data.feels_like_c))detail.push('Feels like '+Math.round(data.feels_like_c)+'°');
      if(Number.isFinite(data.wind_kph))detail.push('Wind '+Math.round(data.wind_kph)+' km/h');
      this.element('weatherDetail').textContent=detail.join(' · ')||data.message||'Additional weather details unavailable.';
      this.element('locationBtn').textContent='Refresh location ↗';
      let when='';if(data.observed_at){const date=new Date(data.observed_at);if(!Number.isNaN(date.getTime()))when=date.toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'});}
      this.element('weatherStamp').textContent='Near you'+(when?' · '+when:'')+(data.stale?' · cached':'');
      this.element('weatherStamp').title=data.message||'';
    }catch{
      if(version!==this.weatherVersion)return null;
      this.weatherUnavailable('Weather is unavailable. Retrying later.','Unable to refresh');
    }
    return this.weather;
  }
  async start() {
    if(this.started)return;
    this.started=true;this.stopped=false;const version=++this.startVersion;
    this.element('locationBtn').onclick=()=>this.locate();this.loadMarkets();
    this.timer=setInterval(()=>{this.loadMarkets();if(this.coords)this.locate();},15*60*1000);
    try {if((await globalThis.navigator?.permissions?.query({name:'geolocation'}))?.state==='granted'&&version===this.startVersion)this.locate();}catch{}
  }
  stop(){
    this.started=false;this.stopped=true;++this.startVersion;++this.lifecycleVersion;++this.weatherVersion;clearInterval(this.timer);
    this.locating=false;this.locationRequest=null;this.element('locationBtn').disabled=false;
  }
}
if(typeof module!=='undefined')module.exports={DashboardWidgets};
