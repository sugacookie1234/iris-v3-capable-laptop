'use strict';
const assert=require('node:assert/strict');
const {DashboardWidgets}=require('../web/dashboard.js');
const elements=new Map();
function element(id){if(!elements.has(id))elements.set(id,{textContent:'',disabled:false,replaceChildren(){},append(){}});return elements.get(id);}
global.document={createElement:()=>({append(){}})};
(async()=>{
  const requests=[];
  const dashboard=new DashboardWidgets({element,geolocation:{getCurrentPosition(resolve){resolve({coords:{latitude:43.65321,longitude:-79.38321}});}},
    api:async(path,payload)=>{requests.push({path,payload});return{temperature_c:8.9,condition:'Cloudy',feels_like_c:7,wind_kph:10};}});
  await dashboard.locate();
  assert.deepEqual(requests[0].payload,{latitude:43.65,longitude:-79.38});
  assert.equal(element('weatherTemp').textContent,9);
  assert.equal(element('locationBtn').disabled,false);
  dashboard.api=async()=>{throw Error('Offline');};
  assert.equal(await dashboard.loadWeather(),null);
  assert.equal(element('weatherTemp').textContent,'—');
  assert.equal(element('weatherStamp').textContent,'Unable to refresh');
  dashboard.markets={items:[{value:123}]};
  assert.equal(await dashboard.loadMarkets(),null);
  assert.match(element('marketStamp').textContent,/unavailable/);
  dashboard.geolocation={getCurrentPosition(resolve,reject){reject({code:1});}};
  assert.equal(await dashboard.locate(),null);
  assert.match(element('weatherDetail').textContent,/Allow location/);
  assert.equal(element('locationBtn').disabled,false);
  assert.equal(requests.length,1);
  console.log('Dashboard location, unavailable-data and stale-value checks passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
