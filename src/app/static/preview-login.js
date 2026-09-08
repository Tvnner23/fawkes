'use strict';
document.getElementById('login').addEventListener('submit', async event => {
  event.preventDefault();
  const input=document.getElementById('credential'), status=document.getElementById('login-result');
  const credential=input.value;input.value='';status.textContent='Signing in…';
  try {
    const response=await fetch('/api/session',{method:'POST',credentials:'same-origin',cache:'no-store',
      headers:{'Content-Type':'application/json'},body:JSON.stringify({credential})});
    if(!response.ok)throw new Error('Sign-in was not accepted.');
    window.location.assign('/dev-console');
  } catch(error) {status.textContent=error.message;}
});
