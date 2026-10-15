"""SmartMic TF220: mobile operator web analyzer. PTFE calibrated nominal 0.793 L/main stroke."""
import asyncio, os, secrets, tempfile, subprocess, hmac, hashlib, base64, time
from collections import defaultdict
from pathlib import Path
import numpy as np
from fastapi import FastAPI, File, Form, UploadFile, HTTPException, Request
from pydantic import BaseModel
from typing import Any
from fastapi.responses import HTMLResponse, Response, JSONResponse
import struct, zlib
from s10_model import diagnose
from scipy.signal import butter, sosfiltfilt, find_peaks, correlate
from scipy.ndimage import gaussian_filter1d
app = FastAPI(docs_url=None, redoc_url=None)
STROKE_L = 0.793
ACCESS_CODE = os.environ.get("ACCESS_CODE", "")
ACCESS_PIN = os.environ.get("ACCESS_PIN", "")
TOKEN_SECRET = os.environ.get("TOKEN_SECRET", "")
FAILURES = defaultdict(list)
COOKIE_NAME = "smartmic_session"
SESSION_DAYS = 180
MAX_MB = 65
UI = """<!doctype html><html lang="sk"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#123a52"><link rel="manifest" href="/manifest.webmanifest"><link rel="apple-touch-icon" href="/icon-192.png"><title>SmartMic TF220</title>
<style>body{background:#f2f6f8;font:16px system-ui,Arial;color:#16394b;margin:0}.wrap{max-width:550px;margin:auto;padding:20px} #accessGate{display:none} #analysisPanel{display:none} #s10card{display:none} .line{display:flex;justify-content:space-between;align-items:center;gap:10px;margin:9px 0}.sema{padding:13px;border-radius:10px;font-weight:800;text-align:center}.sema.green{background:#dff6e6;color:#135c35}.sema.amber{background:#fff0ca;color:#865300}.sema.red{background:#ffe0db;color:#902a25}.sema.gray{background:#ecf0f3;color:#53626a} .tiny{font-size:13px;color:#58707a}.secondarybtn{background:#345269;padding:12px}.history{font-size:13px;border-bottom:1px solid #dce5e9;padding:8px 0} header{background:#123a52;color:white;padding:20px;border-radius:16px;margin-bottom:20px}h1{margin:5px 0;font-size:28px}small{opacity:.8}section{background:white;border-radius:16px;padding:20px;margin:15px 0;box-shadow:0 3px 16px #162d4012}label{display:block;font-weight:600;margin:14px 0}input{display:block;width:100%;box-sizing:border-box;padding:13px;border:1px solid #b7c6cd;border-radius:10px;font:inherit;margin-top:7px}button{width:100%;background:#0b6776;color:white;padding:16px;border:0;border-radius:11px;font:inherit;font-weight:700;margin-top:10px}button:disabled{opacity:.6}.big{font-size:42px;font-weight:800;color:#0b6776}.muted{color:#52656e}#result{display:none}.warn{background:#fff3d8;padding:13px;border-radius:10px}.err{color:#b31919;white-space:pre-wrap}</style>
<div class="wrap"><header><div>HOFITECH · SmartMic</div><h1>TF220 Flow Analyzer</h1><small>PTFE · 0,793 l / hlavný takt</small></header><section id="accessGate"><h2>Prvé prihlásenie</h2><p class="muted">Zadaj 4-miestny PIN. Tento telefón si zapamätá prihlásenie na 180 dní.</p><form id="pinForm"><label>4-miestny PIN<input id="pin" type="password" inputmode="numeric" pattern="[0-9]{4}" maxlength="4" autocomplete="off" required></label><button id="pinButton">Prihlásiť sa</button></form><p id="pinError" class="err"></p></section><section id="analysisPanel"><h2>Analyzovať nahrávku</h2><p class="muted">Nahraj 20–30 sekúnd videa čerpadla. Zvuk automaticky analyzuje server.</p><form id="f"><label>Video alebo audio<input required type="file" name="video" accept="video/*,audio/*,.mp4,.mov,.m4a,.wav"></label><label>Minúta filtrácie<input type="number" name="minute" min="0" step="0.5" inputmode="decimal" placeholder="napr. 29"></label><label>Tlak vody (bar), voliteľné<input type="number" name="pressure_water" min="0" max="30" step="0.1" inputmode="decimal"></label><button id="b">Analyzovať</button></form><p id="error" class="err"></p></section><section id="result"><h2>Výsledok</h2><div class="big" id="q">–</div><p id="info"></p><p id="press"></p><p id="confidence" class="warn"></p><p class="muted">Nominálny akustický prietok. Hodnota sama osebe nie je pokynom zastaviť lis.</p></section><section id="s10card"><h2>Skorá diagnostika S₁₀ (0–30 min)</h2>
<p class="tiny">Pilotný semafor podľa Excelu HOFITECH. Nevyhodnocuje iba jednu nahrávku: potrebuje najmenej 4 merania tlaku, vrátane bodu po 20. minúte.</p>
<div id="semastatus" class="sema gray">ČAKÁ NA DÁTA</div><div class="line"><span>S₁₀-30</span><strong id="s10value">—</strong></div>
<div class="line"><span>Merania v úvodnom okne</span><strong id="pointcount">0</strong></div><div id="s10msg" class="tiny"></div><p id="forecast" class="tiny"></p>
<p id="s10advice"></p>
<div class="line"><span>Cyklus</span><input id="cycleId" value="CYKLUS 1" style="width:55%;margin:0;padding:7px"></div>
<label>Tlak vzduchu (bar), voliteľné<input id="airpressure" type="number" step="0.1" min="0" max="15" placeholder="napr. 3,5"></label>
<label>EC blok 3<select id="eccomplete" style="width:100%;padding:12px"><option value="true">Dokončený</option><option value="false">Nedokončený</option></select></label>
<label>Miešanie<select id="mixing" style="width:100%;padding:12px"><option value="true">Zapnuté</option><option value="false">Vypnuté</option></select></label>
<button type="button" class="secondarybtn" id="saveMeasurement">Uložiť aktuálnu minútu a tlak</button>
<button type="button" class="secondarybtn" id="refreshS10">Prepočítať semafor</button>
<div id="history" class="tiny"></div><button type="button" class="secondarybtn" id="newCycle">Začať nový cyklus</button>
<p class="tiny">Zelená &lt;0,140; oranžová 0,140–0,180; červená ≥0,180 bar/min. Pilotné hodnoty, nie validované bezpečnostné prahy. Pri zmene pneumatického tlaku alebo miešania sa spoľahlivosť predikcie znižuje.</p></section></div>
<script>document.getElementById('f').onsubmit=async e=>{e.preventDefault();const f=e.target,b=document.getElementById('b'),err=document.getElementById('error');err.textContent='';b.disabled=true;b.textContent='Analyzujem…';try{let r=await fetch('/api/analyze',{method:'POST',body:new FormData(f)});let x=await r.json();if(!r.ok){if(r.status===401){document.getElementById('accessGate').style.display='block';document.getElementById('analysisPanel').style.display='none';}throw Error(x.detail||'Chyba');}document.getElementById('result').style.display='block';document.getElementById('q').textContent=x.nominal_flow_lpm.toFixed(1).replace('.',',')+' l/min';document.getElementById('info').textContent='Hlavný takt '+x.main_period_s.toFixed(2)+' s · '+x.strokes_per_min.toFixed(1)+' taktov/min';document.getElementById('press').textContent=x.pressure_water_bar==null?'Tlak vody nezadaný':'Tlak vody '+x.pressure_water_bar+' bar · P/Q '+x.resistance_index.toFixed(3);document.getElementById('confidence').textContent='Spoľahlivosť: '+x.confidence+' · '+x.message;if(x.minute!==null&&x.pressure_water_bar!==null){storeMeasurement(x.minute,x.pressure_water_bar);await refreshS10();}document.getElementById('result').scrollIntoView({behavior:'smooth'});}catch(ex){err.textContent=ex.message;}finally{b.disabled=false;b.textContent='Analyzovať'}};</script><script>
async function checkLogin(){
 try{const r=await fetch('/api/session',{credentials:'same-origin',cache:'no-store'}),x=await r.json();
 const ok=r.ok&&x.authenticated;document.getElementById('accessGate').style.display=ok?'none':'block';
 document.getElementById('analysisPanel').style.display=ok?'block':'none';
 }catch(e){document.getElementById('pinError').textContent='Nepodarilo sa pripojiť k serveru.';document.getElementById('accessGate').style.display='block';}
}
document.getElementById('pinForm').onsubmit=async function(e){
 e.preventDefault();const b=document.getElementById('pinButton'),err=document.getElementById('pinError');err.textContent='';b.disabled=true;
 try{const p=document.getElementById('pin').value;
 const r=await fetch('/api/login',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({pin:p})});
 const x=await r.json();if(!r.ok)throw Error(x.detail||'Nesprávny PIN.');
 document.getElementById('pin').value='';await checkLogin();
 }catch(e){err.textContent=e.message;}finally{b.disabled=false;}
};checkLogin();
</script>
<script>
const storageKey=()=> 'smartmic_s10_'+(document.getElementById('cycleId').value||'CYKLUS 1');
function points(){try{const v=JSON.parse(localStorage.getItem(storageKey())||'[]');return Array.isArray(v)?v:[]}catch(e){return []}}
function storeMeasurement(t,p){
 if(!Number.isFinite(+t)||!Number.isFinite(+p)||+t<0||+p<0)return;
 let v=points();const airField=document.getElementById('airpressure').value;
 const item={minute:+t,water_bar:+p,air_bar:airField===''?null:+airField};
 v=v.filter(x=>x.minute!==item.minute);v.push(item);v.sort((a,b)=>a.minute-b.minute);
 localStorage.setItem(storageKey(),JSON.stringify(v.slice(-100)));
}
async function refreshS10(){
 const pts=points(),out=document.getElementById('semastatus');
 const history=document.getElementById('history');
 history.textContent=pts.length?'Uložené: '+pts.map(x=>x.minute+' min / '+x.water_bar+' bar').join(' · '):'Žiadne uložené merania. Prvé hodnoty doplň vyššie.';
 document.getElementById('pointcount').textContent=pts.filter(x=>x.minute<=30).length;
 try{
 const r=await fetch('/api/diagnose',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
 samples:pts,ec_complete:document.getElementById('eccomplete').value==='true',
 mixing_on:document.getElementById('mixing').value==='true'})});
 const x=await r.json();if(!r.ok)throw Error(x.detail||'Diagnostika nedostupná');
 out.textContent=x.semaphore;out.className='sema '+(x.semaphore==='ZELENÉ'?'green':x.semaphore==='ORANŽOVÉ'?'amber':x.semaphore==='ČERVENÉ'?'red':'gray');
 document.getElementById('s10value').textContent=x.s10===null?'—':x.s10.toFixed(3).replace('.',',')+' bar/min';
 document.getElementById('s10msg').textContent=x.message+(x.warnings&&x.warnings.length?' '+x.warnings.join('; '):'');
 document.getElementById('s10advice').textContent=x.advice||'';document.getElementById('forecast').textContent=x.pressure_prediction_bar?'Model tlaku pri 30. minúte: '+x.pressure_prediction_bar['30'].toFixed(2).replace('.',',')+' bar (iba orientačný Weibull fit; nie bezpečnostný limit).':'';
 }catch(e){out.textContent='DIAGNOSTIKA NEDOSTUPNÁ';out.className='sema gray';document.getElementById('s10msg').textContent=e.message;}
}
document.getElementById('saveMeasurement').onclick=()=>{
 const form=document.getElementById('f');
 const t=+form.elements.minute.value, p=+form.elements.pressure_water.value;
 if(form.elements.minute.value===''||form.elements.pressure_water.value===''){alert('Zadaj minútu a tlak vody.');return}
 storeMeasurement(t,p);refreshS10();
};
document.getElementById('refreshS10').onclick=refreshS10;
document.getElementById('cycleId').addEventListener('change',refreshS10);
document.getElementById('newCycle').onclick=()=>{
 const id=prompt('Názov nového cyklu:', 'CYKLUS '+new Date().toISOString().slice(0,10));
 if(id){document.getElementById('cycleId').value=id;refreshS10();}
};
document.getElementById('eccomplete').addEventListener('change',refreshS10);
document.getElementById('mixing').addEventListener('change',refreshS10);
document.getElementById('s10card').style.display='block';refreshS10();
</script>
<script>if("serviceWorker" in navigator){window.addEventListener("load",()=>navigator.serviceWorker.register("/sw.js").catch(()=>{}));}</script></html>"""

@app.get("/manifest.webmanifest")
def manifest():
    return JSONResponse({
        "id":"/","name":"SmartMic TF220 Flow Analyzer","short_name":"SmartMic TF220",
        "description":"HOFITECH acoustic flow analyzer for Tapflo TF220 PTFE pumps",
        "start_url":"/","scope":"/","display":"standalone",
        "background_color":"#f2f6f8","theme_color":"#123a52",
        "icons":[{"src":"/icon-192.png","sizes":"192x192","type":"image/png","purpose":"any maskable"},{"src":"/icon-512.png","sizes":"512x512","type":"image/png","purpose":"any maskable"}]
    },media_type="application/manifest+json")

@app.get("/sw.js")
def sw():
    return Response("""self.addEventListener('install',e=>self.skipWaiting());
self.addEventListener('activate',e=>e.waitUntil(self.clients.claim()));
self.addEventListener('fetch',e=>{if(e.request.method==='GET'&&e.request.mode==='navigate'){
 e.respondWith(fetch(e.request).catch(()=>new Response('SmartMic vyzaduje internetove pripojenie.',{status:503,headers:{'Content-Type':'text/plain; charset=utf-8'}})));
}});""",media_type="application/javascript",headers={"Cache-Control":"no-store"})

def png_icon(size):
    def chunk(typ,data):
        return struct.pack("!I",len(data))+typ+data+struct.pack("!I",zlib.crc32(typ+data)&0xffffffff)
    lines=[]
    for y in range(size):
        row=bytearray()
        for x in range(size):
            dx=x-size/2;dy=y-size/2
            if abs(dx)<size*.36 and abs(dy)<size*.36:
                # stylized central flowing waveform over teal panel
                h=size*.125
                active= abs(dy-0.11*size*np.sin((x/size)*13.0))<h*.52
                rgb=(78,211,209) if active else (12,104,120)
            else:
                rgb=(18,58,82)
            row.extend(rgb)
        lines.append(b"\\x00"+bytes(row))
    data=zlib.compress(b"".join(lines),9)
    return b"\\x89PNG\\r\\n\\x1a\\n"+chunk(b"IHDR",struct.pack("!2I5B",size,size,8,2,0,0,0))+chunk(b"IDAT",data)+chunk(b"IEND",b"")

@app.get("/icon-{size}.png")
def icon(size:int):
    if size not in (192,512): raise HTTPException(404)
    return Response(png_icon(size),media_type="image/png",headers={"Cache-Control":"public, max-age=86400"})

@app.get("/",response_class=HTMLResponse)
def home(): return UI

class PinPayload(BaseModel):
    pin: str

def session_ok(request:Request):
    token=request.cookies.get(COOKIE_NAME,"")
    try:
        ts,mac=token.split(".",1)
        timestamp=int(ts)
        if not TOKEN_SECRET or timestamp<time.time()-SESSION_DAYS*86400 or timestamp>time.time()+300:return False
        good=hmac.new(TOKEN_SECRET.encode(),ts.encode(),hashlib.sha256).hexdigest()
        return hmac.compare_digest(good,mac)
    except (ValueError,AttributeError):return False

@app.get("/api/session")
def get_session(request:Request):
    return {"authenticated":session_ok(request)}

@app.post("/api/login")
def login(payload:PinPayload,request:Request):
    if not ACCESS_PIN or len(ACCESS_PIN)!=4 or not ACCESS_PIN.isascii() or not ACCESS_PIN.isdigit() or not TOKEN_SECRET:
        raise HTTPException(503,"Autentifikácia ešte nie je nakonfigurovaná.")
    # Approximate in-memory guard; shared global cap also mitigates rotating-IP PIN guessing.
    now=time.monotonic()
    ip=request.client.host if request.client else "unknown"
    for key,limit in ((ip,5),("__global__",40)):
        FAILURES[key]=[x for x in FAILURES[key] if now-x<900]
        if len(FAILURES[key])>=limit:raise HTTPException(429,"Priveľa pokusov. Skús znova o 15 minút.")
    if len(payload.pin)!=4 or not hmac.compare_digest(payload.pin,ACCESS_PIN):
        FAILURES[ip].append(now);FAILURES["__global__"].append(now)
        raise HTTPException(403,"Nesprávny PIN.")
    FAILURES.pop(ip,None)
    ts=str(int(time.time()))
    digest=hmac.new(TOKEN_SECRET.encode(),ts.encode(),hashlib.sha256).hexdigest()
    response=JSONResponse({"authenticated":True})
    response.set_cookie(COOKIE_NAME,ts+"."+digest,max_age=SESSION_DAYS*86400,secure=True,httponly=True,samesite="lax",path="/")
    return response

@app.get("/health")
def health(): return {"status":"ok","protected":bool(ACCESS_CODE)}
def analyze_audio(path):
    p=subprocess.run(["ffmpeg","-nostdin","-hide_banner","-loglevel","error","-i",str(path),"-vn","-ac","1","-ar","8000","-f","f32le","-"],capture_output=True,timeout=70)
    if p.returncode or not p.stdout: raise ValueError("Video nemá použiteľný zvuk.")
    a=np.frombuffer(p.stdout,dtype="<f4").astype(np.float64)
    if len(a)<8000*10: raise ValueError("Nahraj aspoň 20–30 sekúnd zvuku.")
    if np.max(np.abs(a))<1e-8: raise ValueError("Zvuk nie je dostatočne počuteľný.")
    acfs=[]
    for lo,hi,w in [(70,400,.10),(400,1200,.15),(1000,2500,.40),(2500,3500,.35)]:
        filt=sosfiltfilt(butter(3,[lo,hi],btype="bandpass",fs=8000,output="sos"),a)
        env=np.sqrt(np.maximum(0,gaussian_filter1d(filt*filt,80)))[::80]
        env=np.maximum(env-np.quantile(env,.20),0)
        env=env-env.mean()
        c=correlate(env,env,method="fft",mode="full")[len(env)-1:]
        acfs.append((c/max(c[0],1e-12))*w)
    z=sum(acfs)
    peaks,_=find_peaks(z,distance=26,prominence=.04)
    peaks=[int(i) for i in peaks if 50<=i<=min(700,len(z)//3)]
    if not peaks: raise ValueError("Pracovný takt sa nepodarilo spoľahlivo určiť.")
    candidates=sorted(peaks,key=lambda i:z[i],reverse=True)
    best=candidates[0]
    for j in candidates[1:]:
        if 1.87<best/j<2.13 and z[j]>=0.62*z[best] and sum(c[j]/w>.08 for c,w in zip(acfs,[.10,.15,.40,.35]))>=3:
            best=j;break
    T=best/100.
    ambiguous=any(j!=best and z[j]>.8*z[best] and (abs(j/best-2)<.13 or abs(j/best-.5)<.1) for j in candidates[:6])
    confidence="nízka" if z[best]<.20 or ambiguous else "stredná" if z[best]<.55 else "vysoká"
    return {"main_period_s":T,"nominal_flow_lpm":60*STROKE_L/T,"strokes_per_min":60/T,"confidence":confidence,"autocorrelation_score":round(float(z[best]),3),"message":"Pri nejasnom signáli opakujte video." if confidence=="nízka" else "Kontrolujte trend, tlak a objem; pilotné meranie."}

class DiagnoseRequest(BaseModel):
    samples: list[dict[str,Any]]
    ec_complete: bool | None = None
    mixing_on: bool | None = None

@app.post("/api/diagnose")
def operator_diagnose(payload:DiagnoseRequest,request:Request):
    if not session_ok(request):
        raise HTTPException(401,"Najprv sa prihlás cez PIN.")
    if len(payload.samples)>100:
        raise HTTPException(422,"Príliš veľa meraní.")
    return diagnose(payload.samples,payload.ec_complete,payload.mixing_on)

@app.post("/api/analyze")
async def analyze(request:Request, video:UploadFile=File(...), minute:float|None=Form(None), pressure_water:float|None=Form(None)):
    if not session_ok(request): raise HTTPException(401,"Najskôr zadaj PIN.")
    ext=Path(video.filename or "").suffix.lower()
    if ext not in {".mp4",".mov",".m4a",".wav",".webm",".3gp",".mp3",".aac"}: raise HTTPException(415,"Nepodporovaný typ súboru.")
    with tempfile.TemporaryDirectory(prefix="smartmic_") as tmp:
        path=Path(tmp)/("input"+ext)
        n=0
        with path.open("wb") as f:
            while chunk:=await video.read(1024*1024):
                n+=len(chunk)
                if n>MAX_MB*1024*1024: raise HTTPException(413,"Súbor je priveľký (max. 65 MB).")
                f.write(chunk)
        try: result=await asyncio.wait_for(asyncio.to_thread(analyze_audio,path),90)
        except (ValueError,subprocess.TimeoutExpired) as ex: raise HTTPException(422,str(ex))
        except asyncio.TimeoutError: raise HTTPException(504,"Analýza trvala pridlho.")
    result["minute"]=minute
    result["pressure_water_bar"]=pressure_water
    result["resistance_index"]=round(pressure_water/result["nominal_flow_lpm"],4) if pressure_water is not None else None
    return result
