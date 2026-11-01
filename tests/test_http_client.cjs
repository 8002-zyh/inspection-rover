const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const http = require('../patrol/static/http.js');
const pending = () => new Promise(() => {});
async function main() {
  // Parses the actual inline application script, without executing any controls.
  const html=fs.readFileSync('patrol/templates/index.html','utf8');
  new vm.Script(html.match(/<script>([\s\S]*?)<\/script>/)[1]);
  const originalController=global.AbortController;
  try {
    global.AbortController=undefined;
    global.fetch=pending;
    await assert.rejects(http.request('/test',{},15),/请求超时/);
    global.fetch=async()=>({ok:true,status:200,json:pending});
    await assert.rejects(http.request('/test',{},15),/请求超时/);
    global.fetch=async()=>({ok:false,status:401,json:async()=>({error:'用户名或密码错误'})});
    await assert.rejects(http.request('/test',{},100),/用户名或密码错误/);
    global.fetch=async()=>({ok:true,status:200,json:async()=>{throw Error('html')}});
    await assert.rejects(http.request('/test',{},100),/服务器响应异常/);
    global.fetch=async(path,opts)=>{assert.equal(opts.credentials,'same-origin');return {ok:true,status:200,json:async()=>({csrf:'test'})}};
    assert.deepEqual(await http.request('/test',{},100),{csrf:'test'});
  } finally { global.AbortController=originalController; }
  console.log('PASS: inline syntax, no AbortController, stalled body, auth/error and recovery');
}
main().catch(e=>{console.error(e);process.exitCode=1});
