'use strict';
window.socialStudio=(()=>{
  const presets={
    'Performance teaser':'An intimate music performance, expressive close-ups, dramatic stage light, build to an energetic final shot',
    'Cinematic story':'A mysterious journey through a rain-soaked city, a striking opening image, an emotional reveal, cinematic realism',
    'Behind the song':'An artist writing and recording a song in a warmly lit studio, intimate details and authentic creative moments',
    'Dream world':'A surreal dream landscape, floating lights, impossible architecture, a memorable visual transformation',
  };
  let mode='video',tab='music',lastSong='',lastVideo='',planSignature='';
  const player=$('social-video-player'),songPlayer=$('social-song-player');
  // Both workspaces use the same card, handlers, and saved account state.
  const accountCard=document.querySelector('.account-card');
  const musicAccountSlot=document.createElement('div');
  accountCard.before(musicAccountSlot);
  const socialAccountSlot=document.createElement('div');
  $('social-workspace').querySelector('.social-modes').before(socialAccountSlot);
  const fieldIds=['start','duration','platform','framing','x','y','hook','cta','preset','prompt','style'];
  function capture(){
    const result={mode,tab};
    fieldIds.forEach(key=>result[key]=$('social-'+key).value);
    return result;
  }
  function settings(){
    const values=capture();
    for(const key of ['start','duration','x','y'])values[key]=Number(values[key]);
    return values;
  }
  function show(which){
    tab=which==='social'?'social':'music';
    $('music-workspace').hidden=tab!=='music';$('social-workspace').hidden=tab!=='social';
    $('workspace-label').textContent=tab==='social'?'Social Clip Studio':'Music video studio';
    (tab==='social'?socialAccountSlot:musicAccountSlot).append(accountCard);
    document.querySelectorAll('.nav').forEach(button=>button.classList.toggle('active',tab==='social'?button.id==='social-nav':button.dataset.scroll==='top'));
    if(tab==='social'){audio.pause();video.pause();}else{player.pause();songPlayer.pause();}
    window.scrollTo(0,0);
  }
  function setMode(value){
    mode=value==='song'?'song':'video';player.pause();songPlayer.pause();
    $('social-video-source').hidden=mode!=='video';$('social-song-source').hidden=mode!=='song';
    $('social-generation').hidden=mode!=='song';
    $('social-mode-video').classList.toggle('selected',mode==='video');$('social-mode-song').classList.toggle('selected',mode==='song');
    syncSource();updatePreview();
  }
  function currentSource(){return (state.social||{})[mode==='song'?'generated':'video'];}
  function bounds(){
    if(mode==='song'&&state.social?.generated)return {start:0,duration:state.social.board.total_duration};
    return {start:Math.max(0,Number($('social-start').value)||0),duration:Math.max(3,Number($('social-duration').value)||30)};
  }
  function syncSource(){
    const source=currentSource();
    if(source&&player.getAttribute('src')!==source.url){player.src=source.url;player.load();}
    if(!source){player.pause();player.removeAttribute('src');}
    player.hidden=!source;$('social-preview-empty').hidden=!!source;
    $('social-preview-detail').textContent=mode==='song'&&!source?'Preview your song segment while the vertical scenes are being prepared.':'Framing and text preview · export an MP4 to see the finished clip.';
  }
  function updatePreview(){
    player.style.objectFit=$('social-framing').value==='fit'?'contain':'cover';
    player.style.objectPosition=`${$('social-x').value}% ${$('social-y').value}%`;
    const {start,duration}=bounds();
    const elapsed=Math.max(0,Math.min(duration,(Number((currentSource()?player:songPlayer).currentTime)||0)-start));
    $('social-preview-clock').textContent=`${time(elapsed)} / ${time(duration)}`;
    const hook=$('social-hook').value.trim(),cta=$('social-cta').value.trim();
    $('social-hook-preview').textContent=hook;$('social-cta-preview').textContent=cta;
    $('social-hook-preview').hidden=!currentSource()||!hook||elapsed>=3;
    $('social-cta-preview').hidden=!currentSource()||!cta||elapsed<Math.max(0,duration-5);
    const source=mode==='song'?state.social?.song:state.social?.video;
    $('social-range').textContent=source?`${time(start)} → ${time(start+duration)} · source ${time(source.duration)}${start+duration>source.duration+.05?' · Shorten the clip or move the start time back.':''}`:'Choose media to set your clip.';
    $('social-x').disabled=state.busy||$('social-framing').value==='fit';$('social-y').disabled=$('social-x').disabled;
  }
  function planMatches(){
    const social=state.social||{}, plan=social.plan, values=settings();
    return !!plan&&plan.start===values.start&&plan.duration===values.duration&&plan.prompt===values.prompt&&plan.style===values.style&&(plan.reference_path||null)===(social.photo?.path||null);
  }
  function render(next,restoring){
    const social=next.social||{};
    if(restoring){
      const saved=next.ui?.social||{};
      fieldIds.forEach(key=>{if(saved[key]!==undefined)$('social-'+key).value=saved[key];});
      setMode(saved.mode);show(saved.tab);
    }
    const song=social.song, source=social.video;
    if(song?.url!==lastSong){lastSong=song?.url||'';if(song){songPlayer.src=song.url;if(!restoring)$('social-start').value='0';}else songPlayer.removeAttribute('src');}
    if(source?.url!==lastVideo){lastVideo=source?.url||'';if(!restoring&&mode==='video')$('social-start').value='0';}
    $('social-video-name').textContent=source?.name||'Choose finished video';
    $('social-song-name').textContent=song?.name||'Choose your song';
    $('social-photo-name').textContent=social.photo?`Character reference: ${social.photo.name}`:'Without a reference, scenes follow your prompt.';
    syncSource();
    document.querySelectorAll('#social-workspace input,#social-workspace select,#social-workspace textarea').forEach(el=>el.disabled=!ready||next.busy);
    $('social-use-final').disabled=!ready||next.busy||next.final_export?.status!=='completed';
    $('social-create-plan').disabled=!ready||next.busy||!song;
    const matches=planMatches();
    $('social-generate').disabled=!ready||next.busy||!social.board||!matches;
    $('social-refresh').disabled=!ready||next.busy||!social.board;
    $('social-export').disabled=!ready||next.busy||!currentSource()||(mode==='song'&&!matches);
    $('social-open-export').disabled=!ready||next.busy||!social.export;
    $('social-preview').disabled=!ready||next.busy||!(currentSource()||song&&mode==='song');
    $('social-toggle-play').disabled=!ready||next.busy||!currentSource();
    $('social-export-detail').textContent=social.export?`Saved: ${social.export.path}`:'Choose a save location when you export.';
    $('social-plan-detail').textContent=social.plan?`${social.board.scene_count} scenes · ${time(social.plan.start)} song start · ${social.plan.duration}s${matches?' · Ready for generation.':' · Settings changed. Create a new plan to apply them.'}`:'Your plan will appear below before any generation is submitted.';
    const entries=Object.values(social.tracking?.scenes||{});
    $('social-tracking').textContent=social.board?`${Object.keys(social.clips||{}).length} / ${social.board.scene_count} clips imported · ${entries.filter(e=>e.status==='submitted').length} rendering · ${entries.filter(e=>['failed','submission_unknown'].includes(e.status)).length} need review`:'No social scenes yet.';
    const signature=JSON.stringify(social.board);
    if(signature!==planSignature){
      planSignature=signature;const container=$('social-scenes');container.replaceChildren();
      for(const scene of social.board?.scenes||[]){
        const details=document.createElement('details'),summary=document.createElement('summary'),image=document.createElement('p'),motion=document.createElement('p');
        summary.textContent=`Scene ${scene.scene_number} · ${scene.duration}s`;
        image.textContent=scene.image_prompt;motion.textContent=scene.video_audio_prompt;
        details.append(summary,image,motion);container.append(details);
      }
    }
    updatePreview();
  }
  async function preview(){
    const source=currentSource(),{start,duration}=bounds();
    const target=source?player:songPlayer;
    if(!source&&!(mode==='song'&&state.social?.song)){showError('Choose media to preview first.');return;}
    try{target.currentTime=start;await target.play();}catch(error){showError('This file cannot be previewed in the desktop browser. Try an H.264 MP4 or MP3/WAV song.');}
    updatePreview();
  }
  $('social-nav').onclick=()=>{show('social');scheduleWorkspace();};
  $('social-mode-video').onclick=()=>{setMode('video');render(state,false);};$('social-mode-song').onclick=()=>{setMode('song');render(state,false);};
  $('social-pick-video').onclick=()=>call('choose_social_media','video');
  $('social-use-final').onclick=()=>call('use_final_video_for_social');
  $('social-pick-song').onclick=()=>call('choose_social_media','song');
  $('social-pick-photo').onclick=()=>call('choose_social_media','photo');
  $('social-preview').onclick=preview;
  $('social-toggle-play').onclick=()=>{if(player.paused)preview();else player.pause();};
  player.addEventListener('loadedmetadata',()=>{player.currentTime=bounds().start;updatePreview();});
  player.addEventListener('timeupdate',()=>{const b=bounds();if(player.currentTime>=b.start+b.duration){player.pause();}updatePreview();});
  songPlayer.addEventListener('timeupdate',()=>{const start=Number($('social-start').value)||0,duration=Number($('social-duration').value)||30;if(songPlayer.currentTime>=start+duration)songPlayer.pause();if(!currentSource())updatePreview();});
  $('social-preset').onchange=()=>{$('social-prompt').value=presets[$('social-preset').value]||'';render(state,false);};
  $('social-prompt').value=presets['Performance teaser'];
  document.querySelectorAll('#social-workspace input,#social-workspace select,#social-workspace textarea').forEach(el=>el.addEventListener('input',()=>render(state,false)));
  $('social-create-plan').onclick=()=>{if(state.social?.board&&!confirm('Create a new social plan? This replaces the current social scene assignments. Your music-video storyboard is kept.'))return;call('create_social_plan',settings(),$('social-prompt').value,$('social-style').value);};
  $('social-generate').onclick=()=>{if(confirm('Generate the planned vertical scenes in VideoExpress? This uses your account credits. Already tracked scenes are skipped.'))call('generate_social_scenes');};
  $('social-refresh').onclick=()=>call('refresh_social_clips');
  $('social-export').onclick=()=>call('export_social_video',settings());
  $('social-open-export').onclick=()=>call('open_social_export');
  return {capture,render,show};
})();
