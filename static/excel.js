'use strict';
/* Dedicated editable-workbook workflow. Reports never enter legacy import. */
(function () {
 function optionsFrom(values) {
  const year=Number(values.year);
  if(!Number.isInteger(year)||year<1||year>9999)throw Error('Choose a planning year between 1 and 9999.');
  if(!/^\d{4}-(0[1-9]|1[0-2])$/.test(values.reference_month||''))throw Error('Choose a reporting reference month in YYYY-MM format.');
  return {year,inspection_type:values.inspection_type||'',area:values.area||'',family:values.family||'',tag:values.tag||'',source_sheet:values.source_sheet||'',reference_month:values.reference_month,include_overdue:!!values.include_overdue,include_unscheduled:!!values.include_unscheduled,monthly_sheets:!!values.monthly_sheets,include_summary:!!values.include_summary};
 }
 function resolutionsFrom(conflicts,choices) {
  const result={};
  for(const conflict of conflicts){const value=choices[conflict.key];if(!value||!['excel','app','manual'].includes(value.choice))throw Error('Choose a resolution for every conflict.');result[conflict.key]={choice:value.choice};if(value.choice==='manual')result[conflict.key].value=value.value===''?null:value.value;}
  return result;
 }
 function summaryText(preview){return `${preview.added||0} added · ${preview.modified||0} field changes · ${(preview.conflicts||[]).length} conflicts · ${(preview.errors||[]).length} invalid items · ${preview.unchanged||0} unchanged rows · ${preview.missing_rows_retained||0} missing rows retained · ${preview.archived||0} archived`;}
 if(typeof module!=='undefined'&&module.exports){module.exports={optionsFrom,resolutionsFrom,summaryText};return;}
 const panel=document.getElementById('excel-panel');if(!panel)return;
 const find=id=>document.getElementById(id),node=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=String(text);return n;};
 const status=find('excel-status');let preview=null,recovery=null,busy=false;
 function tell(text,error=false){status.textContent=text;status.className=error?'error':'info';}
 function setBusy(value){busy=value;for(const control of panel.querySelectorAll('button,input,select,textarea'))control.disabled=value;refreshApply();}
 function refreshApply(){find('excel-apply').disabled=busy||!preview||(preview.errors||[]).length>0;find('excel-recover-apply').disabled=busy||!recovery||!find('excel-recover-confirm').checked;}
 function values(){const result={};for(const field of ['year','inspection_type','area','family','tag','source_sheet','reference_month','include_overdue','include_unscheduled','monthly_sheets','include_summary']){const c=find('excel-'+field);result[field]=c.type==='checkbox'?c.checked:c.value;}return result;}
 async function post(path,body,json=true){const response=await fetch(path,{method:'POST',headers:requestHeaders(json?{'Content-Type':'application/json'}:{'Content-Type':'application/octet-stream'}),body:json?JSON.stringify(body):body});if(!response.ok){let data;try{data=await response.json();}catch{}throw Error(data?.error||'Excel request failed.');}return response;}
 async function download(response,name){const url=URL.createObjectURL(await response.blob()),a=node('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
 async function fullExport(){
  const started=Date.now(),kickoff=await post('/api/excel/export',{mode:'full',options:{}}),{job_id}=await kickoff.json();
  const wrap=find('excel-progress-wrap'),bar=find('excel-progress'),stage=find('excel-progress-stage');wrap.hidden=false;bar.value=1;stage.textContent='Starting export. You can continue using the app.';
  while(true){
   await new Promise(resolve=>setTimeout(resolve,800));
   const response=await fetch('/api/excel/export-progress/'+encodeURIComponent(job_id),{headers:requestHeaders()});
   if(!response.ok){let data;try{data=await response.json();}catch{}throw Error(data?.error||'Unable to check export progress.');}
   const job=await response.json();stage.textContent=`${job.stage} · ${Math.floor((Date.now()-started)/1000)} sec`;
   if(job.stage==='Writing the Excel workbook')bar.removeAttribute('value');else bar.value=job.progress;
   if(job.state==='error')throw Error(job.error||'Full workbook export failed.');
   if(job.state==='ready'){
    bar.value=100;
    const file=await fetch('/api/excel/export-download/'+encodeURIComponent(job_id),{headers:requestHeaders()});
    if(!file.ok){let data;try{data=await file.json();}catch{}throw Error(data?.error||'Workbook is ready but could not be downloaded.');}
    await download(file,'inspection-editable-database.xlsx');
    stage.textContent=`Workbook downloaded · ${Math.floor((Date.now()-started)/1000)} sec`;
    return;
   }
  }
 }
 function modeChanged(){const full=find('excel-mode').value==='full',filtered=find('excel-mode').value==='filtered';for(const id of ['year','inspection_type','reference_month','include_overdue','include_unscheduled','include_summary','monthly_sheets'])find('excel-'+id).closest('label').hidden=filtered;find('excel-report-options').hidden=full;find('excel-export').textContent=full?'Export Editable Database':find('excel-mode').value==='annual'?'Export Yearly Plan':'Export report';find('excel-mode-help').textContent=full?'Complete business workbook, including archived records, source evidence and supported metadata. Suitable for controlled synchronization and Excel business-data recovery.':'Report-only snapshot. This export cannot synchronize changes or recover the complete database.';}
 function populateFilters(){for(const [id,key] of [['area','location_from'],['family','family'],['source_sheet','source_sheet']]){const select=find('excel-'+id),selected=select.value;select.replaceChildren(new Option('All',''));const unique=[...new Set((typeof assets!=='undefined'?assets:[]).map(a=>a[key]).filter(Boolean))].sort((a,b)=>String(a).localeCompare(String(b)));for(const value of unique)select.append(new Option(value,value));if(id==='source_sheet')select.append(new Option('Manual records','__manual__'));select.value=selected;}}
 find('excel-year').value=new Date().getFullYear();find('excel-reference_month').value=typeof currentMonth==='function'?currentMonth():new Date().toISOString().slice(0,7);
 find('excel-mode').addEventListener('change',modeChanged);panel.addEventListener('focusin',e=>{if(['excel-area','excel-family','excel-source_sheet'].includes(e.target.id))populateFilters();});
 for(const control of document.querySelectorAll('[data-open-excel]'))control.addEventListener('click',()=>{show('import');panel.scrollIntoView({behavior:'smooth'});find('excel-mode').focus();populateFilters();});
 find('excel-export').addEventListener('click',async()=>{if(busy)return;setBusy(true);try{const mode=find('excel-mode').value;if(mode==='full'){tell('Full workbook export started. You can continue using the app.');await fullExport();tell('Workbook generated and downloaded.');}else{const options=optionsFrom(values());await download(await post('/api/excel/export',{mode,options}),`inspection-${mode}-${options.year}.xlsx`);tell('Workbook generated.');}}catch(error){tell(error.message,true);}finally{setBusy(false);}});
 function renderPreview(p){const out=find('excel-preview');out.replaceChildren(node('p',summaryText(p)));for(const error of p.errors||[])out.append(node('p',error));const changes=node('details');changes.append(node('summary','Review proposed changes'));for(const change of p.changes||[]){changes.append(node('p',change.new?`${change.sheet}: new row ${change.row_key}`:`${change.sheet} · ${change.asset_id||change.row_key} · ${change.field}: ${JSON.stringify(change.application)} → ${JSON.stringify(change.value)}`));}out.append(changes);for(const conflict of p.conflicts||[]){const box=node('fieldset'),legend=node('legend',`${conflict.asset_id||conflict.row_key} · ${conflict.field}`);box.append(legend);for(const [title,key] of [['Original','original'],['Excel','excel'],['Application','application']])box.append(node('p',`${title}: ${JSON.stringify(conflict[key])}`));const label=node('label','Resolution '),select=node('select');select.dataset.conflictKey=conflict.key;for(const [text,value] of [['Choose a resolution',''],['Keep Excel','excel'],['Keep application','app'],['Enter manual value','manual']])select.append(new Option(text,value));const manualLabel=node('label','Manual value '),manual=node('textarea');manual.dataset.manualKey=conflict.key;manual.value=conflict.excel===null?'':String(conflict.excel??'');manualLabel.hidden=true;select.addEventListener('change',()=>{manualLabel.hidden=select.value!=='manual';});label.append(select);manualLabel.append(manual);box.append(label,manualLabel);out.append(box);}refreshApply();}
 find('excel-sync-file').addEventListener('change',()=>{preview=null;find('excel-preview').replaceChildren();refreshApply();});
 find('excel-preview-button').addEventListener('click',async()=>{if(busy)return;preview=null;setBusy(true);try{const file=find('excel-sync-file').files[0];if(!file)throw Error('Choose a full editable database workbook.');preview=await(await post('/api/excel/preview',file,false)).json();renderPreview(preview);tell('Review proposed changes and resolve all conflicts before applying.');}catch(error){tell(error.message,true);}finally{setBusy(false);}});
 find('excel-apply').addEventListener('click',async()=>{if(busy||!preview)return;setBusy(true);try{const choices={};for(const select of find('excel-preview').querySelectorAll('[data-conflict-key]')){const manual=[...find('excel-preview').querySelectorAll('[data-manual-key]')].find(c=>c.dataset.manualKey===select.dataset.conflictKey);choices[select.dataset.conflictKey]={choice:select.value,value:manual?.value};}const resolutions=resolutionsFrom(preview.conflicts||[],choices),result=await(await post('/api/excel/apply',{token:preview.token,resolutions})).json();preview=null;find('excel-preview').replaceChildren(node('p',`${result.applied} changes applied. Backup saved. Download the reconciled workbook for the next edit cycle.`));const link=node('a','Download reconciled workbook');link.href='/api/excel/reconciled/'+encodeURIComponent(result.download_id);link.download='inspection-reconciled.xlsx';find('excel-preview').append(link);const response=await fetch(link.href);if(response.ok)await download(response,'inspection-reconciled.xlsx');tell('Excel changes applied. Continue editing the reconciled workbook.');if(typeof load==='function')await load();}catch(error){tell(error.message,true);}finally{setBusy(false);}});
 find('excel-recover-file').addEventListener('change',()=>{recovery=null;find('excel-recovery-preview').replaceChildren();find('excel-recover-confirm').checked=false;refreshApply();});find('excel-recover-confirm').addEventListener('change',refreshApply);
 find('excel-recover-preview').addEventListener('click',async()=>{if(busy)return;recovery=null;find('excel-recover-confirm').checked=false;setBusy(true);try{const file=find('excel-recover-file').files[0];if(!file)throw Error('Choose a full editable database workbook.');recovery=await(await post('/api/excel/recovery-preview',file,false)).json();const out=find('excel-recovery-preview');out.replaceChildren(node('p',`${recovery.assets} assets · ${recovery.inspections} inspection obligations`),node('p',recovery.warning));for(const [table,count] of Object.entries(recovery.tables||{}))out.append(node('p',`${table}: ${count}`));tell('Recovery candidate validated. Review counts before confirming activation.');}catch(error){tell(error.message,true);}finally{setBusy(false);}});
 find('excel-recover-apply').addEventListener('click',async()=>{if(busy||!recovery||!find('excel-recover-confirm').checked)return;setBusy(true);try{await post('/api/excel/recovery-apply',{token:recovery.token,confirmed:true});location.reload();}catch(error){tell(error.message,true);setBusy(false);}});
 modeChanged();refreshApply();
})();
