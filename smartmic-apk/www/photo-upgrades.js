/* SmartMic Test Forms v0.3: offline photo picker, gallery archive and in-app preview. */
(() => {
  'use strict';
  let chosenInput = null, picker, viewer, objectURL = null, choosingFile = false;
  const app = () => window.SmartMicTest;
  const msg = (message, error = false) => {
    const el = document.getElementById('messages');
    if (el) { el.textContent = message; el.classList.toggle('error', error); }
  };
  const open = dlg => { if (typeof dlg.showModal === 'function') dlg.showModal(); else dlg.setAttribute('open',''); };
  const close = dlg => { if (dlg?.open) dlg.close(); };
  const safe = value => String(value || 'Test').replace(/[^a-zA-Z0-9_-]/g, '_').slice(0, 60);
  function setup() {
    const style = document.createElement('style');
    style.textContent = `
      dialog.sm-source:not([open]),dialog.sm-viewer:not([open]){display:none}
      dialog.sm-source{position:fixed;inset:auto 0 0;margin:0 auto;width:min(600px,100%);max-width:100%;border:0;border-radius:20px 20px 0 0;padding:24px 20px calc(24px + env(safe-area-inset-bottom));color:#162840;background:white;box-shadow:0 -8px 30px #0005}
      dialog.sm-source::backdrop{background:#101d34ab}
      .sm-source h2{font-size:22px;margin:0 0 8px}.sm-source p{color:#607286;margin:0 0 18px}
      .sm-source .sm-option{display:block;width:100%;text-align:left;background:#f6f9fb;border:1px solid #cbd8e3;border-radius:12px;min-height:59px;margin:10px 0;padding:15px;font-weight:750}
      .sm-source .sm-cancel{width:100%;padding:14px;background:none;border:0}
      dialog.sm-viewer{position:fixed;inset:0;margin:0;padding:0;width:100vw;height:100dvh;max-width:100vw;max-height:100dvh;background:#091321;color:white;border:0;overflow:hidden}
      dialog.sm-viewer::backdrop{background:#080e17ea}
      .sm-viewer-head{display:flex;align-items:center;gap:12px;background:#162437;padding:calc(10px + env(safe-area-inset-top)) 12px 12px;min-height:65px}
      .sm-viewer-back{background:#fff;color:#132840;border:0;border-radius:10px;padding:12px 16px;min-height:46px;font-weight:800;font-size:16px}
      .sm-viewer-title{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
      .sm-viewer-body{display:flex;align-items:center;justify-content:center;height:calc(100dvh - 81px - env(safe-area-inset-top));padding:8px}
      .sm-viewer-body img,.sm-viewer-body video{max-width:100%;max-height:100%;width:auto;height:auto;object-fit:contain}
    `;
    document.head.appendChild(style);
    picker = document.createElement('dialog');
    picker.className = 'sm-source';picker.id='smartmicPhotoSource';
    picker.innerHTML = `<h2>Pridať fotografiu</h2><p>Vyber zdroj fotografie pre tento test.</p>
      <button class="sm-option" type="button" data-source="camera">📷 Odfotiť fotoaparátom</button>
      <button class="sm-option" type="button" data-source="gallery">🖼️ Vybrať z galérie</button>
      <button class="sm-cancel" type="button" data-source="cancel">Zrušiť</button>`;
    document.body.appendChild(picker);
    picker.addEventListener('click', e => {
      const source=e.target.closest('[data-source]')?.dataset.source;
      if (!source) return;
      if (source==='cancel') { close(picker); chosenInput=null; return; }
      const input=chosenInput;if(!input) {close(picker);return}
      input.value='';input.dataset.photoSource=source;
      if(source==='camera')input.setAttribute('capture','environment');
      else input.removeAttribute('capture');
      close(picker);
      choosingFile=true;
      try{input.click()}finally{choosingFile=false}
    });
    picker.addEventListener('close',()=>{chosenInput=null});
    viewer=document.createElement('dialog');viewer.className='sm-viewer';viewer.id='smartmicMediaViewer';
    viewer.innerHTML=`<div class="sm-viewer-head"><button class="sm-viewer-back" type="button">← Späť k formuláru</button><strong class="sm-viewer-title"></strong></div><div class="sm-viewer-body"></div>`;
    document.body.appendChild(viewer);
    viewer.querySelector('.sm-viewer-back').addEventListener('click',()=>close(viewer));
    viewer.addEventListener('close',()=>{
      viewer.querySelector('.sm-viewer-body').replaceChildren();
      if(objectURL)URL.revokeObjectURL(objectURL);objectURL=null;
    });
    const form=document.getElementById('formContent');if(!form)return;
    form.addEventListener('click',e=>{
      const preview=e.target.closest('[data-preview]');
      if(preview){
        e.preventDefault();e.stopImmediatePropagation(); // block old window.open
        const id=preview.dataset.preview,slot=Number(preview.dataset.slot);
        const entry=app()?.state.media[id]?.[slot];if(!entry)return;
        const type=app()?.state.schema?.items?.find(i=>i.id===id)?.media?.type;
        const body=viewer.querySelector('.sm-viewer-body');body.replaceChildren();
        if(objectURL)URL.revokeObjectURL(objectURL);
        objectURL=URL.createObjectURL(entry.blob);
        const element=document.createElement(type==='video'?'video':'img');
        element.src=objectURL;
        if(type==='video'){element.controls=true;element.playsInline=true}
        else element.alt='Fotografia '+(slot+1);
        body.appendChild(element);
        viewer.querySelector('.sm-viewer-title').textContent=entry.fileName||'Záznam '+(slot+1);
        open(viewer);
        return;
      }
      const input=e.target.closest('label.media-slot')?.querySelector('input[data-file]');
      if(!input||choosingFile)return;
      const item=app()?.state.schema?.items?.find(i=>i.id===input.dataset.file);
      if(item?.media?.type!=='photo')return;
      e.preventDefault();e.stopImmediatePropagation();
      chosenInput=input;open(picker);
    },true);
    form.addEventListener('change',e=>{
      const input=e.target;if(!input.matches('input[data-file]'))return;
      const id=input.dataset.file,slot=Number(input.dataset.slot);
      const item=app()?.state.schema?.items?.find(i=>i.id===id);
      if(item?.media?.type!=='photo')return; // video behavior unchanged
      e.stopImmediatePropagation(); // prevent old handler processing twice
      const file=input.files?.[0];if(!file)return;
      Promise.resolve().then(async()=>{
        await window.mediaChanged(e);
        await window.persist(); // protect draft BEFORE writing to Gallery
        let blob=file,mime=(file.type||'').toLowerCase();
        try{
          if(!['image/jpeg','image/png','image/webp','image/heic','image/heif'].includes(mime)){
            blob=(await window.jpegFromFile(file)).blob;mime='image/jpeg';
          }
          if(!window.SmartMicNative)throw Error('Natívne Android úložisko nie je dostupné');
          const ext={'image/jpeg':'jpg','image/png':'png','image/webp':'webp','image/heic':'heic','image/heif':'heif'}[mime];
          const date=new Date().toISOString().replace(/[-:.TZ]/g,'');
          const test=safe(app().state.schema?.testId);
          const name=`SmartMic_${test}_${date}_${slot+1}_${Math.random().toString(36).slice(2,9)}.${ext}`;
          await window.nativeTransfer(blob,name,mime);
          const entry=app().state.media[id]?.[slot];
          if(entry?.blob===file){entry.gallerySaved=true;window.scheduleSave?.()}
          msg('Fotografia je vo formulári aj v Galérii (Obrázky/SmartMic).');
        }catch(error){
          console.warn('SmartMic gallery write failed',error);
          msg('Fotografia je bezpečne vo formulári, ale uloženie do Galérie zlyhalo: '+(error?.message||error),true);
        }
      }).catch(error=>{console.error(error);msg('Spracovanie fotografie zlyhalo: '+error.message,true)});
    },true);
  }
  document.addEventListener('DOMContentLoaded',setup);
})();