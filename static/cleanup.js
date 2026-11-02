'use strict';
let storedDataInventory=null,storedDeletionPreview=null;

function clearStoredBrowserData(local,session){
 for(const storage of [local,session]){
  const keys=[];for(let i=0;i<storage.length;i++){const key=storage.key(i);if(key?.startsWith('inspection-')&&!['inspection-theme','inspection-data-epoch'].includes(key))keys.push(key)}
  for(const key of keys)storage.removeItem(key);
 }
}
function cleanupConfirmationMatches(preview,value){return !!preview&&value===preview.confirmation}
function visibleSourceCoverage(batches,showDismissed){return batches.filter(batch=>!batch.evidence_deleted&&(showDismissed||!batch.dismissed)&&(batch.unclassified_count||batch.excluded_sheets?.length))}
function cleanupPreviewText(preview){
 const lines=[preview.category==='reset'?'Reset all working data':'Delete selected stored data'];
 for(const [key,count] of Object.entries(preview.counts||{}))lines.push(`${key.replaceAll('_',' ')}: ${count}`);
 if(preview.dependent_assets)lines.push(preview.category==='reset'?`${preview.dependent_assets} current assets and their source links will be removed.`:`${preview.dependent_assets} retained assets depend on this import evidence.`);
 if(preview.files?.length){lines.push('Files to remove:');for(const file of preview.files)lines.push(`${file.folder}/${file.filename}`)}
 lines.push(preview.notice||'');
 if(preview.unavailable_sources?.length)lines.push('Already missing or damaged original sources: '+preview.unavailable_sources.length+'. Protection will preserve available data and record these gaps; it cannot recover already-missing originals.\n'+preview.unavailable_sources.join('\n'));
 if(preview.category!=='recovery_packages'&&preview.category!=='browser')lines.push('A database backup and recovery ZIP will be saved before removal. Saved backups and recovery ZIPs remain separately managed.');
 else if(preview.category==='recovery_packages')lines.push('These selected recovery copies will be removed. No additional backup of these files is created.');
 return lines.join('\n');
}
function browserDataCount(){let count=0;try{for(const storage of [localStorage,sessionStorage])for(let i=0;i<storage.length;i++){const key=storage.key(i);if(key?.startsWith('inspection-')&&!['inspection-theme','inspection-data-epoch'].includes(key))count++}}catch{}return count}
async function loadStoredData(){
 if(!$('#stored-data-category'))return;
 try{
  storedDataInventory=await api('/api/data/inventory');
  const select=$('#stored-data-category'),previous=select.value;select.replaceChildren();
  for(const [key,label] of Object.entries(storedDataInventory.labels)){const option=el('option',`${label} · ${storedDataInventory.counts[key]}`);option.value=key;select.append(option)}
  const browser=el('option',`Browser drafts and reconciliation · ${browserDataCount()}`);browser.value='browser';select.append(browser);
  if(previous)select.value=previous;
  if(!select.value)select.value='imports';
  renderStoredDataItems();
 }catch(error){$('#stored-data-status').textContent=error.message;$('#stored-data-status').className='error'}
}
function renderStoredDataItems(){
 const category=$('#stored-data-category').value,body=$('#stored-data-items');body.replaceChildren();$('#stored-data-all').checked=false;
 const items=category==='browser'?[{id:'browser',label:`Clear ${browserDataCount()} app-owned browser entries; keep theme and other websites' data.`}]:storedDataInventory?.items[category]||[];
 for(const item of items){const label=el('label',null,'cleanup-choice'),input=el('input');input.type='checkbox';input.dataset.cleanupId=item.id;input.onchange=updateStoredDataSelection;label.append(input,el('span',item.label+(item.evidence_deleted?' · evidence already removed; lineage retained':'')));if(item.folder)label.append(el('small',item.folder));body.append(label)}
 if(!items.length)body.append(el('p','No stored records in this category.'));
 $('#stored-data-status').className='';$('#stored-data-status').textContent=category==='sources'||category==='imports'?'Deleting import evidence keeps current assets. Quality checks still identify missing original source files. Embedded copies in assets and other history remain.':category==='history'?'Deleting issue history also removes accepted exceptions. Current issues can reappear when data-quality checks run.':'Select only the items you want to remove, then review the deletion preview.';
 updateStoredDataSelection();
}
function updateStoredDataSelection(){
 const boxes=Array.from($('#stored-data-items').querySelectorAll('input[data-cleanup-id]')),selected=boxes.filter(x=>x.checked).length;
 $('#stored-data-preview').disabled=selected===0;$('#stored-data-selection').textContent=`${selected} selected`;
 const all=$('#stored-data-all');all.checked=boxes.length>0&&selected===boxes.length;all.indeterminate=selected>0&&selected<boxes.length;
}
async function previewStoredCleanup(request){
 try{
  storedDeletionPreview=null;$('#stored-delete-error').textContent='';$('#stored-delete-confirmation').value='';$('#stored-delete-apply').disabled=true;
  if(request.category==='browser')storedDeletionPreview={category:'browser',confirmation:'DELETE',counts:{browser_entries:browserDataCount()},notice:'Only app-owned drafts and reconciliation state in this browser will be removed. Saved database records and backup files remain.'};
  else storedDeletionPreview=await api('/api/data/preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(request)});
  $('#stored-delete-detail').textContent=cleanupPreviewText(storedDeletionPreview);
  const chosen=storedDeletionPreview.selected||[];
  $('#stored-delete-selection').textContent=chosen.length?'Selected records:\n'+chosen.map(item=>`${item.label} · ${item.id}`).join('\n'):'';
  $('#stored-delete-prompt').textContent='Type '+storedDeletionPreview.confirmation+' to confirm';
  $('#stored-delete-dialog').showModal();
 }catch(error){message(error.message,true)}
}
async function applyStoredCleanup(){
 const preview=storedDeletionPreview,button=$('#stored-delete-apply');
 if(!cleanupConfirmationMatches(preview,$('#stored-delete-confirmation').value))return;
 button.disabled=true;$('#stored-delete-cancel').disabled=true;$('#stored-delete-error').textContent='Saving recovery protection and removing the selected data…';
 try{
  if(preview.category==='browser'){clearStoredBrowserData(localStorage,sessionStorage);sessionStorage.setItem('inspection-cleanup-result','Browser drafts and reconciliation cleared. Saved database records remain.');location.reload();return}
  const result=await api('/api/data/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({preview_id:preview.preview_id,confirmation:$('#stored-delete-confirmation').value})});
  if(result.reload_required){clearStoredBrowserData(localStorage,sessionStorage);sessionStorage.setItem('inspection-cleanup-result','Working data reset. Backups retained. Recovery saved: '+result.recovery+(result.warning?' '+result.warning:''));editorDirty=false;location.reload();return}
  $('#stored-delete-dialog').close();storedDeletionPreview=null;selectedAssets.clear();resetImportState(true);
  if(editing?.id&&preview.category==='assets'&&preview.ids.includes(editing.id)){$('#editor').close();editing=null;editorDirty=false}
  await load();await Promise.all([loadStoredData(),loadImportHistory(),loadStagedImports(),loadBackups(),loadBackupStatus(),loadSnapshots()]);
  message('Selected data removed.'+(result.recovery?' Recovery saved: '+result.recovery:'')+(result.warning?' '+result.warning:''),!!result.warning);
 }catch(error){$('#stored-delete-error').textContent=error.message}
 finally{$('#stored-delete-cancel').disabled=false;button.disabled=!cleanupConfirmationMatches(storedDeletionPreview,$('#stored-delete-confirmation').value)}
}
async function setSourceCoverageDismissed(batchId,dismissed){
 try{await api('/api/data/coverage',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({batch_id:batchId,dismissed})});await loadImportHistory();if(storedDataInventory)await loadStoredData();message(dismissed?'Coverage entry dismissed. Its source evidence is retained. Use Show dismissed to restore it.':'Coverage entry restored.')}catch(error){message(error.message,true)}
}
function setupStoredData(){
 if(!$('#stored-data-category'))return;
 try{const result=sessionStorage.getItem('inspection-cleanup-result');if(result){sessionStorage.removeItem('inspection-cleanup-result');message(result)}}catch{}
 $('#stored-data-category').onchange=renderStoredDataItems;$('#stored-data-refresh').onclick=loadStoredData;
 $('#stored-data-all').onchange=()=>{for(const box of $('#stored-data-items').querySelectorAll('input[data-cleanup-id]'))box.checked=$('#stored-data-all').checked;updateStoredDataSelection()};
 $('#stored-data-preview').onclick=()=>previewStoredCleanup({category:$('#stored-data-category').value,ids:Array.from($('#stored-data-items').querySelectorAll('input[data-cleanup-id]')).filter(x=>x.checked).map(x=>x.dataset.cleanupId)});
 $('#stored-data-reset').onclick=()=>previewStoredCleanup({category:'reset'});
 $('#stored-delete-confirmation').oninput=()=>{$('#stored-delete-apply').disabled=!cleanupConfirmationMatches(storedDeletionPreview,$('#stored-delete-confirmation').value)};
 $('#stored-delete-cancel').onclick=()=>{$('#stored-delete-dialog').close();storedDeletionPreview=null};
 $('#stored-delete-dialog').addEventListener('cancel',event=>{if($('#stored-delete-cancel').disabled)event.preventDefault();else storedDeletionPreview=null});
 $('#stored-delete-apply').onclick=applyStoredCleanup;
 $('#coverage-show-dismissed').onchange=loadImportHistory;
 $('#delete-selected-assets').onclick=()=>previewStoredCleanup({category:'assets',ids:Array.from(selectedAssets)});
}
if(typeof document!=='undefined')setupStoredData();
