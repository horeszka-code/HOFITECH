"""Exact portable implementation of S10-30 methodology from HOFITECH operator workbook.
Pilot diagnostic only. Output must not be treated as independently validated safety limit.
"""
import math

GREEN_LIMIT=0.14
RED_LIMIT=0.18
P0_DEFAULT=0.0

def _fit(rows,p0):
    pmax=max(r["water_bar"] for r in rows)
    n=len(rows)
    candidates=[]
    for i in range(25):
        pinf=max(pmax,p0)+0.3+i*0.25
        ln_points=[]
        for r in rows:
            t,p=r["minute"],r["water_bar"]
            if t>0 and p>p0 and p<pinf:
                yy=math.log(-math.log(1-(p-p0)/(pinf-p0)))
                ln_points.append((math.log(t),yy))
        if len(ln_points)<3:continue
        xm=sum(z[0] for z in ln_points)/len(ln_points)
        ym=sum(z[1] for z in ln_points)/len(ln_points)
        denom=sum((x-xm)**2 for x,y in ln_points)
        if denom<1e-12:continue
        beta=sum((x-xm)*(y-ym) for x,y in ln_points)/denom
        if beta<=0:continue
        intercept=ym-beta*xm
        tau=math.exp(-intercept/beta)
        if not math.isfinite(tau) or tau<=0:continue
        loss=sum(
            (r["water_bar"]-(p0+(pinf-p0)*(1-math.exp(-((r["minute"]/tau)**beta)))))**2
            for r in rows if r["minute"]>0
        )
        rmse=math.sqrt(loss/max(1,n-1))
        s10=(pinf-p0)*beta/tau*(10/tau)**(beta-1)*math.exp(-(10/tau)**beta)
        candidates.append(dict(p_inf=pinf,beta=beta,tau=tau,s10=s10,rmse=rmse,sse=loss))
    return min(candidates,key=lambda x:x["sse"]) if candidates else None

def diagnose(samples,ec_complete=None,mixing_on=None):
    cleaned=[]
    for p in samples:
        try:
            t=float(p["minute"]);water=float(p["water_bar"])
            air=p.get("air_bar")
            air=float(air) if air is not None else None
            if not all(map(math.isfinite,[t,water]+([air] if air is not None else []))):continue
            if t<0 or t>240 or water<0 or water>30:continue
            cleaned.append(dict(minute=t,water_bar=water,air_bar=air))
        except (KeyError,TypeError,ValueError):continue
    early=sorted([p for p in cleaned if p["minute"]<=30],key=lambda p:p["minute"])
    # Deduplicate time: newest reading wins, otherwise stale repeated time corrupts linear fit.
    dedup={}
    for p in early:dedup[p["minute"]]=p
    early=list(dedup.values())
    count=len(early)
    last=max((x["minute"] for x in early),default=None)
    air=[x["air_bar"] for x in early if x["air_bar"] is not None]
    delta_air=max(air)-min(air) if len(air)>=2 else None
    p0=next((x["water_bar"] for x in early if x["minute"]==0),P0_DEFAULT)
    p0_assumed=not any(x["minute"]==0 for x in early)
    out={"reference":"SmartMic_S10_30min_Operator_Dashboard_OPRAVENY",
         "measurement_count":count,"last_early_minute":last,"p0_assumed":p0_assumed,
         "delta_air_bar":delta_air,"limits":{"green_below":GREEN_LIMIT,"red_from":RED_LIMIT},
         "status":"WAIT","semaphore":"ČAKÁ NA DÁTA","s10":None,"fit":None,
         "warnings":["Pilotná diagnostika, nie bezpečnostná hranica."] }
    if count<4:
        out["message"]="Pridaj tlakové merania: na index S10 sú potrebné aspoň 4 body."
        return out
    if last is None or last<20:
        out["message"]="Predikcia ešte nie je platná: čakaj na meranie aspoň v 20. minúte."
        return out
    # Distinct from workbook: keep future measurements out of the early window,
    # but warn rather than silently fit them.
    fit=_fit(early,p0)
    if fit is None:
        out["message"]="Weibullov fit nie je dostupný. Skontroluj merania."
        return out
    out.update(s10=round(fit["s10"],6),fit={k:round(v,5) for k,v in fit.items() if k!="s10"},
               semaphore=("ZELENÉ" if fit["s10"]<GREEN_LIMIT else "ORANŽOVÉ" if fit["s10"]<RED_LIMIT else "ČERVENÉ"))
    issues=[]
    if fit["rmse"]>0.5:issues.append("SLABÝ FIT (RMSE > 0,5 bar)")
    if delta_air is not None and delta_air>0.3:issues.append("ZMENA VZDUCHU (>0,3 bar)")
    if p0_assumed:issues.append("P0 PREDPOKLAD")
    if mixing_on is False:issues.append("VYPNUTÉ MIEŠANIE")
    if ec_complete is False:issues.append("NEDOKONČENÝ EC BLOK")
    out["warnings"]+=issues
    out["status"]="CAUTION" if issues else "PILOT"
    out["message"]=("Diagnostika obmedzená: "+", ".join(issues)+".") if issues else (
        "Pilotná predikcia úvodného tlakového nábehu. Sleduj ďalší tlak, prietok a miešanie.")
    # Operational recommendations, not direct stop/continue commands.
    if out["semaphore"]=="ZELENÉ":
        out["advice"]="Počiatočný rast tlaku je priaznivejší. Pokračuj v meraniach; nezaručuje dobrú koncovú filtráciu."
    elif out["semaphore"]=="ORANŽOVÉ":
        out["advice"]="Zvýšená pozornosť: priprav kontrolu filtračného koláča, miešania a trendu Q."
    else:
        out["advice"]="Rizikový počiatočný tlakový nábeh: prever zanášanie a priechodnosť; o prerušení rozhodni podľa tlaku, Q a technologických limitov."
    out["pressure_prediction_bar"]={str(t):round(p0+(fit["p_inf"]-p0)*(1-math.exp(-(t/fit["tau"])**fit["beta"])),2) for t in [20,25,30]}
    return out
