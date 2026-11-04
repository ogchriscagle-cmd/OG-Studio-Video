'use strict';
window.walkthrough=(()=>{
  const flows={
    music:{name:'Make a full music video',workspace:'music',steps:[
      ['pick-audio','Choose your song','Click Choose your track and select an MP3, WAV, FLAC, or M4A file. This is the soundtrack for your full music video.'],
      ['title','Name your project','Enter your project / song title and, optionally, your artist name. Use the same title when uploading and generating in VideoExpress.'],
      ['character','Add your character','Choose a reference photo. Review the automatic appearance draft and correct any clothing, hair, or accessory details.','The first appearance draft downloads a vision model and can take several minutes.'],
      ['world','Choose the look and create a storyboard','Choose a visual style, mood, lighting, location, camera movement, and frame. Add a story concept, then click Create storyboard.'],
      ['board','Review the scene prompts','Read the image direction and motion for each scene. Edit anything you want to change and click Save prompts.','The preview shows prompt cards until you import rendered video clips.'],
      ['account-login','Sign in to VideoExpress','Use Sign in & remember (or Reconnect account) and complete sign-in in the browser that opens. If you already have a saved session, try Check connection first.','The same saved account is used in both studios.'],
      ['upload','Upload the project media','Click Upload project media to upload your selected song and reference photo to your VideoExpress project folder. Check the reference photo name below.'],
      ['test-scene','Test a scene, then generate','Try Test first scene before Generate all scenes. You can also use Generate scene on an individual storyboard card.','Generation uses VideoExpress credits. Tracked submissions are skipped on retries.'],
      ['refresh-tracking','Import the finished clips','Click Refresh rendered clips to check for ready renders, then Auto-import all clips to download them into the app. Preview the clips with your song.','If clips are still rendering, wait and refresh again. Review errors in the status bar at the bottom.'],
      ['auto-assemble','Assemble and review the video','Once every scene is confirmed, click Assemble tracked clips to build the final project in VideoExpress. Use an empty editor timeline, then click View in VideoExpress to review.'],
      ['export-video','Export and download the MP4','Choose resolution and quality, then click Export & download video and select a folder. Watch progress at the bottom. Open downloaded video plays the saved MP4.','Resume export & download checks a pending render before submitting another one.'],
      ['save-project','Save your project for later','Click Save project to choose a .ogstudio.json file. Open / import reopens it later. The workspace also saves automatically when you close the app.','Keep the original media and the app’s local data folder available. Export storyboard saves prompts and tracking; Export & download video saves the finished MP4.'],
    ]},
    video:{name:'Make a social clip from a video',workspace:'social',mode:'video',steps:[
      ['social-pick-video','Choose your finished video','Choose an existing video file, or use Use downloaded music video if you already exported your full video in this app.','This workflow trims and exports on your computer.'],
      ['social-start','Pick the best moment','Enter the start time in seconds and a clip length from 3 to 60 seconds. The default is 30 seconds. Preview selected moment plays that section.','Keep the end of the clip within the source video’s duration.'],
      ['social-framing','Set the vertical framing','Use Fill the frame and adjust the horizontal and vertical sliders to keep your subject in view. Keep the full picture adds black bars instead.'],
      ['social-hook','Add your opening hook','Write a short opening message, such as “Wait for the chorus…”. It appears during the first 3 seconds. Leave the field empty to use no opening text.'],
      ['social-cta','Add a follow or subscribe message','Add a closing message, such as “Follow for more” or “Full video on my channel”. It appears during the last 5 seconds.'],
      ['social-platform','Choose where you’ll post','Choose YouTube Shorts, Instagram Reels, Facebook Reels, or TikTok. All four use the same vertical MP4 export.'],
      ['social-preview-frame','Review the preview','Play the selected moment and check the framing and text. Adjust the start time, clip length, or framing if needed.'],
      ['social-export','Export your social MP4','Click Export social MP4, choose a save location, and watch progress at the bottom. Open exported clip plays the saved file. Upload it through your chosen social platform.'],
      ['save-project','Save your settings','Save project keeps your social settings and media references so you can reopen them with Open / import. Keep your source video available.'],
    ]},
    song:{name:'Make a social clip from a song',workspace:'social',mode:'song',steps:[
      ['account-login','Sign in to VideoExpress','Use Sign in & remember (or Reconnect account) and complete sign-in in the browser. If a session is already saved, try Check connection first.','Song-based scene generation uses your VideoExpress account credits.'],
      ['social-pick-song','Choose a song','Select an MP3, WAV, FLAC, or M4A song. Use the audio player to find a chorus or another memorable moment.'],
      ['social-start','Choose your song segment','Enter the start time in seconds and a whole-number length from 3 to 60 seconds. Start with 30 seconds and use Preview selected moment to listen.'],
      ['social-prompt','Describe your short video','Choose a visual prompt preset, then edit the description to fit your idea. Select a visual style and, optionally, add a character reference photo.'],
      ['social-create-plan','Create and review the plan','Click Create short-video plan. Open each scene below to read its image and motion prompts. Change your description and create a new plan if you want a different result.','Creating the plan prepares your song excerpt and prompts locally.'],
      ['social-generate','Generate the scenes','When you’re happy with the plan, click Generate scenes and confirm the credit use. The app uploads the excerpt and optional reference photo to a separate VideoExpress folder.','Already tracked scenes are skipped on retries.'],
      ['social-refresh','Refresh and import the clips','When the renders are ready, click Refresh & import clips. The app downloads matched clips and combines them with your selected song excerpt.','If some clips are still rendering, wait and refresh again. Check the status bar for any error that needs attention.'],
      ['social-preview-frame','Preview and finish your clip','Review the generated video. Adjust framing if needed, add an opening hook and closing follow/subscribe message, and select your social platform.','If you change the song segment, visual prompt, style, or reference, create a new plan to apply those changes.'],
      ['social-export','Export the vertical MP4','Click Export social MP4 and select a save location. Open exported clip plays the finished file. Post it through your chosen social platform.'],
      ['save-project','Save and return later','Save project keeps the social plan, settings, and tracking. Open / import reopens the project, and the app also restores the last workspace after closing.','Keep the original media and the app’s local data folder so the saved references can be reopened.'],
    ]},
    save:{name:'Save, reopen, and find your exports',workspace:'music',steps:[
      ['save-project','Save a reusable project','Click Save project and choose a .ogstudio.json filename. It saves your settings, storyboard, and clip references. Future changes also save automatically.','Keep your original media and the app’s local data folder; project files reference them rather than embedding every media file.'],
      ['open-project','Reopen an existing project','Click Open / import and choose a saved .ogstudio.json project. You can also import an exported storyboard JSON file. If media moved, select it again at its new location.'],
      ['export','Choose the export you need','Export storyboard saves prompts and tracking. In Music video studio, Export & download video saves the final MP4. Social Clip Studio has its own Export social MP4 button.'],
      ['status','Follow progress and resolve errors','The bottom bar shows the current operation and any error. While rendering, wait and refresh clip tracking. If sign-in expired, use Sign in & remember again.','For a pending final export, use Resume export & download. Avoid submitting duplicate renders when the previous submission is uncertain.'],
    ]},
  };
  const chooser=document.createElement('dialog');chooser.id='walkthrough-chooser';
  chooser.setAttribute('aria-labelledby','walkthrough-title');
  chooser.innerHTML='<div class="guide-intro-heading"><p class="eyebrow accent">WELCOME TO OG STUDIO VIDEO</p><button id="guide-intro-close" class="quiet" aria-label="Close walkthrough choices">✕</button></div><h2 id="walkthrough-title">What would you like to make?</h2><p>Choose a walkthrough. Each step points to the control you need, and you can follow at your own pace.</p><div id="guide-choices"></div><p class="hint">You control each action. VideoExpress generation and rendering use your account allowances.</p>';
  document.body.append(chooser);
  const panel=document.createElement('section');panel.id='walkthrough-panel';panel.hidden=true;
  panel.setAttribute('role','region');panel.setAttribute('aria-labelledby','guide-step-title');
  panel.innerHTML='<div class="guide-top"><span id="guide-progress" class="eyebrow accent"></span><button id="guide-close" class="text-button" aria-label="Close walkthrough">✕</button></div><p id="guide-flow-name" class="hint"></p><h2 id="guide-step-title" tabindex="-1"></h2><p id="guide-step-text"></p><p id="guide-step-tip" class="guide-tip" hidden></p><div class="guide-location"><button id="guide-show" class="text-button accent">Show me ↗</button><span id="guide-target-note" class="hint"></span></div><div class="guide-actions"><button id="guide-back" class="quiet">Back</button><button id="guide-menu" class="quiet">All guides</button><button id="guide-next" class="primary">Next →</button></div>';
  document.body.append(panel);
  const help=document.createElement('button');help.id='how-to-use';help.className='quiet';help.textContent='? How to use';
  document.querySelector('.project-actions').prepend(help);
  for(const hero of document.querySelectorAll('.hero')){
    const start=document.createElement('button');start.className='quiet guide-start';start.textContent='New here? Start a walkthrough →';start.onclick=open;hero.append(start);
  }
  let active=null,index=0,target=null,returnFocus=null;
  function clearTarget(){if(target)target.classList.remove('walkthrough-target');target=null;}
  function close(){
    clearTarget();active=null;panel.hidden=true;document.body.classList.remove('walkthrough-open');
    const focus=returnFocus?.isConnected&&!returnFocus.disabled&&returnFocus.getClientRects().length?returnFocus:help;
    focus.focus({preventScroll:true});
  }
  function open(){returnFocus=document.activeElement;close();if(!chooser.open)chooser.showModal();render();}
  function point(){
    clearTarget();const step=flows[active]?.steps[index];if(!step)return;
    target=$(step[0]);
    if(step[0]==='board')target=target?.querySelector('.scene-card')||target;
    if(!target||!target.getClientRects().length){$('guide-target-note').textContent='Open the relevant studio to see this control.';return;}
    target.classList.add('walkthrough-target');
    const rect=target.getBoundingClientRect(),mainLeft=document.querySelector('main').getBoundingClientRect().left;
    panel.style.left=rect.left>window.innerWidth*.5?`${mainLeft+18}px`:'';
    panel.style.right=rect.left>window.innerWidth*.5?'auto':'';
    target.scrollIntoView({behavior:'smooth',block:'center'});
    $('guide-target-note').textContent=target.disabled?'This control becomes available when its earlier steps are complete.':'';
  }
  function show(){
    const flow=flows[active],step=flow.steps[index];
    $('guide-progress').textContent=`STEP ${index+1} OF ${flow.steps.length}`;
    $('guide-flow-name').textContent=flow.name;$('guide-step-title').textContent=step[1];
    $('guide-step-text').textContent=step[2];$('guide-step-tip').textContent=step[3]||'';$('guide-step-tip').hidden=!step[3];
    $('guide-next').textContent=index===flow.steps.length-1?'Finish guide ✓':'Next →';
    render();point();$('guide-step-title').focus({preventScroll:true});
  }
  function start(key){
    chooser.close();active=key;index=0;
    const flow=flows[key];window.socialStudio.show(flow.workspace);
    if(flow.mode){window.socialStudio.setMode(flow.mode);window.socialStudio.render(state,false);}
    panel.hidden=false;document.body.classList.add('walkthrough-open');show();scheduleWorkspace();
  }
  function render(){
    help.disabled=false;
    document.querySelectorAll('.guide-start,#walkthrough-chooser button,#walkthrough-panel button').forEach(b=>b.disabled=false);
    $('guide-back').disabled=index===0;
    if(active&&target)$('guide-target-note').textContent=target.disabled?'This control becomes available when its earlier steps are complete.':'';
  }
  for(const [key,flow] of Object.entries(flows)){
    const button=document.createElement('button');button.className='quiet';button.textContent=flow.name;button.onclick=()=>start(key);$('guide-choices').append(button);
  }
  help.onclick=open;$('guide-intro-close').onclick=()=>chooser.close();
  chooser.addEventListener('click',event=>{if(event.target===chooser){const r=chooser.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)chooser.close();}});
  $('guide-close').onclick=close;$('guide-menu').onclick=open;$('guide-show').onclick=point;
  $('guide-back').onclick=()=>{if(index>0){index--;show();}};
  $('guide-next').onclick=()=>{if(index===flows[active].steps.length-1)close();else{index++;show();}};
  document.addEventListener('keydown',event=>{if(event.key==='Escape'&&active)close();});
  document.querySelectorAll('.nav').forEach(button=>button.addEventListener('click',()=>{if(active)close();}));
  document.querySelectorAll('.social-modes button').forEach(button=>button.addEventListener('click',()=>{if(active)close();}));
  window.addEventListener('resize',()=>{if(active)point();});
  render();return {open,render};
})();
