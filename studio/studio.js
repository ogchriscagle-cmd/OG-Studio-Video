'use strict';
const $ = id => document.getElementById(id);
let state = {busy:false,storyboard:null,clips:{}}, style='Cinematic', ready=false, rendering='', activeScene=null, activeClip=null, polling=false;
let appearanceBaseline='', appliedDraft=null;
let activityStarted=null;
let pendingPreview=null, workspaceTimer=null, restoringWorkspace=false;
function captureWorkspace(){
  const drafts={};
  document.querySelectorAll('.scene-card').forEach(card=>{
    const fields=card.querySelectorAll('textarea');
    if(fields.length===2)drafts[card.dataset.scene]={image:fields[0].value,motion:fields[1].value};
  });
  return {...options(),aspect:$('aspect').value,reference_name:$('reference-name').value,
    asset_ids:$('asset-ids').value,export_size:$('export-size').value,export_quality:$('export-quality').value,scene_drafts:drafts,preview_seconds:audio.currentTime||0,scroll_y:window.scrollY||0,social:window.socialStudio?.capture()||{}};
}
async function persistWorkspace(){
  if(!ready||restoringWorkspace)return;
  try{const result=await window.pywebview.api.update_workspace(captureWorkspace());if(result.error)showError(result.error);}
  catch(error){showError('Could not save the workspace: '+String(error));}
}
function scheduleWorkspace(){updateDirectionSummary();clearTimeout(workspaceTimer);workspaceTimer=setTimeout(persistWorkspace,350);}
const audio=$('audio'), video=$('video');
const time = n => `${String(Math.floor((n||0)/60)).padStart(2,'0')}:${String(Math.floor((n||0)%60)).padStart(2,'0')}`;
function updateActivity(){
  const error=!$('error').hidden;
  document.body.classList.toggle('status-error',error);
  $('activity-state').textContent=error?'Needs attention':state.busy?'Working':'Ready';
  $('activity-time').textContent=state.busy&&activityStarted!==null?`${Math.floor((Date.now()-activityStarted)/1000)}s elapsed`:'';
}
function showError(message){$('error').textContent=message||'';$('error').hidden=!message;updateActivity();}
async function call(method,...args){
  if(!ready){showError('Open OG Studio Video using the desktop launcher to connect to Python.');return;}
  try{if(method!=='get_state')await persistWorkspace();const result=await window.pywebview.api[method](...args);if(result.error&&!('busy' in result)){showError(result.error);return;}render(result);}
  catch(error){showError(String(error));}
}
function options(){return {title:$('title').value.trim(),artist:$('artist').value.trim(),style,character:$('character-name').value,appearance:$('appearance').value,concept:$('concept').value,mood:$('mood').value,lighting:$('lighting').value,location:$('location').value.trim(),camera:$('camera').value};}
function updateDirectionSummary(){
  const o=options();
  $('direction-summary').textContent=[`Style: ${o.style}`,`Mood: ${o.mood||'Follow song'}`,`Lighting: ${o.lighting||'Use visual style'}`,o.location?`Location: ${o.location}`:null,`Camera: ${o.camera||'Follow song'}`].filter(Boolean).join(' · ');
}
function render(next){
  const old=state;state=next;
  const restoring=state.workspace_revision!==old.workspace_revision&&!!state.ui;
  if(restoring){
    restoringWorkspace=true;audio.pause();
    const ui=state.ui;
    for(const [id,key] of Object.entries({'title':'title','artist':'artist','character-name':'character','appearance':'appearance','concept':'concept','reference-name':'reference_name','asset-ids':'asset_ids','mood':'mood','lighting':'lighting','location':'location','camera':'camera'}))$(id).value=ui[key]??'';
    style=ui.style||'Cinematic';document.querySelectorAll('.style').forEach(b=>b.classList.toggle('selected',b.dataset.style===style));
    $('aspect').value=ui.aspect==='9:16'?'9:16':'16:9';$('frame-label').textContent=$('aspect').value;$('screen').classList.toggle('vertical',$('aspect').value==='9:16');
    pendingPreview=Math.max(0,Number(ui.preview_seconds)||0);appliedDraft=state.appearance_draft?.text||null;
    $('export-size').value=ui.export_size==='720'?'720':'1080';$('export-quality').value=['low','medium','high'].includes(ui.export_quality)?ui.export_quality:'high';
  }
  if(state.busy&&!old.busy)activityStarted=Date.now();
  if(!state.busy)activityStarted=null;
  document.body.classList.toggle('busy',state.busy);
  $('download-progress').hidden=!state.busy||typeof state.download_percent!=='number';
  $('download-progress').value=state.download_percent||0;
  $('status').textContent=state.status;showError(state.error||state.save_error);
  document.querySelectorAll('button').forEach(b=>{b.disabled=!ready||state.busy;});
  document.querySelectorAll('.requires-board').forEach(b=>{b.disabled=!ready||state.busy||!state.storyboard;});
  if(state.audio){
    $('track-name').textContent=state.audio.name;
    if(old.audio?.url!==state.audio.url){audio.src=state.audio.url;activeClip=null;activeScene=null;video.pause();video.hidden=true;$('scene-overlay').hidden=true;$('empty-screen').hidden=false;
      if(!$('title').value.trim())$('title').value=state.audio.name.replace(/\.[^.]+$/,'');}
  }
  if(state.photo){$('portrait-image').src=state.photo.url;$('portrait-image').hidden=false;
    if(old.photo?.url!==state.photo.url&&!restoring){const name=state.photo.name.replace(/\.[^.]+$/,'');$('reference-name').value=name.charAt(0).toUpperCase()+name.slice(1);
      appearanceBaseline=$('appearance').value;appliedDraft=null;$('appearance-suggestion').hidden=true;}}
  $('draft-appearance').disabled=!ready||state.busy||!state.photo;
  const draft=state.appearance_draft;
  if(draft&&draft.photo_url===state.photo?.url&&draft.text!==appliedDraft){
    if($('appearance').value===appearanceBaseline){$('appearance').value=draft.text;}
    else{$('suggestion-text').textContent=draft.text;$('appearance-suggestion').hidden=false;}
    appliedDraft=draft.text;
  }
  $('appearance-status').textContent=state.busy&&state.status.startsWith('Drafting appearance')?'Drafting appearance locally… First use downloads a model and may take several minutes.':draft?'Draft ready. Review clothing, hair, and accessories for mistakes.':'Selecting a photo automatically drafts appearance on this device. First use downloads a vision model.';
  if(state.appearance_error)$('appearance-status').textContent=`Could not draft appearance: ${state.appearance_error} You can type it manually or retry.`;
  $('duration').textContent=state.analysis?time(state.analysis.duration):'—';
  $('tempo').textContent=state.analysis?state.analysis.tempo:'—';
  $('count').textContent=state.storyboard?.scene_count??'—';
  $('scene-badge').textContent=`${state.storyboard?.scene_count??0} scenes`;
  const tracked=Object.values(state.tracking||{}), matched=tracked.filter(t=>t.status==='ready').length;
  $('tracking-summary').textContent=`${matched} / ${state.storyboard?.scene_count??0} clips ready · ${tracked.filter(t=>t.status==='submitted').length} submitted · ${tracked.filter(t=>t.status==='submission_unknown').length} need review`;
  $('auto-assemble').disabled=!ready||state.busy||!state.storyboard||matched!==state.storyboard.scene_count;
  $('import-all-clips').disabled=!ready||state.busy||matched===0;
  const account=state.account||'missing';
  $('account-status').textContent=({connected:'Connected · sign-in remembered',saved:'Saved sign-in available',missing:'Not signed in',expired:'Sign-in expired',unavailable:'Connection could not be checked'})[account]||'Check connection';
  $('account-detail').textContent=account==='unavailable'?'Your saved session is kept. Try Check connection again when VideoExpress is available.':'OG Studio Video automatically reuses your saved session for generation, clips, and exports—even after reopening.';
  $('account-login').textContent=['connected','saved'].includes(account)?'Reconnect account':'Sign in & remember';
  $('app-version').textContent=state.app_version?'v'+state.app_version:'';
  const update=state.app_update;
  $('check-updates').textContent=update?.status==='available'?`↓ Download ${update.latest}`:update?.status==='downloaded'?'Show downloaded update':update?.status==='needs_access'?'Sign in on GitHub ↗':update?.status==='manual'?'View update ↗':'↻ Check updates';
  updateDirectionSummary();
  const finalExport=state.final_export;
  $('open-final-video').disabled=!ready||state.busy||finalExport?.status!=='completed';
  $('export-video').textContent=finalExport&&['submitted','submission_unknown','download_pending'].includes(finalExport.status)?'Resume export & download ↓':'Export & download video ↓';
  $('final-export-status').textContent=finalExport?.status==='completed'?`Saved: ${finalExport.path}`:finalExport?`Export: ${finalExport.status.replaceAll('_',' ')}. Retrying a pending export checks its result without another submission.`:'MP4 · Uses your VideoExpress account rendering limits.';
  const signature=JSON.stringify([state.storyboard,state.clips,state.tracking]);
  if(signature!==rendering){rendering=signature;renderBoard();syncPreview(true);}
  document.querySelectorAll('.auto-import').forEach(b=>{b.disabled=!ready||state.busy||state.tracking?.[b.dataset.scene]?.status!=='ready';});
  window.socialStudio?.render(state,restoring);
  window.walkthrough?.render();
  if(restoring){
    if(!state.photo){$('portrait-image').hidden=true;$('portrait-image').removeAttribute('src');}
    if(!state.audio){audio.removeAttribute('src');$('track-name').textContent='Choose your track';}
    requestAnimationFrame(()=>{window.scrollTo(0,Math.max(0,Number(state.ui.scroll_y)||0));restoringWorkspace=false;});
  }
}
function renderBoard(){
  const board=$('board');if(!state.storyboard){if(board.querySelector('.scene-card'))board.innerHTML='<div class="blank"><span>▦</span><h3>A blank canvas. Endless possibilities.</h3><p>Choose a track and create your first storyboard.</p></div>';return;}
  board.replaceChildren();
  for(const scene of state.storyboard.scenes){
    const card=document.createElement('article');card.className='scene-card';card.dataset.scene=String(scene.scene_number);
    const top=document.createElement('div');top.className='scene-top';
    const num=document.createElement('strong');num.textContent=`SCENE ${String(scene.scene_number).padStart(2,'0')}`;
    const timing=document.createElement('span');timing.textContent=`${time(scene.start)} – ${time(scene.end)} · ${scene.duration}s`;top.append(num,timing);
    const content=document.createElement('div');content.className='scene-content';
    const label=document.createElement('strong');label.textContent=scene.section_label.charAt(0).toUpperCase()+scene.section_label.slice(1);content.append(label);
    const imageLabel=document.createElement('label');imageLabel.textContent='Image direction';
    const draft=state.ui?.scene_drafts?.[String(scene.scene_number)];
    const image=document.createElement('textarea');image.rows=5;image.value=draft?.image??scene.image_prompt;image.disabled=state.busy;imageLabel.append(image);
    const motionLabel=document.createElement('label');motionLabel.textContent='Motion & atmosphere';
    const motion=document.createElement('textarea');motion.rows=3;motion.value=draft?.motion??scene.video_audio_prompt;motion.disabled=state.busy;motionLabel.append(motion);
    const actions=document.createElement('div');actions.className='scene-actions';
    const save=document.createElement('button');save.className='quiet';save.textContent='Save prompts';save.disabled=state.busy;save.onclick=()=>call('edit_scene',scene.scene_number,image.value,motion.value);
    const generateScene=document.createElement('button');generateScene.className='quiet generate-scene';generateScene.textContent='✦ Generate scene';generateScene.disabled=state.busy;
    generateScene.onclick=()=>{if(confirm(`Generate scene ${scene.scene_number} only using the prompts shown on this card? This uses VideoExpress credits. Identical tracked jobs are skipped; changed prompts create a new clip.`))call('generate_scene',scene.scene_number,$('title').value,$('reference-name').value,$('aspect').value,image.value,motion.value);};
    const load=document.createElement('button');load.className='quiet';load.textContent='Import clip ↗';load.disabled=state.busy;load.onclick=()=>call('choose_media','clip',scene.scene_number);
    const preview=document.createElement('button');preview.className='quiet';preview.textContent='Preview';preview.onclick=()=>{audio.currentTime=Math.min(scene.start,Number.isFinite(audio.duration)?audio.duration:scene.start);syncPreview(true);$('screen').scrollIntoView({block:'center',behavior:'smooth'});};
    actions.append(save,generateScene,load,preview);content.append(imageLabel,motionLabel,actions);
    if(state.clips[String(scene.scene_number)]){const name=document.createElement('span');name.className='clip-name';name.textContent='✓ '+state.clips[String(scene.scene_number)].name;content.append(name);}
    card.append(top,content);board.append(card);
    const tracking=state.tracking?.[String(scene.scene_number)];
    const autoImport=document.createElement('button');autoImport.className='quiet auto-import';autoImport.dataset.scene=String(scene.scene_number);autoImport.textContent='Auto-import clip ↓';
    autoImport.disabled=!ready||state.busy||tracking?.status!=='ready';
    autoImport.onclick=()=>call('auto_import_clip',scene.scene_number);actions.insertBefore(autoImport,load);
    if(tracking){const status=document.createElement('span');status.className='clip-name';status.textContent=tracking.status==='ready'?`✓ VideoExpress clip matched · ${tracking.asset_id}`:`VideoExpress · ${tracking.status.replaceAll('_',' ')}`;content.append(status);}
    if(tracking?.error){const detail=document.createElement('p');detail.className='hint';detail.textContent=tracking.error;content.append(detail);}
  }
}
function syncPreview(force=false){
  const current=audio.currentTime||0, duration=Number.isFinite(audio.duration)?audio.duration:0;
  $('clock').textContent=`${time(current)} / ${time(duration)}`;$('seek').value=duration?current/duration*100:0;
  if(!state.storyboard)return;
  const scenes=state.storyboard.scenes;const scene=scenes.find(s=>s.start<=current&&current<s.end)||scenes[scenes.length-1];
  if(!scene)return;
  const clip=state.clips[String(scene.scene_number)];
  if(force||activeScene!==scene.scene_number||activeClip!==clip?.url){
    activeScene=scene.scene_number;activeClip=clip?.url;$('empty-screen').hidden=true;
    $('preview-label').textContent=`SCENE ${String(scene.scene_number).padStart(2,'0')} · ${time(scene.start)} – ${time(scene.end)}`;
    $('preview-heading').textContent=scene.section_label.charAt(0).toUpperCase()+scene.section_label.slice(1);
    $('preview-prompt').textContent=scene.image_prompt;
    video.hidden=!clip;$('scene-overlay').hidden=!!clip;
    $('preview-mode').textContent=clip?'Imported clip · song audio':'Prompt preview · import a rendered clip to see footage';
    if(clip){if(video.getAttribute('src')!==clip.url)video.src=clip.url;}else{video.pause();video.removeAttribute('src');}
  }
  if(clip&&Number.isFinite(video.duration)){
    const desired=Math.min(Math.max(0,video.duration-.05),Math.max(0,current-scene.start));
    if(Math.abs(video.currentTime-desired)>.5)video.currentTime=desired;
    if(audio.paused){video.pause();}else if(video.paused&&desired<video.duration-.1){video.play().catch(()=>{});}
  }
}
document.querySelectorAll('[data-scroll]').forEach(b=>b.onclick=()=>{window.socialStudio?.show('music');document.querySelectorAll('.nav').forEach(n=>n.classList.toggle('active',n===b));$(b.dataset.scroll).scrollIntoView({behavior:'smooth',block:'start'});});
document.querySelectorAll('[data-style]').forEach(b=>b.onclick=()=>{style=b.dataset.style;document.querySelectorAll('.style').forEach(s=>s.classList.toggle('selected',s===b));updateDirectionSummary();});
$('pick-audio').onclick=$('change-track').onclick=()=>call('choose_media','audio');
$('pick-photo').onclick=$('change-photo').onclick=()=>call('choose_media','photo');
$('draft-appearance').onclick=()=>{appearanceBaseline=$('appearance').value;appliedDraft=null;call('draft_appearance');};
$('apply-appearance').onclick=()=>{if(state.appearance_draft?.photo_url===state.photo?.url){$('appearance').value=state.appearance_draft.text;$('appearance-suggestion').hidden=true;}};
$('analyze').onclick=()=>{if(state.storyboard&&!confirm('Rebuild the storyboard? This replaces edited prompts and imported clip assignments.'))return;audio.pause();call('analyze',options());};
$('export').onclick=()=>call('export');$('login').onclick=()=>call('login');
$('open-project').onclick=()=>call('open_project');$('save-project').onclick=()=>call('save_project');
$('upload').onclick=()=>{if(confirm('Upload the selected song and reference photo to your VideoExpress account?'))call('upload',$('title').value);};
function generate(first){if(confirm(first?'Generate the first scene in VideoExpress? This uses your account credits. Tracked scenes are skipped.':'Generate the remaining scenes in VideoExpress? This uses your account credits. Tracked scenes are skipped.'))call('generate',$('title').value,$('reference-name').value,$('aspect').value,first);}
$('test-scene').onclick=()=>generate(true);$('generate').onclick=()=>generate(false);
$('assemble').onclick=()=>{if(confirm('Place the selected clips and song on the VideoExpress timeline and save a project? Start with an empty editor timeline.'))call('assemble',$('title').value,$('asset-ids').value);};
$('refresh-tracking').onclick=()=>call('refresh_tracking');
$('import-all-clips').onclick=()=>call('auto_import_all_clips');
$('view-videoexpress').onclick=()=>call('view_videoexpress_project',$('title').value);
$('export-video').onclick=()=>{if(confirm(`Export the saved “${$('title').value} - Final Video” as a ${$('export-size').value}p MP4 at ${$('export-quality').value} quality and download it? This uses your VideoExpress rendering allowance. Choose a download folder next.`))call('export_final_video',$('title').value,$('export-size').value,$('export-quality').value);};
$('open-final-video').onclick=()=>call('open_downloaded_video');
$('auto-assemble').onclick=()=>{if(confirm('Assemble the confirmed tracked clips with your song in VideoExpress? Start with an empty editor timeline.'))call('assemble',$('title').value,'');};
$('aspect').onchange=()=>{$('frame-label').textContent=$('aspect').value;$('screen').classList.toggle('vertical',$('aspect').value==='9:16');};
$('play').onclick=()=>{if(!state.audio){showError('Choose a track to preview.');return;}if(audio.paused)audio.play().catch(e=>showError('Could not play this audio format: '+e.message));else audio.pause();};
audio.addEventListener('play',()=>{$('play').textContent='Ⅱ';syncPreview(true);});audio.addEventListener('pause',()=>{$('play').textContent='▶';video.pause();});
audio.addEventListener('timeupdate',()=>syncPreview());audio.addEventListener('loadedmetadata',()=>{if(pendingPreview!==null){audio.currentTime=Math.min(pendingPreview,Number.isFinite(audio.duration)?audio.duration:pendingPreview);pendingPreview=null;}syncPreview(true);});video.addEventListener('loadedmetadata',()=>syncPreview(true));
audio.addEventListener('error',()=>showError('This audio format cannot be previewed by the desktop browser. WAV or MP3 is recommended; analysis may still work.'));
video.addEventListener('error',()=>showError('This clip format cannot be previewed. Try an MP4 encoded with H.264.'));
$('seek').oninput=()=>{if(Number.isFinite(audio.duration)){audio.currentTime=Number($('seek').value)/100*audio.duration;syncPreview(true);}};
async function connect(){ready=true;$('bridge-warning').hidden=true;await call('get_state');if(window.pywebview.api.ui_ready)await window.pywebview.api.ui_ready();setInterval(async()=>{if(polling)return;polling=true;try{const next=await window.pywebview.api.get_state();if(JSON.stringify(next)!==JSON.stringify(state))render(next);}catch(e){showError('Desktop connection lost. Restart OG Studio Video.');}finally{polling=false;}},800);}
window.addEventListener('pywebviewready',connect,{once:true});
document.querySelectorAll('button').forEach(b=>b.disabled=true);
setTimeout(()=>{if(!ready)$('bridge-warning').hidden=false;},2500);
setInterval(()=>{if(state.busy)updateActivity();},1000);
if(typeof ResizeObserver!=='undefined')new ResizeObserver(entries=>{
  document.documentElement.style.setProperty('--activity-height',`${entries[0].target.offsetHeight+20}px`);
}).observe(document.querySelector('.app-status'));
document.addEventListener('input',scheduleWorkspace);document.addEventListener('change',scheduleWorkspace);
document.addEventListener('click',scheduleWorkspace);window.addEventListener('scroll',scheduleWorkspace,{passive:true});
setInterval(()=>{if(!audio.paused||state.save_error)persistWorkspace();},2000);

$('account-login').onclick=()=>call('login');
$('account-check').onclick=()=>call('check_videoexpress_login');

$('check-updates').onclick=()=>{const update=state.app_update;call(update?.status==='available'?'download_app_update':update?.status==='downloaded'?'show_app_update':['needs_access','manual'].includes(update?.status)?'open_app_releases':'check_app_update');};
$('open-releases').onclick=()=>call('open_app_releases');
