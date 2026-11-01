// Exercise the real renderer without a browser or additional test dependencies.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const elements = new Map();
function element(id) {
  if (!elements.has(id)) elements.set(id, {
    value:'', textContent:'', hidden:false, disabled:false,
    classList:{toggle(){},add(){},remove(){}},
    addEventListener(){}, querySelector(){return null;}, pause(){}, removeAttribute(){},
  });
  return elements.get(id);
}
const context = vm.createContext({
  document:{getElementById:element,querySelectorAll(){return[];},addEventListener(){},body:element('body')},
  window:{addEventListener(){},scrollTo(){}},setTimeout(){},clearTimeout(){},requestAnimationFrame(fn){fn();},setInterval(){},console,
});
vm.runInContext(fs.readFileSync('studio/studio.js','utf8'), context);
function render(photo, text=null) {
  const state={busy:false,status:'Ready',error:null,photo:{url:photo,name:'portrait.jpg'},audio:null,
    storyboard:null,clips:{},tracking:{},appearance_draft:text?{photo_url:photo,text}:null};
  context.snapshot=state;
  vm.runInContext('render(snapshot)',context);
}
render('/media/first');
render('/media/first','Clothing: blue jacket.');
assert.equal(element('appearance').value,'Clothing: blue jacket.');
render('/media/second');
element('appearance').value='My own description';
render('/media/second','Clothing: red shirt.');
assert.equal(element('appearance').value,'My own description');
assert.equal(element('appearance-suggestion').hidden,false);
assert.equal(element('suggestion-text').textContent,'Clothing: red shirt.');
element('apply-appearance').onclick();
assert.equal(element('appearance').value,'Clothing: red shirt.');
assert.equal(element('appearance-suggestion').hidden,true);
console.log('Appearance UI passed: auto-fill, manual edit protection, apply suggestion.');
context.snapshot={...context.snapshot,busy:true,status:'Drafting appearance locally…'};
vm.runInContext('render(snapshot)',context);
assert.equal(element('activity-state').textContent,'Working');
assert.match(element('activity-time').textContent,/elapsed/);
vm.runInContext('showError("Could not finish")',context);
assert.equal(element('activity-state').textContent,'Needs attention');
assert.equal(element('error').textContent,'Could not finish');
console.log('Status bar passed: current activity, elapsed time, visible error.');
context.snapshot={...context.snapshot,busy:false,workspace_revision:'restored',ui:{title:'Recovered project',appearance:'My saved appearance',aspect:'9:16',reference_name:'Portrait',style:'Neon noir',preview_seconds:12}};
vm.runInContext('render(snapshot)',context);
assert.equal(element('title').value,'Recovered project');
assert.equal(element('appearance').value,'My saved appearance');
assert.equal(element('aspect').value,'9:16');
assert.equal(element('reference-name').value,'Portrait');
assert.equal(vm.runInContext('captureWorkspace().appearance',context),'My saved appearance');
console.log('Workspace UI passed: restore fields, preserve appearance, capture settings.');
