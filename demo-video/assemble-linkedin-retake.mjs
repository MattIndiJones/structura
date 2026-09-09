// Public cut from existing rendered segments. Original recordings remain intact.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';
import { chromium } from 'playwright';
const root=path.dirname(fileURLToPath(import.meta.url));
const out=path.join(root,'build','linkedin-retake'); fs.mkdirSync(out,{recursive:true});
const ff=a=>execFileSync('ffmpeg',['-y','-v','error',...a],{stdio:'inherit'});
const browser=await chromium.launch();
const page=await browser.newPage({viewport:{width:1920,height:1080}});
for(const [name,text] of Object.entries({standard:'ILLUSTRATIVE DEMONSTRATION  ·  Selected implementation details masked',pricing:'ILLUSTRATIVE DEMONSTRATION  ·  Coupon adjusted to 9% for pricing  ·  Model-dependent outputs'})){
 await page.setContent(`<style>html,body{margin:0;background:transparent}div{height:58px;box-sizing:border-box;background:#0c192f;color:#d7e3f4;display:flex;align-items:center;justify-content:center;font:23px 'Segoe UI',sans-serif;letter-spacing:.3px}</style><div>${text}</div>`);
 await page.screenshot({path:path.join(out,name+'.png'),omitBackground:true});
}
// Fully opaque replacement panels: no source-script pixels are composited.
const panel=(x,y,w,h,label=true)=>`<section style="left:${x}px;top:${y}px;width:${w}px;height:${h}px;${label?'':'background:#7d7d79;border:0;'}"><div>${label?'Proprietary product script<span>Hidden in this public demonstration</span>':''}</div></section>`;
for(const id of [3,4,5,6,7,8,9]){
 let panels='';
 if(id===3) panels=panel(16,226,395,355,false)+panel(411,226,538,103,false);
 if(id===4) panels=panel(16,226,395,355,false)+panel(433,438,521,280);
 if(id>=5) panels=panel(18,280,922,368);
 if(id===9) panels+=panel(988,389,900,445);
 await page.setContent(`<style>html,body{margin:0;background:transparent}section{position:absolute;box-sizing:border-box;background:#f1f4f8;border:1px solid #dce3ec;display:flex;align-items:center;justify-content:center;color:#53657b;font:24px 'Segoe UI',sans-serif;text-align:center}span{display:block;font-size:17px;color:#79889b;margin-top:12px}</style>${panels}`);
 await page.screenshot({path:path.join(out,`mask-${id}.png`),omitBackground:true});
}
await browser.close();
const plan=[
 {id:0,speed:1.5}, {id:1,speed:1.35},
 // Skip the empty-editor setup; enter on the product description.
 {id:3,speed:1,blur:[[430,580,405,65]]},
 {id:4,speed:1,blur:[[430,320,405,65],[430,720,330,24]]},
 {id:5,speed:1,pricing:true},
 {id:6,speed:1.4,pricing:true},
 {id:7,speed:1,pricing:true},
 {id:8,speed:1,pricing:true},
 {id:9,speed:1.15,pricing:true,blur:[[1310,1007,365,35]]},
 {id:10,speed:1.6}
];
const parts=[];
for(const [n,s] of plan.entries()){
 const input=path.join(root,'build','retake','seg',String(s.id).padStart(2,'0')+'.mp4');
 let filter=`[0:v]setpts=(PTS-STARTPTS)/${s.speed},fps=30[v0];`,last='v0';
 for(const [j,[x,y,w,h]] of (s.blur||[]).entries()){
  filter+=`[${last}]split[b${j}][c${j}];[c${j}]crop=${w}:${h}:${x}:${y},gblur=sigma=22:steps=3[d${j}];[b${j}][d${j}]overlay=${x}:${y}[v${j+1}];`;last=`v${j+1}`;
 }
 const args=['-i',input];
 if(s.id>=3&&s.id<=9){args.push('-i',path.join(out,(s.pricing?'pricing':'standard')+'.png'),'-i',path.join(out,`mask-${s.id}.png`));filter+=`[${last}][1:v]overlay=0:0[vhead];[vhead][2:v]overlay=0:0[vmask];`;last='vmask';}
 filter+=`[${last}]setsar=1,format=yuv420p[final]`;
 const dest=path.join(out,`${n}.mp4`);
 ff([...args,'-filter_complex',filter,'-map','[final]','-an','-c:v','libx264','-preset','medium','-crf','18','-r','30',dest]);
 parts.push(dest);console.log('Rendered',s.id);
}
const list=path.join(out,'concat.txt');fs.writeFileSync(list,parts.map(p=>`file '${p.replaceAll('\\','/')}'`).join('\n'));
const final=path.join(root,'structura-ai-demo-linkedin-v4.mp4');
ff(['-f','concat','-safe','0','-i',list,'-c','copy','-movflags','+faststart',final]);
console.log(final);
