const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('static/app.js','utf8');
test('loading a reset dataset removes old browser state and keeps appearance',()=>{
 function storage(values){const rows=new Map(Object.entries(values));return {get length(){return rows.size},key:i=>Array.from(rows.keys())[i],removeItem:k=>rows.delete(k),getItem:k=>rows.get(k)??null,setItem:(k,v)=>rows.set(k,v)}}
 const local=storage({'inspection-data-epoch':'old','inspection-theme':'dark','inspection-recon-aliases':'old aliases',unrelated:'keep'}),session=storage({'inspection-last-bulk':'old operation'});
 const ctx=vm.createContext({});vm.runInContext(getFunction('synchronizeBrowserDataset'),ctx);
 ctx.synchronizeBrowserDataset(local,session,'new');
 assert.equal(local.getItem('inspection-recon-aliases'),null);assert.equal(session.getItem('inspection-last-bulk'),null);assert.equal(local.getItem('inspection-theme'),'dark');assert.equal(local.getItem('unrelated'),'keep');assert.equal(local.getItem('inspection-data-epoch'),'new');
});
test('backup upload accepts compressed and existing SQLite formats',()=>{
 const html=fs.readFileSync('static/index.html','utf8');
 const input=html.match(/<input[^>]*id="restore-file"[^>]*>/)[0];
 const accepted=input.match(/accept="([^"]+)"/)[1].split(',');
 for(const extension of ['.db','.sqlite','.sqlite3','.gz'])assert.ok(accepted.includes(extension),extension);
});
test('main served script can render an import preview without loading a second script',()=>{
 const nodes={};function node(tag){return {tagName:tag,content:'test-token',children:[],value:'',dataset:{},attributes:{},classList:{toggle(){},add(){},remove(){}},addEventListener(){},setAttribute(k,v){this.attributes[k]=v},removeAttribute(k){delete this.attributes[k]},setCustomValidity(v){this.validationMessage=v},checkValidity(){return !this.validationMessage},focus(){},append(...xs){this.children.push(...xs)},replaceChildren(...xs){this.children=xs}}}
 const document={querySelector:s=>nodes[s]??=node('div'),querySelectorAll:()=>[],createElement:node};
 const ctx=vm.createContext({document,window:{addEventListener(){}},sessionStorage:{getItem:()=>null},localStorage:{getItem:()=>null},fetch:()=>new Promise(()=>{}),Date});
 vm.runInContext(fs.readFileSync('static/app.js','utf8'),ctx);
 ctx.renderImportPreview({token:'preview',format:'legacy',conflicts:[],partial:false,counts:{Assets:1,'Inspection Plan':1,'Review Items':0},additions:1,updates:0,retained:0,errors:[],comparison:[],included_sheets:['FLs'],excluded_sheets:[],sheet_summary:[]});
 assert.match(nodes['#import-result'].children[0].textContent,/1 assets/);assert.equal(nodes['#apply'].hidden,false);
 const all=n=>[n,...n.children.flatMap(all)],custom=all(nodes['#custom-end-host']).find(n=>n.id==='custom-end');assert.ok(custom);assert.equal(custom.type,'text');assert.ok(all(nodes['#custom-end-host']).some(n=>n.className==='month-picker-toggle'));
});
test('view switching leaves nested content regions available inside the active view',()=>{
 const top={id:'import',hidden:true},nested={id:undefined,hidden:false},nav={dataset:{view:'import'},classList:{toggle(){}}};
 const document={querySelectorAll(selector){if(selector==='main > section')return[top];if(selector==='main section')return[top,nested];if(selector==='nav button')return[nav];return[]}};
 const ctx=vm.createContext({document,message(){},loadBackups(){},loadBackupStatus(){},loadStagedImports(){},loadImportHistory(){},renderImportProgress(){}});
 vm.runInContext(getFunction('show'),ctx);ctx.show('import');
 assert.equal(top.hidden,false);assert.equal(nested.hidden,false);
});
function importContext(){
 function node(tag='div',text=''){return {tagName:tag,textContent:text,children:[],hidden:false,disabled:false,value:'merge',checked:false,classList:{toggle(){}},append(...xs){this.children.push(...xs)},replaceChildren(...xs){this.children=xs},setAttribute(){}}}
 const nodes={};const ctx=vm.createContext({$:s=>nodes[s]??=node(),el:node,importInfo:{format:'legacy',sheets:[{name:'FLs',role:'assets'},{name:'Coolers',role:'reference'}]},importSelection:new Set(['FLs','Coolers']),previewToken:'old',importGeneration:0,importBusy:false,importReview:{partial:false,token:null,conflicts:[],decisions:new Map(),dirty:new Set()}});
 for(const name of ['invalidateImportPreview','updateImportSelection','renderImportSheets','importSelectionNames','importResponseIsCurrent'])vm.runInContext(getFunction(name),ctx);
 return {ctx,nodes};
}
test('excluding a tab invalidates preview and prevents partial replace',()=>{
 const {ctx,nodes}=importContext();ctx.renderImportSheets();ctx.updateImportSelection('Coolers',false);
 assert.equal(ctx.previewToken,null);assert.equal(nodes['#apply'].hidden,true);assert.equal(nodes['#import-mode'].disabled,true);assert.equal(nodes['#import-mode'].value,'merge');
 assert.deepEqual(Array.from(ctx.importSelectionNames()),['FLs']);
});
test('choosing a duplicate action hides import and retains the server review token',()=>{
 const {ctx,nodes}=importContext();ctx.importReview={token:'review-base',conflicts:[{row_key:'row-1'}],decisions:new Map(),dirty:new Set(),partial:false};
 vm.runInContext(getFunction('updateImportDecision'),ctx);ctx.updateImportDecision('row-1','skip');
 assert.equal(ctx.previewToken,null);assert.equal(nodes['#apply'].hidden,true);assert.equal(ctx.importReview.token,'review-base');
 assert.equal(ctx.importReview.decisions.get('row-1').action,'skip');assert.equal(ctx.importReview.dirty.has('row-1'),true);
 assert.equal(nodes['#import-mode'].value,'merge');assert.equal(nodes['#import-mode'].disabled,true);
});
test('existing asset decisions carry the selected target and can be returned to review',()=>{
 const {ctx}=importContext();ctx.importReview={token:'base',conflicts:[{row_key:'row'}],decisions:new Map(),dirty:new Set(),partial:false};
 vm.runInContext(getFunction('updateImportDecision'),ctx);ctx.updateImportDecision('row','match:existing-7');
 assert.equal(ctx.importReview.decisions.get('row').asset_id,'existing-7');ctx.updateImportDecision('row','');
 assert.equal(ctx.importReview.decisions.get('row').action,'review');
});
test('changing tabs clears pending duplicate decisions along with the preview',()=>{
 const {ctx}=importContext();ctx.importReview={token:'old',conflicts:[{}],decisions:new Map([['row',{action:'skip'}]]),dirty:new Set(['row']),partial:true};
 ctx.updateImportSelection('Coolers',false);assert.equal(ctx.importReview.token,null);assert.equal(ctx.importReview.decisions.size,0);
});
test('completed upload preview renders actionable duplicate controls after busy upload',()=>{
 const {ctx,nodes}=importContext();ctx.importBusy=true;ctx.resolveImportPreview=()=>{};
 for(const name of ['importEvidence','renderImportConflicts','renderImportPreview'])vm.runInContext(getFunction(name),ctx);
 ctx.renderImportPreview({token:'new',format:'legacy',partial:false,counts:{Assets:2,'Inspection Plan':2,'Review Items':0},additions:2,updates:0,retained:0,errors:['Needs decisions'],warnings:[],comparison:[],included_sheets:['FLs','Coolers'],excluded_sheets:[],sheet_summary:[],unresolved_count:1,conflicts:[{row_key:'row',source_sheet:'FLs',source_row:4,asset:{name:'AG-101'},inspections:[],notes:[],reasons:['Duplicate'],candidates:[],resolved:false}]});
 const all=node=>[node,...node.children.flatMap(all)];const decision=all(nodes['#import-result']).find(n=>n.tagName==='select');
 assert.ok(decision);assert.equal(decision.disabled,false);assert.equal(ctx.importBusy,false);assert.equal(nodes['#apply'].hidden,true);
});
test('older running import server gives a restart instruction before rendering incompatible preview',()=>{
 const {ctx}=importContext();ctx.renderImportConflicts=()=>{};
 vm.runInContext(getFunction('renderImportPreview'),ctx);
 assert.throws(()=>ctx.renderImportPreview({format:'legacy',token:'old-backend'}),/restart|close.*app/i);
 assert.equal(ctx.previewToken,'old');
});
test('clearing data resets the uploaded file and invalidates late import responses',()=>{
 const {ctx,nodes}=importContext();ctx.importFile={name:'old.xlsx'};const oldFile=ctx.importFile,generation=ctx.importGeneration;
 ctx.importReview.token='old-review';vm.runInContext(getFunction('resetImportState'),ctx);ctx.resetImportState(true);
 assert.equal(ctx.importFile,null);assert.equal(ctx.importInfo,null);assert.equal(ctx.importSelection.size,0);
 assert.equal(ctx.importReview.token,null);assert.equal(ctx.importResponseIsCurrent(generation,oldFile),false);
 assert.equal(nodes['#preview'].disabled,true);assert.equal(nodes['#file'].value,'');
});
test('bulk selection supports no tabs without enabling a preview',()=>{
 const {ctx,nodes}=importContext();ctx.renderImportSheets();nodes['#import-deselect-all'].onclick();
 assert.equal(ctx.importSelectionNames().length,0);assert.equal(nodes['#preview'].disabled,true);
 nodes['#import-select-all'].onclick();assert.equal(ctx.importSelectionNames().length,2);assert.equal(nodes['#preview'].disabled,false);
});
test('obsolete import responses are ignored after file or tab selection changes',()=>{
 const {ctx}=importContext();const file={};ctx.importFile=file;const generation=ctx.importGeneration;
 assert.equal(ctx.importResponseIsCurrent(generation,file),true);ctx.updateImportSelection('Coolers',false);
 assert.equal(ctx.importResponseIsCurrent(generation,file),false);assert.equal(ctx.importResponseIsCurrent(ctx.importGeneration,{}),false);
});
function getFunction(name){const start=source.indexOf('function '+name+'(');assert.notEqual(start,-1,`${name} must exist`);let depth=0,opened=false;for(let i=source.indexOf('{',start);i<source.length;i++){if(source[i]==='{'){depth++;opened=true}if(source[i]==='}'){depth--;if(depth===0&&opened)return source.slice(start,i+1)}}throw Error('missing function end')}
test('switching source sheets clears conflicting filters and resets pagination',()=>{
 const controls=Object.fromEntries(['sheet','search','family','service','due-filter','review-filter','status'].map(id=>['#'+id,{value:'previous filter'}]));let renders=0;
 const context=vm.createContext({$:id=>controls[id],renderAssets:()=>renders++,shown:300,assetPage:4});
 vm.runInContext(getFunction('selectSourceSheet'),context);context.selectSourceSheet('GP Piping');
 assert.equal(controls['#sheet'].value,'GP Piping');assert.equal(controls['#status'].value,'active');
 for(const id of ['search','family','service','due-filter','review-filter'])assert.equal(controls['#'+id].value,'');
 assert.equal(context.shown,300);assert.equal(context.assetPage,1);assert.equal(renders,1);
});
test('saving omits untouched newly added blank rows without deleting imported data',()=>{
 const context=vm.createContext({structuredClone});vm.runInContext(getFunction('prepareAssetForSave'),context);
 const asset={technical_details:[{field_id:'original',field_label:'Original blank',value:''},{field_id:'draft',field_label:'',value:''}],notes:[{note_id:'old',note_text:''},{note_id:'new',note_text:'   '}]};
 const saved=context.prepareAssetForSave(asset,new Set(['draft','new']));
 assert.equal(saved.technical_details.length,1);assert.equal(saved.technical_details[0].field_id,'original');assert.equal(saved.notes.length,1);assert.equal(asset.technical_details.length,2);
});
test('a new technical value needs a field name before saving',()=>{
 const context=vm.createContext({structuredClone});vm.runInContext(getFunction('prepareAssetForSave'),context);
 assert.throws(()=>context.prepareAssetForSave({technical_details:[{field_id:'draft',field_label:'',value:'Cold'}],notes:[]},new Set(['draft'])),/field name/i);
});
test('an imported unnamed asset displays its existing identifier without changing stored name',()=>{
 const context=vm.createContext({});vm.runInContext(getFunction('assetDisplayName'),context);
 const a={name:'(unnamed asset)',tag_original:'NA',oracle_description:'Sep-204'};
 assert.equal(context.assetDisplayName(a),'Sep-204');assert.equal(a.name,'(unnamed asset)');
 assert.equal(context.assetDisplayName({name:'Pump 7',tag_original:'P7'}),'Pump 7');
});
test('yearly rows honor source and inspection type while excluding review and archived entries',()=>{
 const context=vm.createContext({active:a=>a.record_status!=='Archived',applicable:i=>i.applicable==='Yes'});vm.runInContext(getFunction('yearlyRows'),context);
 const plan=[{name:'Vessel',source_sheet:'Tanks',inspections:[{inspection_type:'OSI',applicable:'Yes',next_inspection_month:'2027-02'},{inspection_type:'Internal',applicable:'Yes',next_inspection_month:'2027-01'}]},{name:'Pipe',source_sheet:'Lines',inspections:[{inspection_type:'OSI',applicable:'Yes',next_inspection_month:'2027-03',review_status:'Review'}]},{name:'Archived',source_sheet:'Tanks',record_status:'Archived',inspections:[{inspection_type:'OSI',applicable:'Yes',next_inspection_month:'2027-04'}]}];
 const result=context.yearlyRows(plan,'2027','Tanks','Internal');assert.equal(result.length,1);assert.equal(result[0][2].inspection_type,'Internal');assert.equal(context.yearlyRows(plan,'2027','','').length,2);
});
test('selected export includes only chosen assets even when the register filter changes',()=>{
 const context=vm.createContext({});vm.runInContext(getFunction('selectedAssetRows'),context);
 const records=[{id:'a',name:'A'},{id:'b',name:'B'},{id:'c',name:'C'}];
 const result=context.selectedAssetRows(records,new Set(['a','c']));assert.equal(result.length,2);assert.equal(result[0].id,'a');assert.equal(result[1].id,'c');
});
test('asset grouping keeps all entries and sorts groups by selected local field',()=>{
 const context=vm.createContext({});vm.runInContext(getFunction('groupAssetRows'),context);
 const result=context.groupAssetRows([{id:'a',plant:'West'},{id:'b',plant:'East'},{id:'c',plant:''}], 'plant');
 assert.equal(result.length,3);assert.equal(result[0].label,'East');assert.equal(result[1].label,'West');assert.equal(result[2].label,'Unspecified');
 assert.equal(context.groupAssetRows([{id:'a'},{id:'b'}],'').length,1);
});
test('yearly plan includes earlier months only when carry-over is selected',()=>{
 const context=vm.createContext({active:a=>a.record_status!=='Archived',applicable:i=>i.applicable==='Yes'});vm.runInContext(getFunction('yearlyRows'),context);
 const rows=[{name:'Past',inspections:[{inspection_type:'OSI',applicable:'Yes',next_inspection_month:'2025-03'}]},{name:'Current',inspections:[{inspection_type:'OSI',applicable:'Yes',next_inspection_month:'2027-02'}]},{name:'Future',inspections:[{inspection_type:'OSI',applicable:'Yes',next_inspection_month:'2028-01'}]}];
 assert.equal(context.yearlyRows(rows,'2027','','',false).length,1);assert.equal(context.yearlyRows(rows,'2027','','',true).length,2);
});
test('asset pages clamp to valid pages and preserve all grouped records',()=>{
 const context=vm.createContext({});vm.runInContext(getFunction('paginateAssets'),context);
 const items=Array.from({length:23},(_,i)=>({id:i}));
 let result=context.paginateAssets(items,2,10);assert.equal(result.page,2);assert.equal(result.pages,3);assert.equal(result.rows[0].id,10);
 result=context.paginateAssets(items,9,10);assert.equal(result.page,3);assert.equal(result.rows.length,3);
 result=context.paginateAssets([],5,10);assert.equal(result.page,1);assert.equal(result.pages,1);assert.equal(result.rows.length,0);
});
test('search matches all tokens across asset fields and common equipment abbreviations',()=>{
 const context=vm.createContext({});vm.runInContext(getFunction('matchesAssetSearch'),context);
 const asset={name:'Gas compressor suction',source_sheet:'GP Piping',tag_original:'C-123'};
 assert.equal(context.matchesAssetSearch(asset,'comp gp'),true);assert.equal(context.matchesAssetSearch(asset,'turbine gp'),false);assert.equal(context.matchesAssetSearch(asset,'C-123'),true);
});
test('overdue aging uses whole calendar months and excludes current or undated inspections',()=>{
 const context=vm.createContext({});vm.runInContext(getFunction('overdueAgeMonths'),context);
 assert.equal(context.overdueAgeMonths('2026-09','2026-10'),1);assert.equal(context.overdueAgeMonths('2025-10','2026-10'),12);assert.equal(context.overdueAgeMonths('2026-10','2026-10'),null);assert.equal(context.overdueAgeMonths(null,'2026-10'),null);
});
test('special schedule filters match the preserved condition without inventing dates',()=>{
 const context=vm.createContext({});vm.runInContext(getFunction('matchesSchedulingCondition'),context);
 assert.equal(context.matchesSchedulingCondition({scheduling_condition:'At next shutdown'},'shutdown'),true);
 assert.equal(context.matchesSchedulingCondition({scheduling_condition:'Awaiting evaluation'},'evaluation'),true);
 assert.equal(context.matchesSchedulingCondition({scheduling_condition:'OOS'},'evaluation'),false);
});
test('row opening ignores clicks on controls and opens for ordinary cells',()=>{
 let opened=[];const context=vm.createContext({openEditor:id=>opened.push(id)});vm.runInContext(getFunction('enableAssetRow'),context);
 const row={classList:{add(){}},onclick:null};context.enableAssetRow(row,'asset-1');
 row.onclick({target:{closest:()=>null}});row.onclick({target:{closest:()=>({})}});
 assert.deepEqual(opened,['asset-1']);
});
test('recent reconciliation highlights retain asset fields and inspection scope',()=>{
 const ctx=vm.createContext({});vm.runInContext(getFunction('buildReconciliationHighlights'),ctx);
 const selected=[{row:{chosen:'a',inspection_type:'OSI',changes:{next_inspection_month:'2027-02',remark:'Reviewed'}}},{row:{chosen:'a',inspection_type:'Internal',changes:{last_inspection_month:'2026-01'}}}];
 const result=ctx.buildReconciliationHighlights(selected);
 assert.equal(result.a.OSI.next_inspection_month,'2027-02');assert.equal(result.a.Internal.last_inspection_month,'2026-01');assert.equal(result.a.asset.remark,'Reviewed');
});
test('confirmed reconciliation matches and selected proposals can be shown without applying them',()=>{
 const ctx=vm.createContext({});vm.runInContext(getFunction('buildConfirmedReconHighlights'),ctx);
 const rows=[{row:3,chosen:'a',inspection_type:'Internal',confirmed:true,changes:{next_inspection_month:'2027-02',remark:'Proposed note'}},{row:4,chosen:'b',inspection_type:'OSI',confirmed:true,changes:{}},{row:5,chosen:'c',confirmed:false,changes:{remark:'not confirmed'}},{row:6,chosen:'d',confirmed:true,excluded:true,changes:{}}];
 const result=ctx.buildConfirmedReconHighlights(rows);assert.equal(result.a[0].changes.next_inspection_month,'2027-02');assert.equal(result.a[0].inspection_type,'Internal');assert.equal(result.b.length,1);assert.equal(result.c,undefined);assert.equal(result.d,undefined);
});
test('dashboard attention explains review flags, recorded conditions, and missing dates separately',()=>{
 const ctx=vm.createContext({});vm.runInContext(getFunction('inspectionAttention'),ctx);
 assert.deepEqual(JSON.parse(JSON.stringify(ctx.inspectionAttention({review_status:'Review',review_reason:'Ambiguous date',next_original:'TBC'}))),{kind:'review',label:'Needs review',detail:'Ambiguous date',original:'TBC'});
 assert.equal(ctx.inspectionAttention({scheduling_condition:'OOS'}).label,'OOS');
 assert.equal(ctx.inspectionAttention({}).label,'No scheduled date');
});

test('source navigation exits both reconciliation-only views',()=>{
 const controls=Object.fromEntries(['sheet','search','family','service','due-filter','review-filter','status'].map(id=>['#'+id,{value:''}]));
 const ctx=vm.createContext({$:id=>controls[id],renderAssets(){},onlyRecentRecon:true,onlyConfirmedRecon:true,assetPage:4});
 vm.runInContext(getFunction('selectSourceSheet'),ctx);ctx.selectSourceSheet('GP Piping');
 assert.equal(ctx.onlyRecentRecon,false);assert.equal(ctx.onlyConfirmedRecon,false);
});

test('dashboard summary and aging cards exit reconciliation restrictions',()=>{
 function node(){return {value:'',children:[],dataset:{},classList:{add(){}},append(...xs){this.children.push(...xs)},replaceChildren(...xs){this.children=xs},setAttribute(){}}}
 const nodes={};const ctx=vm.createContext({$:s=>nodes[s]??=node(),assets:[],onlyRecentRecon:true,onlyConfirmedRecon:true,assetPage:4,Date,el:()=>node(),active:()=>true,applicable:()=>true,currentMonth:()=> '2026-11',addMonths:()=> '2027-02',queuePanel:()=>node(),renderSheetShortcuts(){},show(){}});
 vm.runInContext(getFunction('renderDashboard'),ctx);ctx.renderDashboard();
 for(const card of [...nodes['#cards'].children,...nodes['#aging-panel'].children[1].children]){
  ctx.onlyRecentRecon=true;ctx.onlyConfirmedRecon=true;ctx.assetPage=4;card.onclick();
  assert.equal(ctx.onlyRecentRecon,false);assert.equal(ctx.onlyConfirmedRecon,false);assert.equal(ctx.assetPage,1);
 }
});

test('verify selected follows the cross-page register selection bar',()=>{
 function node(){return {value:'',hidden:false,disabled:false,checked:false,indeterminate:false,textContent:''}}
 const nodes={'#select-visible':node(),'#selection-count':node(),'#selection-bar':node(),'#verify-selected':node()};
 const selectedAssets=new Set(['asset-selected-on-another-page']);const ctx=vm.createContext({$:selector=>nodes[selector],selectedAssets,visibleAssetRows:()=>[]});
 vm.runInContext(getFunction('updateSelectionBar'),ctx);ctx.updateSelectionBar();
 assert.equal(nodes['#selection-bar'].hidden,false);assert.equal(nodes['#verify-selected'].disabled,false);
 selectedAssets.clear();ctx.updateSelectionBar();assert.equal(nodes['#selection-bar'].hidden,true);assert.equal(nodes['#verify-selected'].disabled,true);
});

test('saved backups expose selectable rows, select all and an empty disabled delete action',async()=>{
 const html=fs.readFileSync('static/index.html','utf8');
 for(const id of ['backup-select-all','backup-selection-count','delete-selected-backups'])assert.match(html,new RegExp(`id="${id}"`));
 function node(tag='div',text=''){return {tagName:tag,textContent:text,children:[],value:'',checked:false,disabled:false,indeterminate:false,dataset:{},append(...items){this.children.push(...items)},replaceChildren(...items){this.children=items},setAttribute(name,value){this[name]=value},querySelectorAll(selector){const all=n=>[n,...n.children.flatMap(all)];return all(this).filter(item=>selector==='input[data-backup-name]'&&item.tagName==='input'&&item.dataset.backupName)}}}
 const nodes={},backups=[{filename:'inspection-a.db',modified:'2026-01-01T10:00:00',size:100},{filename:'inspection-b.db',modified:'2026-01-02T10:00:00',size:200}];
 const ctx=vm.createContext({savedBackups:[],selectedBackupNames:new Set(),$:selector=>nodes[selector]??=node(),el:(tag,text,cls)=>{const item=node(tag,text??'');item.className=cls||'';return item},Date,
  api:async path=>path==='/api/backups'?backups:[],message(){},confirm:()=>true});
 function extract(name){let start=source.indexOf('function '+name+'(');assert.notEqual(start,-1,`${name} must exist`);const prefix=source.slice(Math.max(0,start-6),start)==='async '?'async ':'';let depth=0,opened=false;for(let i=source.indexOf('{',start);i<source.length;i++){if(source[i]==='{'){depth++;opened=true}if(source[i]==='}'){depth--;if(opened&&depth===0)return prefix+source.slice(start,i+1)}}throw Error(name+' has no closing brace')}
 for(const name of ['updateBackupSelectionUI','setSavedBackupSelection','setAllSavedBackupSelection','loadBackups','deleteSelectedBackups','setupBackupSelection'])vm.runInContext(extract(name),ctx);
 ctx.setupBackupSelection();await ctx.loadBackups();
 const all=n=>[n,...n.children.flatMap(all)],boxes=all(nodes['#backup-list']).filter(item=>item.tagName==='input');
 assert.equal(boxes.length,2);assert.equal(nodes['#delete-selected-backups'].disabled,true);assert.equal(nodes['#backup-selection-count'].textContent,'0 selected');
 boxes[0].checked=true;boxes[0].onchange();assert.equal(nodes['#delete-selected-backups'].disabled,false);assert.equal(nodes['#backup-selection-count'].textContent,'1 selected');assert.equal(nodes['#backup-select-all'].indeterminate,true);
 nodes['#backup-select-all'].checked=true;nodes['#backup-select-all'].onchange({target:nodes['#backup-select-all']});assert.equal(ctx.selectedBackupNames.size,2);assert.equal(nodes['#backup-selection-count'].textContent,'2 selected');
});

test('saved backup deletion confirms exact filenames, deletes selected records and refreshes',async()=>{
 function node(tag='div',text=''){return {tagName:tag,textContent:text,children:[],value:'',checked:false,disabled:false,indeterminate:false,dataset:{},append(...items){this.children.push(...items)},replaceChildren(...items){this.children=items},setAttribute(name,value){this[name]=value}}}
 const nodes={},backups=[{filename:'inspection-a.db',modified:'2026-01-01T10:00:00',size:100},{filename:'inspection-b.db',modified:'2026-01-02T10:00:00',size:200},{filename:'inspection-c.db',modified:'2026-01-03T10:00:00',size:300}],requests=[];
 const ctx=vm.createContext({savedBackups:[],selectedBackupNames:new Set(),$:selector=>nodes[selector]??=node(),el:(tag,text,cls)=>{const item=node(tag,text??'');item.className=cls||'';return item},Date,
  api:async(path,options)=>{if(path==='/api/backups')return backups.filter(item=>!ctx.deleted?.includes(item.filename));const body=JSON.parse(options.body);requests.push({path,body});ctx.deleted=['inspection-a.db'];return {deleted:['inspection-a.db'],failed:[{filename:'inspection-b.db',error:'locked'}]}},
  message(text){ctx.lastMessage=text},loadBackupStatus:async()=>{ctx.statusRefreshes=(ctx.statusRefreshes||0)+1},confirm(prompt){ctx.prompt=prompt;return ctx.confirmResult}});
 function extract(name){let start=source.indexOf('function '+name+'(');assert.notEqual(start,-1,`${name} must exist`);const prefix=source.slice(Math.max(0,start-6),start)==='async '?'async ':'';let depth=0,opened=false;for(let i=source.indexOf('{',start);i<source.length;i++){if(source[i]==='{'){depth++;opened=true}if(source[i]==='}'){depth--;if(opened&&depth===0)return prefix+source.slice(start,i+1)}}throw Error(name+' has no closing brace')}
 for(const name of ['updateBackupSelectionUI','setSavedBackupSelection','setAllSavedBackupSelection','loadBackups','deleteSelectedBackups'])vm.runInContext(extract(name),ctx);
 await ctx.loadBackups();const all=n=>[n,...n.children.flatMap(all)],boxes=all(nodes['#backup-list']).filter(item=>item.tagName==='input');
 boxes[0].checked=true;boxes[0].onchange();boxes[1].checked=true;boxes[1].onchange();ctx.confirmResult=false;await ctx.deleteSelectedBackups();
 assert.equal(requests.length,0);assert.match(ctx.prompt,/inspection-a\.db/);assert.match(ctx.prompt,/inspection-b\.db/);assert.doesNotMatch(ctx.prompt,/inspection-c\.db/);
 ctx.confirmResult=true;await ctx.deleteSelectedBackups();
 assert.deepEqual(requests,[{path:'/api/backups/delete',body:{filenames:['inspection-a.db','inspection-b.db']}}]);
 assert.equal(ctx.selectedBackupNames.size,0);assert.equal(all(nodes['#backup-list']).filter(item=>item.tagName==='input').length,2);assert.equal(ctx.statusRefreshes,1);assert.match(ctx.lastMessage,/Deleted 1 backup/);assert.match(ctx.lastMessage,/1 could not be deleted/);
});

test('month entry combines typing with a year and month-grid popup without day choices',()=>{
 let draftWrites=0,dismiss=null,activeElement=null;const document={get activeElement(){return activeElement},addEventListener(name,listener){if(name==='pointerdown')dismiss=listener},removeEventListener(name,listener){if(name==='pointerdown'&&dismiss===listener)dismiss=null}};
 function node(tag,text,cls){return {tagName:tag,textContent:text,children:[],className:cls,value:'',hidden:false,disabled:false,attributes:{},dataset:{},classList:{toggle(){}},append(...items){this.children.push(...items)},setAttribute(key,value){this.attributes[key]=value},removeAttribute(key){delete this.attributes[key]},setCustomValidity(value){this.validationMessage=value},focus(){activeElement=this},contains(target){return !target?.outside}}}
 const ctx=vm.createContext({el:node,editorDirty:false,monthFieldSequence:0,Date,document,persistEditorDraft(){draftWrites++}});vm.runInContext(getFunction('monthEntry'),ctx);vm.runInContext(getFunction('field'),ctx);
 const parent=node('div');let saved;
 const label=ctx.field(parent,'Next inspection month','2027-04',v=>saved=v),wrap=parent.children[0],all=n=>[n,...n.children.flatMap(all)],month=all(wrap).find(child=>child.tagName==='input'),toggle=all(wrap).find(child=>child.className==='month-picker-toggle'),picker=all(wrap).find(child=>child.className==='month-picker');
 assert.equal(month.type,'text');assert.equal(month.value,'2027-04');assert.equal(month.placeholder,'YYYY-MM');const hint=all(wrap).find(child=>child.className==='month-entry-hint');assert.match(hint.textContent,/type.*or pick/i);assert.match(hint.textContent,/No day is recorded/);assert.equal(picker.hidden,true);
 month.value='2027-05';month.oninput();assert.equal(saved,'2027-05');assert.equal(ctx.editorDirty,true);assert.equal(draftWrites,1);
 month.value='2027-13';month.oninput();month.onblur();assert.equal(month.attributes['aria-invalid'],'true');assert.match(all(wrap).find(child=>child.className==='month-entry-error').textContent,/YYYY-MM/);
 month.value='';month.oninput();assert.equal(saved,null);assert.equal(draftWrites,4);
 toggle.onclick();assert.equal(picker.hidden,false);assert.equal(toggle.attributes['aria-expanded'],'true');const buttons=all(picker).filter(child=>child.className==='month-picker-month');assert.equal(buttons.length,12);assert.equal(buttons[0].textContent,'Jan');assert.equal(all(picker).some(child=>/^([0-9]|[12][0-9]|3[01])$/.test(child.textContent)),false);
 const yearLabel=all(picker).find(child=>child.className==='month-picker-year'),currentMonthLabel=new Date().toLocaleString('en',{month:'long'}),currentMonthIndex=new Date().getMonth();assert.equal(yearLabel.textContent,`${currentMonthLabel} ${new Date().getFullYear()}`);picker.onkeydown({key:'ArrowLeft',preventDefault(){}});assert.equal(document.activeElement,buttons[(currentMonthIndex+11)%12]);all(picker).find(child=>child.className==='month-picker-next').onclick();assert.equal(yearLabel.textContent,`${currentMonthLabel} ${new Date().getFullYear()+1}`);
 buttons[7].onclick();assert.equal(month.value,`${new Date().getFullYear()+1}-08`);assert.equal(saved,month.value);assert.equal(picker.hidden,true);assert.equal(ctx.editorDirty,true);assert.equal(draftWrites,5);
 toggle.onclick();picker.onkeydown({key:'Escape',preventDefault(){}});assert.equal(picker.hidden,true);assert.equal(toggle.attributes['aria-expanded'],'false');
 toggle.onclick();assert.equal(picker.hidden,false);dismiss({target:{outside:true}});assert.equal(picker.hidden,true);assert.equal(toggle.attributes['aria-expanded'],'false');assert.equal(dismiss,null);
 const applicability=ctx.field(parent,'Applicable (Yes / No)','Yes',()=>{}).children[0];
 assert.equal(applicability.tagName,'select');assert.ok(applicability.children.some(o=>o.value==='No'));
 const status=ctx.field(parent,'Record status','Legacy status',()=>{}).children[0];
 assert.equal(status.value,'Legacy status');assert.ok(status.children.some(o=>o.value==='Legacy status'));
});

test('field state cues show text for review, changed, verified and neutral fields',()=>{
 function node(tag='label',text=''){return {tagName:tag,textContent:text,children:[],classes:new Set(),classList:{add(value){this.owner.classes.add(value)},owner:null},append(...items){this.children.push(...items)}}}
 const el=(tag,text,cls)=>{const item=node(tag,text);if(cls)item.className=cls;item.classList.owner=item;return item};
 const ctx=vm.createContext({el});vm.runInContext(getFunction('markFieldState'),ctx);
 for(const [state,label,cls] of [['review','Needs review','field-state-review'],['changed','Changed · not verified','field-state-changed'],['verified','Verified for current value','field-state-verified'],['','', '']]){
  const field=node();field.classList.owner=field;ctx.markFieldState(field,state);assert.equal(field.children[0]?.textContent||'',label);if(cls){assert.ok(field.classes.has(cls));assert.equal(field.children[0].className,'field-state-label '+cls)}else assert.equal(field.children.length,0);
 }
});

test('register and reconciliation search use search controls while asset numbers stay free text',()=>{
 const html=fs.readFileSync('static/index.html','utf8');assert.match(html,/<input type="search" aria-label="Search assets" id="search"/);assert.match(html,/<input type="search" id="recon-search"/);assert.match(html,/<input id="recon-year" type="number"/);
 function node(tag='div',text=''){return {tagName:tag,textContent:text,value:'',type:tag==='input'?'text':'',children:[],classList:{add(){}},append(...items){this.children.push(...items)}}}
 const ctx=vm.createContext({el:node,editorDirty:false});vm.runInContext(getFunction('field'),ctx);const parent=node();ctx.field(parent,'Asset number','P-101A',()=>{});assert.equal(parent.children[0].children[0].type,'text');assert.equal(parent.children[0].children[0].value,'P-101A');
});

test('yearly export omissions explain review, undated and earlier due months',()=>{
 const ctx=vm.createContext({active:a=>a.record_status!=='Archived',applicable:i=>i.applicable==='Yes'});vm.runInContext(getFunction('yearlyOmissions'),ctx);
 const records=[{id:'a',name:'A',inspections:[{inspection_type:'OSI',applicable:'Yes',review_status:'Review',next_inspection_month:'2027-04'},{inspection_type:'Internal',applicable:'Yes',next_inspection_month:null}]},{id:'b',name:'B',inspections:[{inspection_type:'OSI',applicable:'Yes',next_inspection_month:'2026-01'}]}];
 const report=ctx.yearlyOmissions(records,'2027','','',false);
 assert.deepEqual(Array.from(report,r=>r.reason),['Needs review','No next month / scheduling condition','Due before selected year; carry-over is off']);
});
test('editor field context shows only matching saved verification and issues and removes verification when edited',()=>{
 const ctx=vm.createContext({el:(tag,text,cls)=>({tag,textContent:text,className:cls,dataset:{}}),markFieldState(label,state,text){label.states.push([state,text])}});
 vm.runInContext(getFunction('decorateEditorField'),ctx);
 const listeners={},label={states:[],children:[],append(x){this.children.push(x)},closest(){return null},querySelector(selector){return selector.includes('verified')?{remove(){}}:null},addEventListener(k,fn){listeners[k]=fn},classList:{remove(){}}};
 ctx.decorateEditorField(label,'name',{fields:[{field:'name',verified:true}],version:3},[{field:'name',severity:'blocking',message:'Name needed'},{field:'family',message:'Other'}],3);
 assert.equal(label.states[0][0],'verified');assert.match(label.children[0].textContent,/Name needed/);assert.equal(label.children.length,1);
 listeners.input();assert.equal(label.states.at(-1)[0],'changed');
 const stale={...label,states:[],children:[]};ctx.decorateEditorField(stale,'name',{fields:[{field:'name',verified:true}],version:2},[],3);assert.equal(stale.states.length,0);
});

test('a recovered unsaved draft never labels its values as verified',()=>{
 const ctx=vm.createContext({editorDirty:true,el:()=>({}),markFieldState(label,state,text){label.states.push([state,text])}});
 vm.runInContext(getFunction('decorateEditorField'),ctx);
 const label={states:[],append(){},closest(){return null},addEventListener(){},classList:{remove(){}}};
 ctx.decorateEditorField(label,'name',{version:3,fields:[{field:'name',verified:true}]},[],3);
 assert.notEqual(label.states[0]?.[0],'verified');
});

test('new asset fields render without a verification response',()=>{
 const ctx=vm.createContext({editorDirty:false,el:()=>({}),markFieldState(){}});
 vm.runInContext(getFunction('decorateEditorField'),ctx);
 const label={append(){},closest(){return null},addEventListener(){}};
 assert.doesNotThrow(()=>ctx.decorateEditorField(label,'name',null,[],undefined));
});

test('service status highlights require an actual reconciliation update',()=>{
 assert.match(source,/recentReconUpdates\[id\]\?\.asset\?\.\[key\]!==undefined&&recentReconUpdates\[id\]\.asset\[key\]===editing\[key\]/);
});

test('dashboard separates condition schedules from inspections needing checking',()=>{
 function node(){return {value:'',children:[],dataset:{},classList:{add(){}},append(...xs){this.children.push(...xs)},replaceChildren(...xs){this.children=xs},setAttribute(){}}}
 const nodes={},queues=[];
 const ctx=vm.createContext({$:s=>nodes[s]??=node(),assets:[{name:'Condition',inspections:[{applicable:'Yes',scheduling_condition:'OOS'}]},{name:'Problem',inspections:[{applicable:'Yes',review_status:'Review',review_reason:'Missing schedule'}]}],Date,el:()=>node(),active:()=>true,applicable:i=>i.applicable==='Yes',currentMonth:()=> '2026-11',addMonths:()=> '2027-02',queuePanel(title,description,rows){queues.push({title,rows});return node()},renderSheetShortcuts(){}});
 vm.runInContext(getFunction('renderDashboard'),ctx);ctx.renderDashboard();
 assert.deepEqual(Array.from(queues.find(q=>q.title==='Needs a closer look').rows,r=>r[1].name),['Problem']);
 assert.deepEqual(Array.from(queues.find(q=>q.title==='Scheduled by condition').rows,r=>r[1].name),['Condition']);
});

test('register local review and attention filters agree with asset and schedule checks',()=>{
 const filters={search:'',sheet:'',status:'active',family:'',service:'','review-filter':'review','due-filter':'',period:'3'};
 const ctx=vm.createContext({$:s=>({value:filters[s.slice(1)]}),onlyRecentRecon:false,onlyConfirmedRecon:false,currentMonth:()=> '2026-11',addMonths:()=> '2027-02',applicable:i=>i.applicable==='Yes',active:()=>true,matchesAssetSearch:()=>true});
 vm.runInContext(getFunction('matches'),ctx);
 assert.equal(ctx.matches({quality_status:'Needs checking',asset_review_reasons:['Missing name']}),true);
 filters['review-filter']='';filters['due-filter']='attention';
 assert.equal(ctx.matches({inspections:[{applicable:'Yes',scheduling_condition:'OOS'}]}),false);
 assert.equal(ctx.matches({asset_review_reasons:['Missing name']}),true);
});

test('review comments mentioning month remain ordinary text controls',()=>{
 const ctx=vm.createContext({el:(tag,text)=>({tagName:tag,textContent:text,children:[],append(...xs){this.children.push(...xs)}}),editorDirty:false,monthEntry(){throw Error('Review item incorrectly became a date input')}});
 vm.runInContext(getFunction('field'),ctx);
 const parent={children:[],append(x){this.children.push(x)}};
 ctx.field(parent,'OSI: last inspection · No unambiguous month; original value retained for review.','Review',()=>{});
 assert.equal(parent.children[0].children[0].tagName,'input');
});

function editorSaveHarness(){
 const nodes={'#form':{},'#save-asset':{disabled:false},'#fields':{inert:false},'#editor':{close(){this.closed=(this.closed||0)+1}},'#edit-error':{textContent:''},'#quality':{hidden:true}};
 const requests=[];let resolve,reject;
 const ctx=vm.createContext({$:s=>nodes[s],editing:{name:'New',family:'Flowline'},editorDrafts:new Set(),editorDirty:true,editorGeneration:1,editorSavePending:false,
  prepareAssetForSave:asset=>({...asset}),api:(path,options)=>{requests.push({path,options});return new Promise((yes,no)=>{resolve=yes;reject=no})},
  discardEditorDraft(){ctx.discarded=(ctx.discarded||0)+1},load:async()=>{},renderAssets(){},message(text){ctx.notice=text}});
 const line=source.split('\n').find(row=>row.startsWith("$('#form').onsubmit="));assert.ok(line);vm.runInContext(line,ctx);
 return {ctx,nodes,requests,resolve:()=>resolve({}),reject:()=>reject(Error('Offline'))};
}
test('editor save ignores duplicate submissions while the request is pending',async()=>{
 const h=editorSaveHarness(),event={preventDefault(){}};
 const first=h.nodes['#form'].onsubmit(event),second=h.nodes['#form'].onsubmit(event);
 assert.equal(h.requests.length,1);assert.equal(h.nodes['#save-asset'].disabled,true);
 h.resolve();await Promise.all([first,second]);assert.equal(h.nodes['#save-asset'].disabled,false);assert.equal(h.nodes['#editor'].closed,1);
});
test('failed editor save retains the draft and permits retry',async()=>{
 const h=editorSaveHarness(),event={preventDefault(){}};
 const first=h.nodes['#form'].onsubmit(event);h.reject();await first;
 assert.equal(h.ctx.discarded,undefined);assert.equal(h.nodes['#editor'].closed,undefined);assert.match(h.nodes['#edit-error'].textContent,/Offline/);assert.equal(h.nodes['#save-asset'].disabled,false);
 const second=h.nodes['#form'].onsubmit(event);assert.equal(h.requests.length,2);h.resolve();await second;
});
test('late editor save cannot discard or close a different editor',async()=>{
 const h=editorSaveHarness(),event={preventDefault(){}};
 const pending=h.nodes['#form'].onsubmit(event);h.ctx.editorGeneration++;h.ctx.editing={id:'other',name:'Other',family:'Flowline'};
 h.resolve();await pending;assert.equal(h.ctx.discarded,undefined);assert.equal(h.nodes['#editor'].closed,undefined);assert.equal(h.ctx.editorDirty,true);
});

test('successful save reports success even before the dialog close event runs',async()=>{
 const h=editorSaveHarness(),pending=h.nodes['#form'].onsubmit({preventDefault(){}});
 h.resolve();await pending;assert.match(h.ctx.notice,/Asset saved/);
});
