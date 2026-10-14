"""SmartMic TF220: mobile operator web analyzer. PTFE calibrated nominal 0.793 L/main stroke."""
import asyncio, os, secrets, tempfile, subprocess
from pathlib import Path
import numpy as np
from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.responses import HTMLResponse
from scipy.signal import butter, sosfiltfilt, find_peaks, correlate
from scipy.ndimage import gaussian_filter1d
app = FastAPI(docs_url=None, redoc_url=None)
STROKE_L = 0.793
ACCESS_CODE = os.environ.get("ACCESS_CODE", "")
MAX_MB = 65
UI = """<!doctype html><html lang="sk"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#123a52"><title>SmartMic TF220</title>
<style>body{background:#f2f6f8;font:16px system-ui,Arial;color:#16394b;margin:0}.wrap{max-width:550px;margin:auto;padding:20px}header{background:#123a52;color:white;padding:20px;border-radius:16px;margin-bottom:20px}h1{margin:5px 0;font-size:28px}small{opacity:.8}section{background:white;border-radius:16px;padding:20px;margin:15px 0;box-shadow:0 3px 16px #162d4012}label{display:block;font-weight:600;margin:14px 0}input{display:block;width:100%;box-sizing:border-box;padding:13px;border:1px solid #b7c6cd;border-radius:10px;font:inherit;margin-top:7px}button{width:100%;background:#0b6776;color:white;padding:16px;border:0;border-radius:11px;font:inherit;font-weight:700;margin-top:10px}button:disabled{opacity:.6}.big{font-size:42px;font-weight:800;color:#0b6776}.muted{color:#52656e}#result{display:none}.warn{background:#fff3d8;padding:13px;border-radius:10px}.err{color:#b31919;white-space:pre-wrap}</style>
<div class="wrap"><header><div>HOFITECH · SmartMic</div><h1>TF220 Flow Analyzer</h1><small>PTFE · 0,793 l / hlavný takt</small></header><section><h2>Analyzovať nahrávku</h2><p class="muted">Nahraj 20–30 sekúnd videa čerpadla. Zvuk automaticky analyzuje server.</p><form id="f"><label>Video alebo audio<input required type="file" name="video" accept="video/*,audio/*,.mp4,.mov,.m4a,.wav"></label><label>Minúta filtrácie<input type="number" name="minute" min="0" step="0.5" inputmode="decimal" placeholder="napr. 29"></label><label>Prístupový kód<input type="password" name="access_code" required autocomplete="off"></label><label>Tlak vody (bar), voliteľné<input type="number" name="pressure_water" min="0" max="30" step="0.1" inputmode="decimal"></label><button id="b">Analyzovať</button></form><p id="error" class="err"></p></section><section id="result"><h2>Výsledok</h2><div class="big" id="q">–</div><p id="info"></p><p id="press"></p><p id="confidence" class="warn"></p><p class="muted">Nominálny akustický prietok. Hodnota sama osebe nie je pokynom zastaviť lis.</p></section></div>
<script>document.getElementById('f').onsubmit=async e=>{e.preventDefault();const f=e.target,b=document.getElementById('b'),err=document.getElementById('error');err.textContent='';b.disabled=true;b.textContent='Analyzujem…';try{let r=await fetch('/api/analyze',{method:'POST',body:new FormData(f)});let x=await r.json();if(!r.ok)throw Error(x.detail||'Chyba');document.getElementById('result').style.display='block';document.getElementById('q').textContent=x.nominal_flow_lpm.toFixed(1).replace('.',',')+' l/min';document.getElementById('info').textContent='Hlavný takt '+x.main_period_s.toFixed(2)+' s · '+x.strokes_per_min.toFixed(1)+' taktov/min';document.getElementById('press').textContent=x.pressure_water_bar==null?'Tlak vody nezadaný':'Tlak vody '+x.pressure_water_bar+' bar · P/Q '+x.resistance_index.toFixed(3);document.getElementById('confidence').textContent='Spoľahlivosť: '+x.confidence+' · '+x.message;document.getElementById('result').scrollIntoView({behavior:'smooth'});}catch(ex){err.textContent=ex.message;}finally{b.disabled=false;b.textContent='Analyzovať'}};</script></html>"""
@app.get("/",response_class=HTMLResponse)
def home(): return UI
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
@app.post("/api/analyze")
async def analyze(video:UploadFile=File(...), minute:float|None=Form(None), access_code:str=Form(""), pressure_water:float|None=Form(None)):
    if not ACCESS_CODE: raise HTTPException(503,"Server ešte nemá nastavený prístupový kód.")
    if not secrets.compare_digest(access_code,ACCESS_CODE): raise HTTPException(403,"Nesprávny prístupový kód.")
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
