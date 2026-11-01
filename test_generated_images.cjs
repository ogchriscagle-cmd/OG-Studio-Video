const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('videoexpress_automation.py','utf8');
const script=source.match(/GENERATED_IMAGE_STATE_JS = """([\s\S]*?)"""/)[1];
function probe(images){
  const clicked=[];
  const items=images.map((data,index)=>({querySelector(){return {...data,getAttribute(){return data.src;}};},click(){clicked.push(index);}}));
  const state=vm.runInNewContext(`(${script})()`,{URL,document:{baseURI:'https://app.videoexpress.ai/',querySelectorAll(){return items;}}});
  return {state,clicked};
}
const error={src:'https://app.videoexpress.ai/img/slide-error.png',complete:true,naturalWidth:512};
const loading={src:'https://app.videoexpress.ai/img/loading-paint3-horiz.gif',complete:true,naturalWidth:512};
const real={src:'https://cdn-ny-b.videoexpress.ai/generated/real-image.jpg',complete:true,naturalWidth:1024};
let result=probe([error,loading]);
assert.equal(result.state.ready,0);assert.equal(result.state.failed,1);assert.equal(result.state.pending,1);assert.deepEqual(result.clicked,[]);
result=probe([error,real]);assert.equal(result.state.ready,1);assert.deepEqual(result.clicked,[1]);
result=probe([error,error]);assert.equal(result.state.failed,2);assert.equal(result.state.ready,0);assert.deepEqual(result.clicked,[]);
console.log('Generated image DOM checks passed: error icons excluded, pending candidate awaited, real candidate selected.');
