"""Self-contained player for validated data; no scripts from sources or agents."""

import json
from html import escape

from .process_visualization import checked_process

PLAYER_SCRIPT = r"""
const data = JSON.parse(document.getElementById('process-data').textContent);
const colors = {control:'#3265a8',proposed:'#087f75',truth:'#c45b19',
                muted:'#b6c1cf',field:'#677587'};
const root = document.getElementById('player');
let index = 0, timer = null;
const slider = root.querySelector('input');
const play = root.querySelector('[data-play]');
const step = root.querySelector('[data-step]');
const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
root.querySelector('h1').textContent = data.title;
root.querySelector('[data-description]').textContent = data.description;
root.querySelector('[data-selection]').textContent = data.selection;
root.querySelector('[data-limits]').textContent = data.limitations;
root.querySelector('pre').textContent = JSON.stringify(
  {inputs:data.inputs,provenance:data.provenance},null,2);
slider.max = data.times.length-1;
slider.setAttribute('aria-label', data.timeline_label);
const worlds = ['original','proposed'].map(key => {
  const card = root.querySelector('[data-world='+key+']');
  card.querySelector('h2').textContent = data[key].label;
  card.querySelector('p').textContent = data[key].description;
  card.querySelector('canvas').setAttribute('aria-label',data[key].label+': '+data.description);
  return {world:data[key],card,ctx:card.querySelector('canvas').getContext('2d')};
});
function draw({world,card,ctx}) {
  const width=600,height=410,pad=44;
  const [x0,x1,y0,y1]=data.bounds;
  const sx=(width-pad*2)/(x1-x0),sy=(height-pad*2)/(y1-y0);
  const scale=Math.min(sx,sy);
  const xscale=data.independent_axes?sx:scale,yscale=data.independent_axes?sy:scale;
  const px=x => width/2+(x-(x0+x1)/2)*xscale;
  const py=y => height/2-(y-(y0+y1)/2)*yscale;
  ctx.clearRect(0,0,width,height);
  ctx.fillStyle='#f8fafc'; ctx.fillRect(0,0,width,height);
  ctx.save(); ctx.beginPath();ctx.rect(px(x0),py(y1),(x1-x0)*xscale,(y1-y0)*yscale);ctx.clip();
  function glyph(g) {
    if (g.start>index) return;
    const highlighted=g.highlight.includes(index);
    ctx.strokeStyle=colors[highlighted?'truth':g.color];
    ctx.fillStyle=ctx.strokeStyle;ctx.lineWidth=highlighted?2.5:1.5;
    ctx.beginPath();
    if (g.kind==='circle') {
      ctx.arc(px(g.x),py(g.y),Math.max(1,g.radius*scale)*(highlighted?1.6:1),0,2*Math.PI);
      g.filled ? ctx.fill() : ctx.stroke();
    } else {
      const ax=px(g.x),ay=py(g.y),bx=px(g.x2),by=py(g.y2);
      ctx.moveTo(ax,ay);ctx.lineTo(bx,by);ctx.stroke();
      if(g.kind==='arrow') {
        const angle=Math.atan2(by-ay,bx-ax),len=Math.min(5,Math.hypot(bx-ax,by-ay)*.35);
        ctx.beginPath();ctx.moveTo(bx,by);
        ctx.lineTo(bx-len*Math.cos(angle-.5),by-len*Math.sin(angle-.5));
        ctx.lineTo(bx-len*Math.cos(angle+.5),by-len*Math.sin(angle+.5));ctx.closePath();ctx.fill();
      }
    }
  }
  world.geometry.forEach(glyph);world.frames[index].glyphs.forEach(glyph);
  ctx.restore();ctx.strokeStyle='#b6c1cf';ctx.lineWidth=1;
  ctx.strokeRect(px(x0),py(y1),(x1-x0)*xscale,(y1-y0)*yscale);
  ctx.fillStyle='#334155';ctx.font='13px system-ui';ctx.textAlign='center';
  ctx.fillText(data.x_label,width/2,height-9);
  ctx.fillText(x0.toPrecision(3),px(x0),py(y0)+17);
  ctx.fillText(x1.toPrecision(3),px(x1),py(y0)+17);
  ctx.textAlign='left';ctx.fillText(data.y_label,12,18);
  ctx.fillText(y1.toPrecision(3),4,py(y1)+14);
  ctx.fillText(y0.toPrecision(3),4,py(y0));
  card.querySelector('[data-caption]').textContent=world.frames[index].caption;
}
function render() {
  slider.value=index;
  step.textContent=data.timeline_label+': '+Number(data.times[index].toFixed(3))+
    ' · frame '+(index+1)+' / '+data.times.length;
  worlds.forEach(draw);
}
function pause() {
  clearInterval(timer);timer=null;play.textContent=index===data.times.length-1?'Replay':'Play';
}
function start() {
  if(index===data.times.length-1) index=0;
  play.textContent='Pause';render();
  timer=setInterval(()=>{index++;render();if(index===data.times.length-1)pause();},160);
}
play.addEventListener('click',()=>timer ? pause() : start());
root.querySelector('[data-reset]').addEventListener('click',()=>{pause();index=0;render();play.textContent='Play';});
slider.addEventListener('input',()=>{pause();index=Number(slider.value);render();});
document.addEventListener('visibilitychange',()=>{if(document.hidden)pause();});
window.addEventListener('pagehide',pause);
render();if(!reduced)start();
"""


def process_html(process, *, scalar_axes=False):
    process = checked_process(process)
    payload = json.dumps(
        {**process, "independent_axes": scalar_axes}, allow_nan=False, separators=(",", ":")
    )
    payload = payload.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    cards = "".join(
        f'<section data-world="{key}"><h2></h2><p></p>'
        '<canvas width="600" height="410" role="img"></canvas>'
        "<p data-caption></p></section>"
        for key in ("original", "proposed")
    )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{escape(process['title'])}</title><style>"
        "body{margin:0;padding:16px;font:15px/1.5 system-ui;color:#172b42;background:white}"
        "h1{font-size:22px;margin:0 0 8px}h2{font-size:18px;margin:0}p{margin:8px 0}"
        ".worlds{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin:18px 0}"
        "section{min-width:0;border:1px solid #d8e0e8;border-radius:10px;padding:12px}"
        "section>p{font-size:13px}canvas{width:100%;height:auto;display:block}"
        ".controls{display:flex;align-items:center;gap:12px;flex-wrap:wrap}"
        "button{font:inherit;padding:6px 16px;cursor:pointer}input{flex:1;min-width:100px}"
        "[data-step]{display:block;font-size:13px}details{margin-top:12px}"
        "pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:280px;overflow:auto}"
        ".note{font-size:13px;color:#42566f}"
        "@media(max-width:600px){.worlds{grid-template-columns:1fr}}"
        '</style></head><body><main id="player"><h1></h1><p data-description></p>'
        '<div class="controls"><button data-play>Play</button><button data-reset>Reset</button>'
        '<input type="range" min="0" value="0" step="1"></div><output data-step></output>'
        f'<div class="worlds">{cards}</div><p class="note" data-selection></p>'
        '<p class="note" data-limits></p><details><summary>Recorded inputs and provenance</summary>'
        "<pre></pre></details><noscript>Enable JavaScript to play the saved simulation states. "
        "The companion process.json contains all states and provenance.</noscript></main>"
        f'<script type="application/json" id="process-data">{payload}</script>'
        f"<script>{PLAYER_SCRIPT}</script></body></html>"
    )
