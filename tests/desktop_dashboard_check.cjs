'use strict';
const assert=require('node:assert/strict');
const {DashboardWidgets}=require('../web/dashboard.js');
const weather=(overrides={})=>({status:'ok',temperature_c:8.9,condition:'Cloudy',feels_like_c:7,wind_kph:10,...overrides});
const position=(latitude=43.65321,longitude=-79.38321)=>({coords:{latitude,longitude}});
function deferred(){let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return{promise,resolve,reject};}
function fixture(options={}){
  const elements=new Map();
  const element=id=>{if(!elements.has(id))elements.set(id,{textContent:'',disabled:false,children:[],replaceChildren(){this.children=[];},append(node){this.children.push(node);}});return elements.get(id);};
  const dashboard=new DashboardWidgets({element,geolocation:{getCurrentPosition(resolve){resolve(position());}},api:async()=>weather(),...options});
  return{dashboard,element};
}
global.document={createElement:()=>({children:[],append(node){this.children.push(node);}})};

(async()=>{
  // Location stays approximate; multiple callers await the same fresh reading.
  const requests=[],geo=deferred(),reading=deferred();let locationCalls=0;
  const {dashboard,element}=fixture({
    geolocation:{getCurrentPosition(resolve,reject,options){locationCalls++;assert.equal(options.enableHighAccuracy,false);geo.promise.then(resolve,reject);}},
    api:(path,payload)=>{requests.push({path,payload});return reading.promise;}
  });
  dashboard.weather=weather({temperature_c:99});
  const first=dashboard.locate(),second=dashboard.locate();
  assert.equal(first,second);
  assert.equal(dashboard.weather,null);
  assert.equal(locationCalls,1);
  assert.equal(element('locationBtn').disabled,true);
  geo.resolve(position());await Promise.resolve();await Promise.resolve();
  assert.deepEqual(requests[0].payload,{latitude:43.65,longitude:-79.38});
  let secondFinished=false;second.then(()=>{secondFinished=true;});await Promise.resolve();
  assert.equal(secondFinished,false,'Concurrent voice request must await weather, not return the old reading.');
  reading.resolve(weather());
  assert.equal((await first).temperature_c,8.9);
  assert.equal(await first,await second);
  assert.equal(element('weatherTemp').textContent,9);
  assert.equal(element('locationBtn').disabled,false);

  // Losing permission clears both old weather and old coordinates, with a retry.
  dashboard.geolocation={getCurrentPosition(resolve,reject){reject({code:1});}};
  assert.equal(await dashboard.locate(),null);
  assert.equal(dashboard.weather,null);assert.equal(dashboard.coords,null);
  assert.equal(element('weatherTemp').textContent,'—');
  assert.match(dashboard.weatherMessage,/Allow location/);
  assert.equal(element('locationBtn').disabled,false);
  assert.equal(requests.length,1,'Denied location must not query weather for the previous location.');
  dashboard.geolocation={getCurrentPosition(resolve){resolve(position(49.28273,-123.12073));}};
  dashboard.api=async(path,payload)=>{requests.push({path,payload});return weather({temperature_c:14});};
  assert.equal((await dashboard.locate()).temperature_c,14);
  assert.deepEqual(requests.at(-1).payload,{latitude:49.28,longitude:-123.12});

  // Permission denial, location timeout and a weather outage are distinct.
  for(const [code,pattern] of [[2,/location is unavailable/],[3,/timed out/]]){
    dashboard.geolocation={getCurrentPosition(resolve,reject){reject({code});}};
    assert.equal(await dashboard.locate(),null);assert.match(dashboard.weatherMessage,pattern);
    assert.doesNotMatch(dashboard.weatherMessage,/Allow location/);
  }
  dashboard.geolocation=undefined;
  assert.equal(await dashboard.locate(),null);assert.match(dashboard.weatherMessage,/on this device/);
  dashboard.geolocation={getCurrentPosition(resolve){resolve(position(NaN,12));}};
  assert.equal(await dashboard.locate(),null);assert.equal(dashboard.coords,null);
  dashboard.geolocation={getCurrentPosition(resolve){resolve(position());}};
  for(const response of [null,weather({temperature_c:null}),weather({status:'unavailable',message:'Weather service is temporarily unavailable.'})]){
    dashboard.api=async()=>response;
    assert.equal(await dashboard.locate(),null);
    assert.equal(dashboard.weather,null);assert.equal(element('weatherTemp').textContent,'—');
    assert.equal(element('weatherStamp').textContent,'Unable to refresh');
    assert.match(dashboard.weatherMessage,/Weather/);assert.doesNotMatch(dashboard.weatherMessage,/Allow location/);
  }
  dashboard.api=async()=>{throw Error('Offline');};
  assert.equal(await dashboard.loadWeather(),null);
  assert.match(dashboard.weatherMessage,/Retrying later/);
  dashboard.api=async()=>weather({stale:true,wind_kph:null,observed_at:'2026-10-24T12:00:00Z'});
  assert.equal((await dashboard.loadWeather()).stale,true);
  assert.match(element('weatherStamp').textContent,/cached/);
  assert.doesNotMatch(element('weatherDetail').textContent,/NaN|Wind 0/);

  // An older request cannot overwrite a new location, even if it finishes last.
  const old=deferred(),fresh=deferred();let calls=0;
  dashboard.api=()=>++calls===1?old.promise:fresh.promise;
  const oldRequest=dashboard.loadWeather();
  dashboard.geolocation={getCurrentPosition(resolve){resolve(position(45,10));}};
  const newRequest=dashboard.locate();await Promise.resolve();
  fresh.resolve(weather({temperature_c:25}));await newRequest;
  old.resolve(weather({temperature_c:-20}));
  assert.equal(await oldRequest,null);
  assert.equal(dashboard.weather.temperature_c,25);assert.equal(element('weatherTemp').textContent,25);

  // Closing the page during geolocation must not send a subsequent weather request.
  const pendingLocation=deferred();let stoppedApiCalls=0,stoppedGeoCalls=0;
  const closing=fixture({
    geolocation:{getCurrentPosition(resolve,reject){stoppedGeoCalls++;pendingLocation.promise.then(resolve,reject);}},
    api:async()=>{stoppedApiCalls++;return weather();}
  });
  const closingRequest=closing.dashboard.locate();closing.dashboard.stop();
  const closingDetail=closing.element('weatherDetail').textContent;
  pendingLocation.resolve(position());
  assert.equal(await closingRequest,null);assert.equal(stoppedApiCalls,0);
  assert.equal(closing.dashboard.coords,null);assert.equal(closing.dashboard.weather,null);
  assert.equal(closing.element('weatherDetail').textContent,closingDetail);
  assert.equal(closing.element('locationBtn').disabled,false);
  assert.equal(await closing.dashboard.locate(),null);assert.equal(stoppedGeoCalls,1);

  // A weather response or failure finishing after stop cannot publish any reading.
  for(const fails of [false,true]){
    const pendingWeather=deferred();
    const closingWeather=fixture({api:()=>pendingWeather.promise});
    closingWeather.dashboard.coords={latitude:43,longitude:-79};
    closingWeather.element('weatherTemp').textContent='unchanged';
    closingWeather.element('weatherDetail').textContent='unchanged';
    const fetching=closingWeather.dashboard.loadWeather();closingWeather.dashboard.stop();
    if(fails)pendingWeather.reject(Error('Offline'));else pendingWeather.resolve(weather());
    assert.equal(await fetching,null);assert.equal(closingWeather.dashboard.weather,null);
    assert.equal(closingWeather.element('weatherTemp').textContent,'unchanged');
    assert.equal(closingWeather.element('weatherDetail').textContent,'unchanged');
    assert.equal(await closingWeather.dashboard.loadWeather(),null);
  }

  // Market refreshes coalesce; unavailable rows cannot be read as real quotes.
  const market=deferred();let marketCalls=0;
  dashboard.api=()=>{marketCalls++;return market.promise;};
  const marketFirst=dashboard.loadMarkets(),marketSecond=dashboard.loadMarkets();
  assert.equal(marketFirst,marketSecond);assert.equal(marketCalls,1);
  market.resolve({status:'stale',stale:true,items:[{symbol:'SPY',name:'S&P 500',status:'unavailable',value:100,change_percent:3}]});
  assert.equal((await marketFirst).items[0].value,null);
  assert.match(element('marketStamp').textContent,/cached/);
  dashboard.api=async()=>({status:'unavailable',items:[{value:123}]});
  assert.equal(await dashboard.loadMarkets(),null);assert.equal(dashboard.markets,null);
  assert.match(element('marketStamp').textContent,/unavailable/);
  dashboard.api=async()=>{throw Error('Offline');};
  assert.equal(await dashboard.loadMarkets(),null);

  // Stopping while the browser checks permission must not restart standby work.
  const originalNavigator=Object.getOwnPropertyDescriptor(globalThis,'navigator');
  const originalSetInterval=global.setInterval,originalClearInterval=global.clearInterval;
  const permission=deferred();let timer,cleared=0,starts=0;
  try{
    Object.defineProperty(globalThis,'navigator',{configurable:true,value:{permissions:{query:()=>permission.promise}}});
    global.setInterval=fn=>{starts++;timer=fn;return 17;};
    global.clearInterval=id=>{if(id===17)cleared++;};
    let geoCalls=0;
    const stopped=fixture({api:async()=>({items:[]}),geolocation:{getCurrentPosition(){geoCalls++;}}}).dashboard;
    const starting=stopped.start();await stopped.start();stopped.stop();
    permission.resolve({state:'granted'});await starting;
    assert.equal(starts,1);assert.equal(cleared,1);assert.equal(geoCalls,0);

    // Scheduled refresh reacquires location, and a denial stops repeated requests.
    Object.defineProperty(globalThis,'navigator',{configurable:true,value:{permissions:{query:async()=>({state:'prompt'})}}});
    const periodic=fixture({api:async path=>path==='/api/weather'?weather():{items:[]}}).dashboard;
    await periodic.start();periodic.coords={latitude:1,longitude:1};
    periodic.geolocation={getCurrentPosition(resolve,reject){geoCalls++;reject({code:1});}};
    timer();await periodic.locationRequest;assert.equal(geoCalls,1);
    timer();assert.equal(geoCalls,1);periodic.stop();
  }finally{
    global.setInterval=originalSetInterval;global.clearInterval=originalClearInterval;
    if(originalNavigator)Object.defineProperty(globalThis,'navigator',originalNavigator);else delete globalThis.navigator;
  }
  console.log('Dashboard location races, permission recovery, weather availability and refresh checks passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
