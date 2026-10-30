// npm install --no-save playwright@1.56.1; npx playwright install chromium
// Start the real app first. Requires ffmpeg/ffprobe.
const {chromium}=require('playwright');const fs=require('fs');const path=require('path');const {spawnSync}=require('child_process');
const repo=path.resolve(__dirname,'..'),raw=path.join(repo,'.demo-recording');fs.mkdirSync(raw,{recursive:true});
const rect=(x,y,w,h)=>[[x,y],[x+w,y],[x+w,y+h],[x,y+h],[x,y]];
const circle=(x,y,r)=>Array.from({length:17},(_,i)=>[x+r*Math.cos(i*Math.PI/8),y+r*Math.sin(i*Math.PI/8)]);
const strokes=[rect(392,180,240,190),[[512,180],[512,124]],circle(512,110,14),circle(462,260,26),circle(562,260,26),[[462,320],[562,320]],rect(352,390,320,300),rect(452,450,120,90),[[352,420],[262,560]],[[672,420],[762,560]],rect(392,690,80,150),rect(552,690,80,150)];
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--use-angle=swiftshader','--enable-unsafe-swiftshader']});
 const context=await browser.newContext({viewport:{width:1400,height:720},recordVideo:{dir:raw,size:{width:1400,height:720}}});
 const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(String(e)));
 await page.goto('http://127.0.0.1:7861');await page.waitForFunction(()=>document.querySelector('#status').textContent==='ready'||document.querySelector('#output').src);
 await page.locator('#seed').fill('1056993011');await page.locator('#seed').dispatchEvent('change');await page.locator('#size').fill('10');
 const box=await page.locator('#sketch-stage').boundingBox();const pt=([x,y])=>[box.x+x*box.width/1024,box.y+y*box.height/1024];
 await page.waitForTimeout(450);
 for(const stroke of strokes){await page.mouse.move(...pt(stroke[0]));await page.mouse.down();for(const point of stroke.slice(1))await page.mouse.move(...pt(point),{steps:2});await page.mouse.up();await page.waitForTimeout(100);}
 await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('preview'));await page.waitForTimeout(600);
 const clicked=Date.now();await page.locator('#make3d').click();
 await page.waitForFunction(()=>!document.querySelector('#download').hidden,{timeout:240000});
 const generation=(Date.now()-clicked)/1000;await page.mouse.move(1390,710);await page.waitForTimeout(4200);
 await page.screenshot({path:path.join(raw,'final.png')});const info=await page.locator('#mesh-info').innerText();console.log({generation,info,errors});
 if(errors.length||!info.includes('faces'))throw Error('Real mesh did not complete');
 const video=page.video();await context.close();const source=await video.path();await browser.close();
 const d=+JSON.parse(spawnSync('ffprobe',['-v','error','-show_entries','format=duration','-of','json',source],{encoding:'utf8'}).stdout).format.duration;
 // Keep actual drawing and actual rotating result; omit the long middle wait.
 const first=Math.min(4.5,Math.max(3,d-generation-5));
 const end=d-3.8;
 const filter=`[0:v]split[v1][v2];[v1]trim=start=0:end=${first},setpts=PTS-STARTPTS[a];[v2]trim=start=${end},setpts=PTS-STARTPTS[b];[a][b]concat=n=2:v=1:a=0,fps=12,scale=800:-1:flags=lanczos,drawtext=fontfile='C\\:/Windows/Fonts/arial.ttf':text='Actual RTX 3090 run - 3D generation wait omitted':x=12:y=h-23:fontsize=13:fontcolor=white:box=1:boxcolor=black@0.7,split[c][e];[c]palettegen=stats_mode=diff[p];[e][p]paletteuse=dither=sierra2_4a`;
 const result=spawnSync('ffmpeg',['-y','-i',source,'-filter_complex',filter,'-loop','0',path.join(repo,'media/demo.gif')],{encoding:'utf8'});if(result.status)throw Error(result.stderr.slice(-2000));
 fs.writeFileSync(path.join(repo,'media/DEMO.md'),`# Real Doodle2Part capture\n\nFresh Playwright recording of the actual CUDA application on an RTX 3090. A robot is drawn with mouse events; SD-Turbo produces the live preview; Make 3D runs real TRELLIS inference. The resulting mesh is displayed by the actual three.js viewer with Spin enabled. No mock generator or substituted output.\n\nThe ${generation.toFixed(2)}-second 3D wait is omitted from this short GIF, as the burned-in caption states. Raw video and final screenshot stay in ignored .demo-recording/. Seed: 1056993011; default prompt: a cute toy robot. Final app status: ${info}.\n`);
 console.log('GIF',fs.statSync(path.join(repo,'media/demo.gif')).size);
})().catch(e=>{console.error(e);process.exitCode=1});
