const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('static/reconciliation.js','utf8');
function fn(name){let start=source.indexOf('function '+name+'('),depth=0,open=false;assert.notEqual(start,-1);for(let i=source.indexOf('{',start);i<source.length;i++){if(source[i]==='{'){depth++;open=true}if(source[i]==='}'&&!--depth&&open)return source.slice(start,i+1)}throw Error('function not closed')}
function context(rows,assets){const ctx=vm.createContext({reconRows:rows,assets});for(const name of ['reconAsset','reconConflict','reconStatus'])vm.runInContext(fn(name),ctx);return ctx}
test('duplicate plan items stay conflicts even after confirming',()=>{const a={identifier:'V-1',inspection_type:'OSI',chosen:'1',confirmed:true,candidates:[]},b={...a};const ctx=context([a,b],[{id:'1',family:'Vessel'}]);assert.equal(ctx.reconStatus(a),'conflict');b.excluded=true;assert.equal(ctx.reconStatus(a),'confirmed')});
test('internal inspection matched to a line is a conflict',()=>{const row={identifier:'L1',inspection_type:'Internal',chosen:'1',confirmed:true,candidates:[]};const ctx=context([row],[{id:'1',family:'Flowline'}]);assert.equal(ctx.reconStatus(row),'conflict')});
test('opening a reconciliation row supports a remarks text area',()=>{
 const nodes={};let opened=false;
 function element(tag,text){let n={tagName:tag,textContent:text,value:'',children:[],setAttribute(){},scrollIntoView(){},append(...xs){this.children.push(...xs)},replaceChildren(...xs){this.children=xs},showModal(){opened=true}};Object.defineProperty(n,'firstChild',{get(){return this.children[0]}});Object.defineProperty(n,'type',{set(v){if(tag==='textarea')throw TypeError('textarea type is read-only')},get(){return ''}});return n}
 const row={row:3,identifier:'V1',description:'Vessel',scope:'OSI',inspection_type:'OSI',candidates:[],changes:{}};
 const ctx=vm.createContext({assets:[],reconRows:[row],el:element,$:selector=>nodes[selector]??=(element('div')),reconConflict:()=>false,reconConflictReasons:()=>[],reconComparison:()=>({status:'incomplete',details:[]}),reconMasterPreview:()=>({changes:{}}),reconServiceComparison:()=>({status:'unavailable',sources:[],master:''}),reconRemarkComparison:()=>({status:'unavailable',incoming:[],master:[]}),active:()=>true,searchReconAssets:()=>[],assetDisplayName:a=>a.name,applicable:()=>true,localStorage:{setItem(){}},reconAliases:{},reconKey:()=>'',message(){},persistReconciliation(){},renderRecon(){}});
 vm.runInContext(fn('openRecon'),ctx);ctx.openRecon(row);assert.equal(opened,true)
});
test('asset search matches multiple terms across identifiers and ignores archived assets',()=>{
 const ctx=vm.createContext({assets:[{id:'A01-0249',name:'Prod. Tank-T28',tag_original:'T28',record_status:'Active'},{id:'A01-0250',name:'Other tank',record_status:'Archived'}],active:a=>a.record_status!=='Archived',matchesAssetSearch:(a,q)=>q.toLowerCase().split(/\s+/).every(t=>[a.name,a.tag_original,a.id].join(' ').toLowerCase().includes(t))});
 vm.runInContext(fn('searchReconAssets'),ctx);
 assert.equal(ctx.searchReconAssets('tank t28').length,1);
 assert.equal(ctx.searchReconAssets('A01 0249').length,1);
 assert.equal(ctx.searchReconAssets('other').length,0);
});
test('changing the inspection type and closing review does not alter a saved decision',()=>{
 const nodes={};let controls=[];
 function element(tag,text){const n={tagName:tag,textContent:text,value:'',children:[],setAttribute(){},scrollIntoView(){},append(...xs){this.children.push(...xs)},replaceChildren(...xs){this.children=xs},showModal(){},close(){}};Object.defineProperty(n,'type',{set(){}});controls.push(n);return n}
 const row={row:3,identifier:'V1',description:'Vessel',scope:'OSI',inspection_type:'OSI',candidates:[],changes:{remark:'keep'},confirmed:true};
 const ctx=vm.createContext({assets:[],reconRows:[row],el:element,$:selector=>nodes[selector]??=element('div'),reconConflict:()=>false,reconConflictReasons:()=>[],reconComparison:()=>({status:'incomplete',details:[]}),reconMasterPreview:()=>({changes:{}}),reconServiceComparison:()=>({status:'unavailable',sources:[],master:''}),reconRemarkComparison:()=>({status:'unavailable',incoming:[],master:[]}),active:()=>true,searchReconAssets:()=>[],assetDisplayName:a=>a.name,applicable:()=>true,localStorage:{setItem(){}},reconAliases:{},reconKey:()=>'',message(){},persistReconciliation(){},renderRecon(){}});
 vm.runInContext(fn('openRecon'),ctx);ctx.openRecon(row);let scope=controls.find(n=>n.tagName==='select');scope.value='Internal';scope.onchange();
 assert.equal(row.inspection_type,'OSI');assert.equal(row.confirmed,true);assert.equal(row.changes.remark,'keep');
});
test('after a successful update reviewed rows remain confirmed and are ready for a new review',()=>{
 const row={confirmed:true,changes:{remark:'note'},version:1};const asset={id:'1',version:2};const ctx=vm.createContext({assets:[asset]});vm.runInContext(fn('completeReconUpdates'),ctx);ctx.completeReconUpdates([{row,asset}]);assert.equal(row.confirmed,true);assert.deepEqual(Object.keys(row.changes),[]);assert.equal(row.version,2);
});
test('different assets sharing a package are not treated as duplicate plan rows',()=>{
 const a={identifier:'OP',description:'Tank one',inspection_type:'OSI',chosen:'1',confirmed:true,candidates:[]},b={identifier:'OP',description:'Tank two',inspection_type:'OSI',chosen:'2',confirmed:true,candidates:[]};
 const ctx=context([a,b],[{id:'1',family:'Vessel'},{id:'2',family:'Vessel'}]);assert.equal(ctx.reconStatus(a),'confirmed');assert.equal(ctx.reconStatus(b),'confirmed');
});
test('pending-change and plan-year filters narrow reconciliation rows',()=>{
 const nodes={'#recon-search':{value:''},'#recon-status':{value:'pending'},'#recon-type':{value:''},'#recon-sheet':{value:''},'#recon-family':{value:''},'#recon-year':{value:'2026'},'#recon-category':{value:''},'#recon-comparison':{value:''},'#recon-service-comparison':{value:''},'#recon-remark-comparison':{value:''}};
 const rows=[{confirmed:true,changes:{remark:'note'},planned_month:'2026-05',candidates:[]},{confirmed:true,changes:{},planned_month:'2026-06',candidates:[]},{confirmed:true,changes:{remark:'note'},planned_month:'2025-05',candidates:[]}];
 const ctx=vm.createContext({reconRows:rows,$:s=>nodes[s],reconAsset:()=>null,reconStatus:()=> 'confirmed',reconScopedAsset:()=>true,reconDue:()=>''});vm.runInContext(fn('reconVisible'),ctx);
 assert.equal(ctx.reconVisible().length,1);assert.equal(ctx.reconVisible()[0],rows[0]);
});
test('choosing a different search result and confirming saves the new match',()=>{
 const nodes={},controls=[];function element(tag,text){const n={tagName:tag,textContent:text,value:'',children:[],setAttribute(){},scrollIntoView(){},append(...xs){this.children.push(...xs)},replaceChildren(...xs){this.children=xs},showModal(){},close(){}};Object.defineProperty(n,'type',{set(){}});controls.push(n);return n}
 const assets=[{id:'1',name:'First',family:'Vessel',version:1,inspections:[]},{id:'2',name:'Second',family:'Vessel',version:3,inspections:[]}];
 const row={row:3,identifier:'V1',description:'Vessel',scope:'OSI',inspection_type:'OSI',chosen:'1',confirmed:true,candidates:[],changes:{}};
 const ctx=vm.createContext({assets,reconRows:[row],el:element,$:s=>nodes[s]??=element('div'),reconConflict:()=>false,reconConflictReasons:()=>[],reconComparison:()=>({status:'incomplete',details:[]}),reconMasterPreview:()=>({changes:{}}),reconServiceComparison:()=>({status:'unavailable',sources:[],master:''}),reconRemarkComparison:()=>({status:'unavailable',incoming:[],master:[]}),active:()=>true,searchReconAssets:()=>[assets[1]],assetDisplayName:a=>a.name,applicable:()=>true,localStorage:{setItem(){}},reconAliases:{},reconKey:()=>'',message(){},persistReconciliation(){},renderRecon(){}});
 vm.runInContext(fn('openRecon'),ctx);ctx.openRecon(row);const input=controls.find(n=>n.placeholder==='Search by name, tag, asset number or location');input.value='Second';input.oninput();controls.find(n=>n.tagName==='button'&&n.children.some(c=>c.textContent==='Second')).onclick();controls.find(n=>n.textContent==='Confirm match and selected fields').onclick();assert.equal(row.chosen,'2');assert.equal(row.version,3);
});
test('conflict explanation identifies the other row and updates for the proposed asset',()=>{
 const a={completion_status:'done',row:20,identifier:'VEGE-NA-001',description:'Receiver',inspection_type:'Internal',chosen:'1',confirmed:true,candidates:[]};
 const b={row:34,identifier:'VEGE-NA-001',description:'Air receiver',inspection_type:'Internal',chosen:'1',confirmed:false,candidates:[],planned_month:'2025-12'};
 const ctx=vm.createContext({reconRows:[a,b],assets:[{id:'1',family:'Vessel'},{id:'2',family:'Vessel'}]});vm.runInContext(fn('reconConflictReasons'),ctx);
 assert.match(ctx.reconConflictReasons(a,'1','Internal').join(' '),/row 34/i);
 assert.match(ctx.reconConflictReasons(a,'1','Internal').join(' '),/2025-12/);
 assert.equal(ctx.reconConflictReasons(a,'2','Internal').length,0);
});
test('saved reconciliation restores reviewed rows and pending field changes',()=>{
 const data=new Map(),storage={setItem:(k,v)=>data.set(k,v),getItem:k=>data.get(k)||null};
 const rows=[{row:20,confirmed:true,chosen:'a',version:7,changes:{next_inspection_month:'2026-06'},candidates:[]}];
 const ctx=vm.createContext({localStorage:storage,reconRows:rows,reconWorkbookName:'plan.xlsx'});
 vm.runInContext(fn('saveReconciliation'),ctx);vm.runInContext(fn('readReconciliation'),ctx);ctx.saveReconciliation();const saved=ctx.readReconciliation();
 assert.equal(saved.name,'plan.xlsx');assert.equal(saved.rows[0].changes.next_inspection_month,'2026-06');assert.equal(saved.rows[0].version,7);
});
test('a saved pending change is blocked if the master asset has changed',()=>{
 const row={row:3,inspection_type:'OSI',chosen:'1',confirmed:true,version:2,changes:{remark:'note'},candidates:[]};
 const ctx=context([row],[{id:'1',family:'Vessel',version:3}]);assert.equal(ctx.reconStatus(row),'conflict');
});
test('comparison distinguishes matching, differing and incomplete dates',()=>{
 const ctx=vm.createContext({applicable:i=>i.applicable==='Yes'});vm.runInContext(fn('reconComparison'),ctx);
 const asset={inspections:[{inspection_type:'Internal',applicable:'Yes',last_inspection_month:'2018-10',next_inspection_month:'2024-10'}]};
 const row={inspection_type:'Internal',last_month:'2018-10',planned_month:'2024-10'};
 assert.equal(ctx.reconComparison(row,asset).status,'agree');
 assert.equal(ctx.reconComparison({...row,planned_month:'2025-01'},asset).status,'different');
 assert.equal(ctx.reconComparison({...row,last_month:null},asset).status,'incomplete');
 assert.equal(ctx.reconComparison(row,{inspections:[]}).status,'incomplete');
});
test('comparison does not treat review-flagged master dates as confirmed agreement',()=>{
 const ctx=vm.createContext({applicable:i=>i.applicable==='Yes'});vm.runInContext(fn('reconComparison'),ctx);
 const row={inspection_type:'OSI',last_month:'2020-01',planned_month:'2026-01'},asset={inspections:[{inspection_type:'OSI',applicable:'Yes',review_status:'Review',last_inspection_month:'2020-01',next_inspection_month:'2026-01'}]};
 assert.equal(ctx.reconComparison(row,asset).status,'incomplete');
});
test('an exact suggested match shows whether dates agree or differ without confirming it',()=>{
 const row={identifier:'V1',description:'Vessel',inspection_type:'Internal',chosen:'1',confirmed:false,candidates:[{evidence:'Exact asset number'}],last_month:'2018-10',planned_month:'2024-10'};
 const asset={id:'1',family:'Vessel',inspections:[{inspection_type:'Internal',applicable:'Yes',last_inspection_month:'2018-10',next_inspection_month:'2024-10'}]};
 const ctx=context([row],[asset]);ctx.applicable=i=>i.applicable==='Yes';vm.runInContext(fn('reconComparison'),ctx);
 assert.equal(ctx.reconStatus(row),'agree');asset.inspections[0].next_inspection_month='2025-01';assert.equal(ctx.reconStatus(row),'different');assert.equal(row.confirmed,false);
});
test('remarks compare both incoming columns against each master note without assuming partial matches',()=>{
 const ctx=vm.createContext({});vm.runInContext(fn('reconRemarkComparison'),ctx);
 const asset={notes:[{note_type:'Finding',note_text:'Existing remark'},{note_type:'Remark',note_text:'Other note'}]};
 assert.equal(ctx.reconRemarkComparison({remarks:'  existing  remark  ',final_remarks:'Other note'},asset).status,'agree');
 assert.equal(ctx.reconRemarkComparison({remarks:'Existing remark',final_remarks:'New detail'},asset).status,'different');
 assert.equal(ctx.reconRemarkComparison({remarks:''},asset).status,'unavailable');
 assert.equal(ctx.reconRemarkComparison({remarks:'Existing'},asset).status,'different');
});
test('service comparison handles explicit statuses without guessing from ambiguous text',()=>{
 const ctx=vm.createContext({});for(const name of ['reconServiceValue','reconServiceComparison'])vm.runInContext(fn(name),ctx);
 assert.equal(ctx.reconServiceComparison({progress:'OUT OF SURVICE',report:''},{service_status_original:'OOS'}).status,'agree');
 assert.equal(ctx.reconServiceComparison({progress:'Out of service'},{service_status_original:'In service'}).status,'different');
 assert.equal(ctx.reconServiceComparison({progress:'',report:''},{service_status_original:'OOS'}).status,'unavailable');
 assert.equal(ctx.reconServiceComparison({progress:'out of service',report:'in service'},{service_status_original:'OOS'}).status,'unclear');
 assert.equal(ctx.reconServiceComparison({progress:'inspection in progress'},{service_status_original:'Yes'}).status,'unavailable');
});
test('selecting a status pill clears other filters and toggles the chosen status',()=>{
 const controls=Object.fromEntries(['recon-search','recon-status','recon-sheet','recon-family','recon-type','recon-year','recon-category','recon-comparison','recon-service-comparison','recon-remark-comparison'].map(id=>['#'+id,{value:'old'}]));let renders=0;
 const ctx=vm.createContext({$:s=>controls[s],renderRecon:()=>renders++});vm.runInContext(fn('filterReconStatus'),ctx);
 ctx.filterReconStatus('confirmed');assert.equal(controls['#recon-status'].value,'confirmed');assert.equal(controls['#recon-search'].value,'');assert.equal(controls['#recon-comparison'].value,'');
 ctx.filterReconStatus('confirmed');assert.equal(controls['#recon-status'].value,'');assert.equal(renders,2);
});
test('final review applies only the checked rows and leaves the rest staged',()=>{
 const a={row:3,confirmed:true,changes:{remark:'first'},version:1},b={row:4,confirmed:true,changes:{remark:'second'},version:1};
 const ctx=vm.createContext({reconApplyChoices:new Map([[a,true],[b,false]]),selectedReconUpdates:()=>[{row:a,asset:{id:'a'}},{row:b,asset:{id:'b'}}]});
 vm.runInContext(fn('checkedReconUpdates'),ctx);vm.runInContext(fn('completeReconUpdates'),ctx);
 const chosen=ctx.checkedReconUpdates();assert.equal(chosen.length,1);assert.equal(chosen[0].row,a);ctx.completeReconUpdates(chosen);assert.equal(b.changes.remark,'second');assert.equal(b.version,1);
});
test('removing a workbook clears its saved review without touching the master',()=>{
 const data=new Map([['inspection-reconciliation-v1','saved']]),nodes={};let renders=0;
 const ctx=vm.createContext({reconRows:[{row:4}],reconWorkbookName:'plan.xlsx',reconApplyChoices:new Map(),reconAliases:{},onlyConfirmedRecon:true,localStorage:{removeItem:k=>data.delete(k),setItem:(k,v)=>data.set(k,v)},confirm:()=>true,reconKey:()=>'',syncConfirmedReconHighlights(){},updateReconBatchActions(){},$:s=>nodes[s]??={value:'',hidden:false,disabled:false,textContent:'',replaceChildren(){}},message(){},renderAssets(){renders++}});
 vm.runInContext(fn('removeReconciliation'),ctx);ctx.removeReconciliation();assert.equal(data.has('inspection-reconciliation-v1'),false);assert.equal(ctx.reconRows.length,0);assert.equal(nodes['#recon-work'].hidden,true);assert.equal(nodes['#recon-review'].disabled,true);
});
test('cancelling workbook removal preserves the saved review',()=>{
 const data=new Map([['inspection-reconciliation-v1','saved']]);const rows=[{row:4}];const ctx=vm.createContext({reconRows:rows,localStorage:{removeItem:k=>data.delete(k)},confirm:()=>false});vm.runInContext(fn('removeReconciliation'),ctx);ctx.removeReconciliation();assert.equal(data.get('inspection-reconciliation-v1'),'saved');assert.equal(ctx.reconRows,rows);
});

test('complete review export retains hidden rows and every proposed field',()=>{
 const rows=[{row:2,description:'Tank',chosen:'a',inspection_type:'OSI',confirmed:true,excluded:false,version:7,changes:{last_inspection_month:'2026-01',next_inspection_month:'2027-02',service_status_original:'Out of service',remark:'Manual, "note"\nsecond line'},candidates:[]},{row:3,description:'Hidden by filter',confirmed:false,excluded:true,candidates:[],changes:{remark:'Keep hidden note'}}];
 const ctx=vm.createContext({reconRows:rows,reconAsset:r=>r.chosen?{id:'a',name:'Tank'}:null,reconDue:()=>'',reconStatus:()=> 'confirmed',reconLabel:x=>x});
 vm.runInContext(fn('reconciliationExportRows'),ctx);
 const [header,...exported]=ctx.reconciliationExportRows();
 assert.equal(exported.length,2);
 const record=Object.fromEntries(header.map((h,i)=>[h,exported[0][i]]));
 assert.equal(record['Selected last inspection month'],'2026-01');assert.equal(record['Selected next inspection month'],'2027-02');
 assert.equal(record['Selected service status'],'Out of service');assert.equal(record['Selected remark'],rows[0].changes.remark);
 assert.equal(record['Master version at confirmation'],7);assert.equal(record['Confirmed'],true);
 assert.equal(exported[1][header.indexOf('Selected remark')],'Keep hidden note');
});

test('complete review export retains the missing-from-plan worklist',()=>{
 const ctx=vm.createContext({reconRows:[],reconAsset:()=>null,reconDue:()=>'',reconStatus:()=>'',reconLabel:x=>x});
 vm.runInContext(fn('reconciliationExportRows'),ctx);
 const [header,...rows]=ctx.reconciliationExportRows([{asset:{id:'absent',name:'Unplanned tank'},inspection:{inspection_type:'OSI',next_inspection_month:'2027-01'}}]);
 assert.equal(rows.length,1);assert.equal(rows[0][header.indexOf('Status')],'Missing from plan');
 assert.equal(rows[0][header.indexOf('Matched asset ID')],'absent');assert.equal(rows[0][header.indexOf('Master due month')],'2027-01');
});

test('downloaded review CSV keeps multiline selected remarks and escapes formulas',async()=>{
 let downloaded,clicked=false;const nodes={'#recon-export':{},'#recon-status':{value:'pending'}};
 const row={row:2,description:'=SUM(A1)',confirmed:true,changes:{remark:'Manual, "note"\nsecond line'},candidates:[]};
 const ctx=vm.createContext({reconRows:[row],$:s=>nodes[s],reconAsset:()=>null,reconDue:()=>'',reconStatus:()=> 'confirmed',reconLabel:x=>x,Blob,URL:{createObjectURL:b=>{downloaded=b;return 'blob:test'},revokeObjectURL(){}},el:()=>({click(){clicked=true}}),setTimeout(){}});
 vm.runInContext(fn('reconciliationExportRows'),ctx);
 vm.runInContext(source.slice(source.indexOf("$('#recon-export').onclick="),source.indexOf('\n\nfunction completeReconUpdates')),ctx);
 nodes['#recon-export'].onclick();assert.equal(clicked,true);const csv=await downloaded.text();
 assert.ok(csv.includes('"Selected remark"'));assert.ok(csv.includes('"Manual, ""note""\nsecond line"'));assert.ok(csv.includes('"\'=SUM(A1)"'));
});

test('batch date proposals skip old, invalid, ambiguous and planned-only results',()=>{
 const asset={id:'1',version:12,family:'Vessel',inspections:[{inspection_type:'OSI',applicable:'Yes',last_inspection_month:'2025-02',next_inspection_month:'2026-02'}]};
 const row={completion_status:'done',chosen:'1',inspection_type:'OSI',last_month:'2026-09',next_month:'2028-09',candidates:[{evidence:'Exact tag'}]};
 const ctx=vm.createContext({assets:[asset],reconRows:[row],active:()=>true,applicable:i=>i.applicable==='Yes'});
 for(const name of ['reconAsset','reconConflict','reconRemarkComparison','reconServiceValue','reconServiceComparison','reconMasterPreview','reconBatchProposal','reconStatus'])vm.runInContext(fn(name),ctx);
 assert.equal(ctx.reconBatchProposal(row).status,'update_available');
 assert.deepEqual(JSON.parse(JSON.stringify(ctx.reconBatchProposal(row).fields)),{last_inspection_month:'2026-09',next_inspection_month:'2028-09'});
 row.last_month='2024-01';assert.equal(ctx.reconBatchProposal(row).status,'up_to_date');
 row.last_month=null;row.planned_month='2026-09';assert.equal(ctx.reconBatchProposal(row).status,'needs_review');
 row.last_month='2026-09';row.next_original='2028';row.next_month=null;assert.equal(ctx.reconBatchProposal(row).status,'needs_review');
 row.next_original='';row.next_month='2028-09';row.ambiguous=true;assert.equal(ctx.reconBatchProposal(row).status,'needs_review');
 row.ambiguous=false;row.last_month='2025-02';row.next_month='2026-02';assert.equal(ctx.reconStatus(row),'up_to_date');
 row.last_month='2026-09';row.next_month='2026-01';assert.equal(ctx.reconBatchProposal(row).status,'needs_review');
});
test('batch completion uses authoritative revisions for multiple assets',()=>{
 const rows=[{chosen:'a',version:4,changes:{last_inspection_month:'2026-09'}},{chosen:'b',version:8,changes:{last_inspection_month:'2026-09'}}];
 const ctx=vm.createContext({});vm.runInContext(fn('completeReconUpdates'),ctx);ctx.completeReconUpdates(rows.map(row=>({row})),{a:19,b:20});
 assert.equal(rows[0].version,19);assert.equal(rows[1].version,20);
});
test('preparing a batch respects visible rows and preserves manual proposals',()=>{
 const ready={chosen:'a'},hidden={chosen:'b'},manual={chosen:'c',confirmed:true,changes:{remark:'keep'}};
 let saved=0,rendered=0;
 const ctx=vm.createContext({reconVisible:()=>[ready,manual],reconBatchProposal:()=>({status:'update_available',fields:{last_inspection_month:'2026-09'}}),reconAsset:()=>({version:42}),persistReconciliation:()=>saved++,renderRecon:()=>rendered++,message:()=>{}});
 vm.runInContext(fn('prepareReconBatch'),ctx);ctx.prepareReconBatch();
 assert.equal(ready.confirmed,true);assert.equal(ready.version,42);assert.equal(ready.changes.last_inspection_month,'2026-09');assert.equal(hidden.confirmed,undefined);assert.equal(manual.changes.remark,'keep');assert.equal(saved,1);assert.equal(rendered,1);
});
test('dates require completion in incoming workbook, not confirmation of the match',()=>{
 const asset={id:'a',version:1,family:'Vessel',inspections:[{inspection_type:'OSI',applicable:'Yes',last_inspection_month:'2020-01'}]};
 const row={chosen:'a',inspection_type:'OSI',last_month:'2026-09',next_month:null,candidates:[{evidence:'Exact tag'}],confirmed:true,version:1};
 const ctx=vm.createContext({assets:[asset],reconRows:[row],active:()=>true,applicable:()=>true});
 for(const name of ['reconAsset','reconConflict','reconRemarkComparison','reconServiceValue','reconServiceComparison','reconMasterPreview','reconBatchProposal'])vm.runInContext(fn(name),ctx);
 assert.equal(ctx.reconBatchProposal(row).status,'needs_review');
 row.completion_status='not_done';assert.equal(ctx.reconBatchProposal(row).status,'not_done');
 row.completion_status='done';assert.equal(ctx.reconBatchProposal(row).status,'update_available');
 row.changes={last_inspection_month:'2026-09'};row.completion_status='not_done';assert.equal(ctx.reconConflict(row),true);
});

test('master preview highlights incoming differences without altering row decisions or asset values',()=>{
 const asset={id:'a',service_status_original:'In service',inspections:[{inspection_type:'OSI',last_inspection_month:'2020-01',next_inspection_month:'2027-01'},{inspection_type:'Internal',last_inspection_month:'2026-09'}]};
 const row={row:5,chosen:'a',completion_status:'not_done',last_month:'2026-09',next_month:'2027-01',confirmed:false,changes:{}};
 const ctx=vm.createContext({});vm.runInContext(fn('reconServiceValue'),ctx);vm.runInContext(fn('reconRemarkComparison'),ctx);vm.runInContext(fn('reconMasterPreview'),ctx);
 const preview=ctx.reconMasterPreview(row,asset,'OSI');
 assert.equal(preview.previewOnly,true);assert.deepEqual(JSON.parse(JSON.stringify(preview.changes)),{last_inspection_month:'2026-09'});
 assert.equal(asset.inspections[0].last_inspection_month,'2020-01');assert.equal(row.confirmed,false);assert.deepEqual(row.changes,{});
 row.changes={next_inspection_month:'2028-01',remark:'Selected remark'};
 const selected=ctx.reconMasterPreview(row,asset,'Internal');assert.equal(selected.previewOnly,false);assert.equal(selected.inspection_type,'Internal');assert.equal(selected.changes.next_inspection_month,'2028-01');assert.equal(selected.changes.remark,'Selected remark');
});
test('batch toolbar counts visible eligibility separately from all prepared rows',()=>{
 const nodes={'#recon-status':{value:''},'#recon-prepare-batch':{},'#recon-review':{},'#recon-batch-status':{}};
 const ctx=vm.createContext({reconRows:[{},{}],$:id=>nodes[id],reconVisible:()=>[{confirmed:false},{confirmed:true,changes:{remark:'kept'}}],reconBatchProposal:()=>({status:'update_available'}),selectedReconUpdates:()=>[{},{}]});
 vm.runInContext(fn('updateReconBatchActions'),ctx);ctx.updateReconBatchActions();
 assert.equal(nodes['#recon-prepare-batch'].disabled,false);assert.equal(nodes['#recon-review'].disabled,false);assert.match(nodes['#recon-batch-status'].textContent,/1 eligible.*2 prepared/);
 nodes['#recon-status'].value='missing';ctx.updateReconBatchActions();assert.equal(nodes['#recon-prepare-batch'].disabled,true);
});

test('master preview includes service and both remarks even when only a date was selected',()=>{
 const asset={service_status_original:'In service',inspections:[{inspection_type:'OSI',last_inspection_month:'2020-01'}],notes:[{note_text:'Existing remark'}]};
 const row={last_month:'2026-09',service_status:'Out of service',remarks:'New scope remark',final_remarks:'New final remark',changes:{last_inspection_month:'2026-09'}};
 const ctx=vm.createContext({});for(const name of ['reconServiceValue','reconRemarkComparison','reconMasterPreview'])vm.runInContext(fn(name),ctx);
 const preview=ctx.reconMasterPreview(row,asset,'OSI');
 assert.equal(preview.changes.service_status_original,'Out of service');
 assert.deepEqual(JSON.parse(JSON.stringify(preview.remarkPreviews)),[{text:'New scope remark',selected:false},{text:'New final remark',selected:false}]);
 assert.deepEqual(JSON.parse(JSON.stringify(preview.selectedFields)),['last_inspection_month']);
 assert.equal(row.changes.service_status_original,undefined);assert.equal(asset.service_status_original,'In service');
 row.changes.remark='Manually selected note';const selected=ctx.reconMasterPreview(row,asset,'OSI');
 assert.equal(selected.remarkPreviews[0].text,'Manually selected note');assert.equal(selected.remarkPreviews[0].selected,true);assert.equal(selected.remarkPreviews.length,3);
});
test('master preview omits identical remarks and statuses and avoids guessing conflicting service statuses',()=>{
 const asset={service_status_original:'OOS',notes:[{note_text:' Existing   remark '}]};
 const ctx=vm.createContext({});for(const name of ['reconServiceValue','reconRemarkComparison','reconMasterPreview'])vm.runInContext(fn(name),ctx);
 let preview=ctx.reconMasterPreview({progress:'Out of service',remarks:'existing remark',final_remarks:'EXISTING REMARK'},asset,'OSI');
 assert.deepEqual(Object.keys(preview.changes),[]);assert.equal(preview.remarkPreviews.length,0);
 preview=ctx.reconMasterPreview({progress:'In service',report:'Out of service'},asset,'OSI');assert.equal(preview.changes.service_status_original,undefined);
 preview=ctx.reconMasterPreview({service_status:'Maintenance'},{service_status_original:'Maintenance'},'OSI');assert.equal(preview.changes.service_status_original,undefined);
});

test('a row leaves active reconciliation only after every source proposal is applied',()=>{
 const row={row:2,chosen:'a',completion_status:'done',inspection_type:'OSI',last_month:'2026-09',next_month:'2028-09',service_status:'Out of service',remarks:'Scope detail',final_remarks:'Final detail',changes:{last_inspection_month:'2026-09'}};
 const asset={id:'a',inspections:[{inspection_type:'OSI',last_inspection_month:'2026-09',next_inspection_month:'2028-09'}],service_status_original:'In service',notes:[]};
 const ctx=vm.createContext({});for(const name of ['reconServiceValue','reconRemarkComparison','reconMasterPreview','completeReconUpdates','reconRowFinished'])vm.runInContext(fn(name),ctx);
 assert.equal(ctx.reconRowFinished(row,asset),false);
 ctx.completeReconUpdates([{row}],{a:20});assert.equal(ctx.reconRowFinished(row,asset),false);
 asset.service_status_original='Out of service';asset.notes=[{note_text:'Scope detail'}];assert.equal(ctx.reconRowFinished(row,asset),false);
 asset.notes.push({note_text:'Final detail'});assert.equal(ctx.reconRowFinished(row,asset),true);
 row.completion_status='not_done';assert.equal(ctx.reconRowFinished(row,asset),false);
});
test('completed rows stay available in history while disappearing from default filters',()=>{
 const nodes={};for(const key of ['search','status','type','year','category','comparison','service-comparison','remark-comparison','sheet','family'])nodes['#recon-'+key]={value:''};
 const completed={completed:true,candidates:[]},pending={completed:false,candidates:[]};
 const ctx=vm.createContext({reconRows:[completed,pending],$:id=>nodes[id],reconAsset:()=>null,reconStatus:row=>row.completed?'completed':'not_done'});
 vm.runInContext(fn('reconVisible'),ctx);assert.equal(ctx.reconVisible().length,1);assert.equal(ctx.reconVisible()[0],pending);
 nodes['#recon-status'].value='completed';assert.equal(ctx.reconVisible().length,1);assert.equal(ctx.reconVisible()[0],completed);
});

test('identical incoming remarks do not need completion evidence or manual confirmation',()=>{
 const asset={id:'a',family:'Vessel',inspections:[{inspection_type:'OSI',applicable:'Yes',last_inspection_month:'2026-09',next_inspection_month:'2028-09'}],notes:[{note_text:'Existing remark'}]};
 const row={chosen:'a',inspection_type:'OSI',candidates:[{evidence:'Exact tag'}],next_month:null,last_month:null,remarks:' existing   REMARK ',completion_status:'unknown'};
 const ctx=vm.createContext({assets:[asset],reconRows:[row],active:()=>true,applicable:()=>true});
 for(const name of ['reconAsset','reconConflict','reconServiceValue','reconServiceComparison','reconRemarkComparison','reconMasterPreview','reconBatchProposal','reconStatus','reconNeedsAttention'])vm.runInContext(fn(name),ctx);
 assert.equal(ctx.reconStatus(row),'up_to_date');assert.equal(ctx.reconNeedsAttention(row),false);
 row.last_month='2026-09';row.next_month='2028-09';assert.equal(ctx.reconStatus(row),'up_to_date');assert.equal(ctx.reconNeedsAttention(row),false);
 row.last_month='2026-10';assert.notEqual(ctx.reconStatus(row),'up_to_date');
});
test('whole matching remarks compare consistently whether stored combined or separately',()=>{
 const ctx=vm.createContext({});for(const name of ['reconServiceValue','reconRemarkComparison','reconMasterPreview'])vm.runInContext(fn(name),ctx);
 const row={remarks:'Scope detail',final_remarks:'Final detail'};
 const asset={notes:[{note_text:'Scope detail\nFinal detail'}]};
 assert.equal(ctx.reconRemarkComparison(row,asset).status,'agree');assert.equal(ctx.reconMasterPreview(row,asset,'OSI').remarkPreviews.length,0);
 assert.equal(ctx.reconRemarkComparison({remarks:'Scope detail\nFinal detail'},{notes:[{note_text:'Scope detail'},{note_text:'Final detail'}]}).status,'agree');
 assert.equal(ctx.reconRemarkComparison({remarks:'Scope'},{notes:[{note_text:'Scope detail'}]}).status,'different');
});

test('unchanged selected values clear themselves without masking stale real changes',()=>{
 const row={chosen:'a',version:1,confirmed:true,inspection_type:'OSI',completion_status:'done',last_month:'2026-09',next_month:null,remarks:'Scope detail',final_remarks:'Final detail',candidates:[{evidence:'Exact tag'}],changes:{last_inspection_month:'2026-09',remark:'Scope detail\nFinal detail',service_status_original:' MAINTENANCE '}};
 const asset={id:'a',version:9,family:'Vessel',service_status_original:'maintenance',inspections:[{inspection_type:'OSI',applicable:'Yes',last_inspection_month:'2026-09'}],notes:[{note_text:'Scope detail'},{note_text:'Final detail'}]};
 const ctx=vm.createContext({reconRows:[row],assets:[asset],active:()=>true,applicable:()=>true});
 for(const name of ['reconAsset','reconConflict','reconServiceValue','reconRemarkComparison','reconServiceComparison','reconMasterPreview','pruneReconNoops','reconBatchProposal','reconStatus','reconNeedsAttention'])vm.runInContext(fn(name),ctx);
 ctx.pruneReconNoops(row,asset);assert.deepEqual(Object.keys(row.changes),[]);assert.equal(ctx.reconStatus(row),'up_to_date');assert.equal(ctx.reconNeedsAttention(row),false);assert.equal(asset.version,9);
 row.changes={last_inspection_month:'2026-10'};ctx.pruneReconNoops(row,asset);assert.equal(ctx.reconStatus(row),'conflict');assert.equal(ctx.reconNeedsAttention(row),true);
});
test('blank next due and matching opaque service status do not create review work',()=>{
 const asset={id:'a',family:'Vessel',service_status_original:' Maintenance ',inspections:[{inspection_type:'OSI',applicable:'Yes',last_inspection_month:'2026-09'}],notes:[]};
 const row={chosen:'a',inspection_type:'OSI',candidates:[{evidence:'Exact tag'}],last_month:'2026-09',next_month:null,service_status:'maintenance',completion_status:'unknown'};
 const ctx=vm.createContext({assets:[asset],reconRows:[row],active:()=>true,applicable:()=>true});
 for(const name of ['reconAsset','reconConflict','reconServiceValue','reconRemarkComparison','reconServiceComparison','reconMasterPreview','reconBatchProposal','reconStatus','reconNeedsAttention'])vm.runInContext(fn(name),ctx);
 assert.equal(ctx.reconStatus(row),'up_to_date');assert.equal(ctx.reconNeedsAttention(row),false);
 row.last_original='not a date';row.last_month=null;assert.equal(ctx.reconStatus(row),'needs_review');
});
test('matching remarks alone need no applicable inspection until date changes are proposed',()=>{
 const asset={id:'a',family:'Vessel',inspections:[],notes:[{note_text:'Already recorded'}]};
 const row={chosen:'a',inspection_type:'OSI',candidates:[{evidence:'Exact tag'}],last_month:null,next_month:null,remarks:'Already recorded'};
 const ctx=vm.createContext({reconRows:[row],assets:[asset],active:()=>true,applicable:()=>false});
 for(const name of ['reconAsset','reconConflict','reconServiceValue','reconRemarkComparison','reconServiceComparison','reconMasterPreview','reconBatchProposal','reconStatus'])vm.runInContext(fn(name),ctx);
 assert.equal(ctx.reconStatus(row),'up_to_date');row.last_month='2026-09';assert.equal(ctx.reconStatus(row),'needs_review');
});
test('retained master paragraphs match without discarding later history or matching partial sentences',()=>{
 const ctx=vm.createContext({});vm.runInContext(fn('reconRemarkComparison'),ctx);
 const asset={notes:[{note_text:'Insulation in bad condition.\nCheck nozzles for CUI.\n\nLater inspection history and notes.'}]};
 assert.equal(ctx.reconRemarkComparison({remarks:'Insulation in bad condition.\nCheck nozzles for CUI'},asset).status,'agree');
 assert.equal(ctx.reconRemarkComparison({remarks:'Insulation in bad condition'},asset).status,'different');
});
test('newer master dates produce no downgrade proposal, including saved selections',()=>{
 const asset={id:'a',family:'Vessel',inspections:[{inspection_type:'OSI',applicable:'Yes',last_inspection_month:'2026-04',next_inspection_month:'2036-03'}],notes:[]};
 const row={chosen:'a',inspection_type:'OSI',last_month:'2021-04',next_month:'2030-04',candidates:[{evidence:'Exact tag'}],completion_status:'done',changes:{last_inspection_month:'2021-04',next_inspection_month:'2030-04'}};
 const ctx=vm.createContext({assets:[asset],reconRows:[row],active:()=>true,applicable:()=>true});
 for(const name of ['reconAsset','reconConflict','reconServiceValue','reconRemarkComparison','reconServiceComparison','reconMasterPreview','pruneReconNoops','reconBatchProposal','reconStatus','reconNeedsAttention'])vm.runInContext(fn(name),ctx);
 assert.equal(Object.keys(ctx.reconMasterPreview(row,asset,'OSI').changes).length,0);ctx.pruneReconNoops(row,asset);assert.equal(Object.keys(row.changes).length,0);assert.equal(ctx.reconStatus(row),'up_to_date');assert.equal(ctx.reconNeedsAttention(row),false);
 row.last_date_role='historical';row.last_month=null;row.last_original='2016';row.next_month=null;assert.equal(ctx.reconStatus(row),'up_to_date');
});
test('duplicate source rows already reflected in the master require no duplicate review',()=>{
 const asset={id:'a',family:'Vessel',inspections:[{inspection_type:'OSI',applicable:'Yes',last_inspection_month:'2026-04'}]};
 const row={identifier:'V1',description:'Vessel',chosen:'a',inspection_type:'OSI',last_month:'2021-04',next_month:null,candidates:[{evidence:'Exact tag'}],completion_status:'done'};
 const duplicate={...row};const ctx=vm.createContext({reconRows:[row,duplicate],assets:[asset],active:()=>true,applicable:()=>true});
 for(const name of ['reconAsset','reconServiceValue','reconRemarkComparison','reconServiceComparison','reconMasterPreview','reconConflict','reconBatchProposal','reconStatus','reconNeedsAttention'])vm.runInContext(fn(name),ctx);
 assert.equal(ctx.reconStatus(row),'up_to_date');assert.equal(ctx.reconNeedsAttention(row),false);
 duplicate.last_month='2027-04';assert.equal(ctx.reconStatus(duplicate),'conflict');
});
