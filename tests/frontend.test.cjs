const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('static/app.js','utf8');
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
