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
 const ctx=vm.createContext({assets:[],reconRows:[row],el:element,$:selector=>nodes[selector]??=(element('div')),reconConflict:()=>false,reconConflictReasons:()=>[],reconComparison:()=>({status:'incomplete',details:[]}),reconServiceComparison:()=>({status:'unavailable',sources:[],master:''}),reconRemarkComparison:()=>({status:'unavailable',incoming:[],master:[]}),active:()=>true,searchReconAssets:()=>[],assetDisplayName:a=>a.name,applicable:()=>true,localStorage:{setItem(){}},reconAliases:{},reconKey:()=>'',message(){},persistReconciliation(){},renderRecon(){}});
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
 const ctx=vm.createContext({assets:[],reconRows:[row],el:element,$:selector=>nodes[selector]??=element('div'),reconConflict:()=>false,reconConflictReasons:()=>[],reconComparison:()=>({status:'incomplete',details:[]}),reconServiceComparison:()=>({status:'unavailable',sources:[],master:''}),reconRemarkComparison:()=>({status:'unavailable',incoming:[],master:[]}),active:()=>true,searchReconAssets:()=>[],assetDisplayName:a=>a.name,applicable:()=>true,localStorage:{setItem(){}},reconAliases:{},reconKey:()=>'',message(){},persistReconciliation(){},renderRecon(){}});
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
 const ctx=vm.createContext({assets,reconRows:[row],el:element,$:s=>nodes[s]??=element('div'),reconConflict:()=>false,reconConflictReasons:()=>[],reconComparison:()=>({status:'incomplete',details:[]}),reconServiceComparison:()=>({status:'unavailable',sources:[],master:''}),reconRemarkComparison:()=>({status:'unavailable',incoming:[],master:[]}),active:()=>true,searchReconAssets:()=>[assets[1]],assetDisplayName:a=>a.name,applicable:()=>true,localStorage:{setItem(){}},reconAliases:{},reconKey:()=>'',message(){},persistReconciliation(){},renderRecon(){}});
 vm.runInContext(fn('openRecon'),ctx);ctx.openRecon(row);const input=controls.find(n=>n.placeholder==='Search by name, tag, asset number or location');input.value='Second';input.oninput();controls.find(n=>n.tagName==='button'&&n.children.some(c=>c.textContent==='Second')).onclick();controls.find(n=>n.textContent==='Confirm match and selected fields').onclick();assert.equal(row.chosen,'2');assert.equal(row.version,3);
});
test('conflict explanation identifies the other row and updates for the proposed asset',()=>{
 const a={row:20,identifier:'VEGE-NA-001',description:'Receiver',inspection_type:'Internal',chosen:'1',confirmed:true,candidates:[]};
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
 const ctx=vm.createContext({reconRows:[{row:4}],reconWorkbookName:'plan.xlsx',reconApplyChoices:new Map(),reconAliases:{},onlyConfirmedRecon:true,localStorage:{removeItem:k=>data.delete(k),setItem:(k,v)=>data.set(k,v)},confirm:()=>true,reconKey:()=>'',syncConfirmedReconHighlights(){},$:s=>nodes[s]??={value:'',hidden:false,disabled:false,textContent:'',replaceChildren(){}},message(){},renderAssets(){renders++}});
 vm.runInContext(fn('removeReconciliation'),ctx);ctx.removeReconciliation();assert.equal(data.has('inspection-reconciliation-v1'),false);assert.equal(ctx.reconRows.length,0);assert.equal(nodes['#recon-work'].hidden,true);assert.equal(nodes['#recon-review'].disabled,true);
});
test('cancelling workbook removal preserves the saved review',()=>{
 const data=new Map([['inspection-reconciliation-v1','saved']]);const rows=[{row:4}];const ctx=vm.createContext({reconRows:rows,localStorage:{removeItem:k=>data.delete(k)},confirm:()=>false});vm.runInContext(fn('removeReconciliation'),ctx);ctx.removeReconciliation();assert.equal(data.get('inspection-reconciliation-v1'),'saved');assert.equal(ctx.reconRows,rows);
});
