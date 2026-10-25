import type { Page } from '@playwright/test';

// API giả khác nguồn, dùng chung cho prototype và Companion thật; không gọi YouTube.
export interface FakeStats { created: number; destroyed: number; nativeSpace: number; cues: { videoId: string; startSeconds: number }[]; blocked: boolean; holdLoads?: boolean; heldLoads?: number; fail: (code: number) => void; nativeVolume: (value: number) => void; end: () => void }
const fakeScript = String.raw`
const stats=window.__ytFake={created:0,destroyed:0,nativeSpace:0,cues:[],blocked:false,active:null};
class Player {
 constructor(element,options) {
  const start=options.playerVars?.start;
  this.options=options; this.volume=60; this.muted=false; this.time=Number.isInteger(start)&&start>=0?start:0; this.duration=240; this.playing=false; this.dead=false;this.videoId=options.videoId;
  this.iframe=document.createElement('iframe');this.iframe.src='https://www.youtube.com/embed/'+options.videoId;
  element.replaceWith(this.iframe);stats.active=this;stats.created++;
  setTimeout(()=>{if(!this.dead)options.events.onReady({target:this});},20);
 }
 state(data) {this.playerState=data;this.playing=data===1;this.options.events.onStateChange({target:this,data});}
 cueVideoById(source) {stats.cues.push(source);this.videoId=source.videoId;this.time=source.startSeconds;this.iframe.dataset.videoId=source.videoId;this.state(5);}
 loadVideoById(source) {if(stats.holdLoads){stats.heldLoads=(stats.heldLoads||0)+1;this.state(1);return;}this.cueVideoById(source);this.playVideo();}
 getVideoUrl() {return 'https://www.youtube.com/watch?v='+this.videoId;}
 getPlayerState() {return this.playerState??-1;}
 playVideo() {if(stats.blocked)this.options.events.onAutoplayBlocked();else this.state(1);}
 pauseVideo() {this.state(2);}
 stopVideo() {this.playing=false;}
 seekTo(value) {this.time=value;}
 setVolume(value) {this.volume=value;}
 getVolume() {return this.volume;}
 mute() {this.muted=true;}
 unMute() {this.muted=false;}
 isMuted() {return this.muted;}
 getCurrentTime() {return this.time;}
 getDuration() {return this.duration;}
 getIframe() {return this.iframe;}
 destroy() {this.dead=true;this.iframe.remove();stats.destroyed++;}
}
stats.fail=code=>stats.active.options.events.onError({target:stats.active,data:code});
stats.nativeVolume=value=>{stats.active.volume=value;stats.active.muted=false;};
stats.end=()=>{stats.active.time=stats.active.duration;stats.active.state(0);};
window.addEventListener('message',event=>{
 const active=stats.active;
 if(!active||active.dead||event.origin!=='https://www.youtube.com'||event.source!==active.iframe.contentWindow)return;
 if(event.data==='fake-native-play')active.playVideo();
 if(event.data==='fake-native-space'){stats.nativeSpace++;active.playing?active.pauseVideo():active.playVideo();}
});
window.YT={Player};window.onYouTubeIframeAPIReady?.();
`;

export async function installApi(page: Page, options: { failFirst?: boolean; delay?: number } = {}) {
  let requests = 0;
  await page.route('https://www.youtube.com/iframe_api', async route => {
    requests++;
    if (options.failFirst && requests === 1) { await route.abort('failed'); return; }
    if (options.delay) await new Promise(resolve => setTimeout(resolve, options.delay));
    await route.fulfill({ contentType: 'application/javascript', body: fakeScript });
  });
  await page.route('https://www.youtube.com/embed/**', route => route.fulfill({ contentType: 'text/html; charset=utf-8', body: `<!doctype html><html lang="vi"><head><meta charset="UTF-8"></head><body style="margin:0;background:#202020;color:white;display:grid;place-items:center;height:100vh"><button aria-label="Phát trong YouTube giả" onclick="parent.postMessage('fake-native-play','*')">Phát YouTube · API giả</button><script>document.addEventListener('keydown',event=>{if(event.code==='Space'){event.preventDefault();parent.postMessage('fake-native-space','*');}})</script></body></html>` }));
  return () => requests;
}
export const stats = (page: Page) => page.evaluate(() => {
  const value = (window as unknown as { __ytFake: FakeStats }).__ytFake;
  return { created: value.created, destroyed: value.destroyed, nativeSpace: value.nativeSpace, cues: value.cues };
});

export const nativeVolume = (page: Page) => page.evaluate(() => {
  const player = (window as unknown as { __ytFake: { active: { volume: number; muted: boolean } } }).__ytFake.active;
  return player.muted ? 0 : player.volume;
});
