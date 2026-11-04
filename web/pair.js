'use strict';
(async()=>{
  const token=new URLSearchParams(location.hash.slice(1)).get('pair');
  history.replaceState(null,'',location.pathname);
  if(!token)return;
  try{
    const response=await fetch('/api/pair',{method:'POST',headers:{'Content-Type':'application/json','X-IRIS-Request':'1'},body:JSON.stringify({token})});
    if(!response.ok)throw new Error('Pairing rejected');
    const result=await response.json();
    if(location.pathname==='/visual'&&result.visual_token)sessionStorage.setItem('iris.visual.lease',result.visual_token);
    location.replace(location.pathname==='/visual'?'/visual':'/');
  }catch{(document.getElementById('pairStatus')||document.body).textContent='Pairing expired or failed. Close this window and relaunch IRIS.';}
})();
