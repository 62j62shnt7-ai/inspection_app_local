const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('static/quality.js','utf8');
test('verification selection includes only explicitly checked field names',()=>{
 const ctx=vm.createContext({});vm.runInContext(source,ctx);
 assert.deepEqual(Array.from(ctx.checkedVerificationFields([{checked:true,value:'name'},{checked:false,value:'family'}])),['name']);
});

test('quality issues label warning and blocking severity with actionable rows',()=>{
 const nodes={};function node(tag='div',text=''){return {tagName:tag,textContent:text,children:[],className:'',style:{},append(...items){this.children.push(...items)},replaceChildren(...items){this.children=items},setAttribute(){}}}
 let openedAsset;const ctx=vm.createContext({assets:[{id:"a",name:"Vessel 101"}],assetDisplayName:a=>a.name,qualityState:{page:1,pages:1,filtered_issue_count:2,quality:{issues:[{severity:'blocking',asset_id:'a',field:'name',message:'Missing description',rule_id:'required'},{severity:'warning',asset_id:'b',field:'name',message:'Check source',rule_id:'source-review'}],issue_count:2,affected_assets:2,revision:1},readiness:{eligible_count:0,excluded_count:2,excluded:[]}},$:selector=>nodes[selector]??=node(),el:(tag,text,cls)=>{const n=node(tag,text??'');n.className=cls||'';return n},verificationLabel:value=>value,openEditor(id){openedAsset=id},openIssueReview(){},markFieldState(){}});
 let start=source.indexOf('function renderQuality('),depth=0,opened=false,end=-1;for(let i=source.indexOf('{',start);i<source.length;i++){if(source[i]==='{'){depth++;opened=true}if(source[i]==='}'){depth--;if(opened&&depth===0){end=i+1;break}}}vm.runInContext(source.slice(start,end),ctx);ctx.renderQuality();
 const all=n=>[n,...n.children.flatMap(all)],rows=all(nodes['#quality-rows']).filter(n=>n.tagName==='tr');assert.equal(rows.length,2);const badges=all(nodes['#quality-rows']).filter(n=>n.className.startsWith('quality-severity-badge'));
 assert.match(nodes['#quality-summary'].textContent,/passed checks/i);assert.doesNotMatch(nodes['#quality-summary'].textContent,/verified and eligible/i);assert.equal(rows[0].children[1].textContent,'Vessel 101');assert.equal(rows[1].children[1].textContent,'b');rows[0].children[4].children[0].onclick();assert.equal(openedAsset,'a');assert.deepEqual(badges.map(n=>n.textContent),['Blocking issue','Warning']);assert.ok(badges[0].className.includes('blocking'));assert.ok(badges[1].className.includes('warning'));
});

test('verification explains engineering fields without exposing storage keys or JSON',()=>{
 const ctx=vm.createContext({});vm.runInContext(source,ctx);
 assert.equal(ctx.verificationLabel('inspections.OSI.next_inspection_month'),'OSI · Next inspection month');
 assert.equal(ctx.verificationLabel('name'),'Description');
 assert.equal(ctx.verificationValue({location_from:'North plant',tag_original:null}),'Location: North plant');
});

test('batch identity preview shows blank identifier members explicitly',()=>{
 const ctx=vm.createContext({});vm.runInContext(source,ctx);
 assert.equal(ctx.batchVerificationValue({tag_original:null,asset_number_original:'',oracle_description:'Line 4',location_from:'North'}),'Tag: Blank · Asset number: Blank · Oracle description: Line 4 · Location: North');
});

test('draft recovery refuses stale master versions and retains current read-only evidence',()=>{
 const ctx=vm.createContext({});vm.runInContext(source,ctx);
 const current={id:'a',version:4,name:'Saved',source_cells:[{original_value:'Current evidence'}]};
 assert.throws(()=>ctx.recoverEditorDraft(current,{baseVersion:3,asset:{name:'Draft'}}),/changed/);
 const resumed=ctx.recoverEditorDraft(current,{baseVersion:4,asset:{name:'Draft'}});
 assert.equal(resumed.name,'Draft');assert.equal(resumed.id,'a');assert.equal(resumed.version,4);assert.equal(resumed.source_cells[0].original_value,'Current evidence');
});

test('appearance has a persistent light/dark toggle synchronized with the theme selector',()=>{
 const html=fs.readFileSync('static/index.html','utf8');assert.match(html,/id="theme-toggle"[^>]*aria-label="Switch to light mode"/);
 const theme={value:'system',onchange:null},toggle={textContent:'',title:'',setAttribute(name,value){this[name]=value},onclick:null};
 const root={dataset:{}};const listeners={};const media={matches:false,addEventListener(name,fn){listeners[name]=fn}};const saved={};
 const ctx=vm.createContext({$:selector=>selector==='#theme-choice'?theme:toggle,document:{documentElement:root,querySelector(selector){return selector==='#theme-choice'?theme:toggle}},window:{matchMedia:()=>media},localStorage:{getItem:()=>null,setItem(key,value){saved[key]=value}}});
 const start=source.indexOf('function setupAppearance(');let depth=0,opened=false,end=-1;for(let i=source.indexOf('{',start);i<source.length;i++){if(source[i]==='{'){depth++;opened=true}if(source[i]==='}'){depth--;if(opened&&depth===0){end=i+1;break}}}assert.ok(end>start);vm.runInContext(source.slice(start,end)+';setupAppearance()',ctx);
 assert.equal(typeof toggle.onclick,'function');
 toggle.onclick();assert.equal(root.dataset.theme,'light');assert.equal(theme.value,'light');assert.equal(saved['inspection-theme'],'light');
 toggle.onclick();assert.equal(root.dataset.theme,'dark');assert.equal(theme.value,'dark');
 theme.value='system';theme.onchange();assert.equal(root.dataset.theme,'dark');assert.match(toggle.textContent,/light/i);
});

test('both themes provide explicit colors for key dashboard surfaces and disabled controls',()=>{
 const css=fs.readFileSync('static/style.css','utf8');
 for(const selector of [':root[data-theme=light] .period-control',':root[data-theme=light] #aging-panel',':root[data-theme=light] button:disabled',':root[data-theme=dark] button:disabled',':root[data-theme=dark] .aging-card'])assert.ok(css.includes(selector),`missing palette rule ${selector}`);
});

test('batch verification preview requests every selected ID, shows values and blockers, and guards apply',async()=>{
 const preview={preview_id:'preview-1',revision:5,asset_count:2,assets:[
  {id:'a',name:'V-101',source:{sheet:'Vessels & TKs',row:7},required_fields:[{field:'name',value:'V-101'},{field:'inspections.OSI.next_inspection_month',value:'2027-05'}],blockers:[]},
  {id:'b',name:'FL-2',source:{sheet:'FLs',row:9},required_fields:[{field:'identity',value:{tag_original:null,asset_number_original:'',oracle_description:'Line 4'}},{field:'context',value:{location_from:'North'}}],blockers:['Identifier is shared by multiple assets; review identity']}
 ]};
 const nodes={};function node(text=''){return {textContent:text,value:'',checked:false,disabled:false,children:[],dataset:{},append(...items){this.children.push(...items)},replaceChildren(...items){this.children=items},setAttribute(){},showModal(){this.opened=true},close(){this.closed=true}}}
 const ctx=vm.createContext({selectedAssets:new Set(['a','b']),bulkVerificationPreview:null,bulkVerificationPage:1,bulkVerificationPageSize:25,bulkVerificationSearch:'',
  $:selector=>nodes[selector]??=node(),el:(tag,text,cls)=>{const result=node(text??'');result.tagName=tag;result.className=cls||'';return result},
  verificationLabel:value=>value,verificationValue:value=>typeof value==='object'?JSON.stringify(value):String(value),batchVerificationValue:value=>typeof value==='object'?Object.entries(value).map(([k,v])=>`${k}: ${v===null||v===undefined||v===''?'Blank':v}`).join(' · '):String(value),message(text){ctx.lastMessage=text},
  load:async()=>{},renderAssets(){},loadQuality:async()=>{},
  api:async(path,options)=>{ctx.lastRequest={path,body:JSON.parse(options.body)};return path.endsWith('/preview')?preview:{verified_asset_count:2,verified_field_count:4,still_excluded_count:1}},
  updateBulkVerificationApplyState(){}});
 function extract(name){let start=source.indexOf('function '+name+'(');assert.notEqual(start,-1,`${name} must exist`);if(source.slice(start-6,start)==='async ')start-=6;let depth=0,opened=false;for(let i=source.indexOf('{',start);i<source.length;i++){if(source[i]==='{'){depth++;opened=true}if(source[i]==='}'){depth--;if(opened&&depth===0)return source.slice(start,i+1)}}throw Error(name+' has no closing brace')}
 for(const name of ['openSelectedVerification','renderBulkVerificationPreview','applyBulkVerification'])vm.runInContext(extract(name),ctx);
 await ctx.openSelectedVerification();
 assert.equal(ctx.lastRequest.path,'/api/verification/bulk/preview');assert.deepEqual(Array.from(ctx.lastRequest.body.asset_ids),['a','b']);assert.ok(nodes['#batch-verification-dialog']?.opened,ctx.lastMessage||'dialog did not open');
 ctx.bulkVerificationPreview=preview;ctx.renderBulkVerificationPreview();
 const all=n=>[n,...n.children.flatMap(all)];const text=all(nodes['#batch-verification-list']).map(n=>n.textContent).join(' ');
 assert.match(nodes['#batch-verification-summary'].textContent,/2 selected assets/);assert.match(text,/2027-05/);assert.match(text,/multiple assets/);assert.match(text,/Vessels & TKs · row 7/);assert.match(text,/tag_original: Blank · asset_number_original: Blank/);
 let applied=0;ctx.api=async(path,options)=>{if(path.endsWith('/apply')){applied++;return {verified_asset_count:2,verified_field_count:4,still_excluded_count:1}};throw Error('unexpected request')};
 nodes['#batch-verification-evidence'].value='Workbook MIP · tabs reviewed';nodes['#batch-verification-confirm'].checked=false;
 await ctx.applyBulkVerification();assert.equal(applied,0);
 nodes['#batch-verification-confirm'].checked=true;nodes['#batch-verification-evidence'].value='';await ctx.applyBulkVerification();assert.equal(applied,0);
 nodes['#batch-verification-evidence'].value='Workbook MIP · tabs reviewed';await ctx.applyBulkVerification();assert.equal(applied,1);assert.equal(ctx.selectedAssets.size,0);assert.equal(nodes['#batch-verification-dialog'].closed,true);
});

test('register selection accumulates across pages and filters before batch verification',async()=>{
 const appSource=fs.readFileSync('static/app.js','utf8'),selectedAssets=new Set(),nodes={};
 function node(){return {value:'',checked:false,children:[],replaceChildren(...items){this.children=items},setAttribute(){},showModal(){this.opened=true}}}
 const ctx=vm.createContext({selectedAssets,bulkVerificationPreview:null,bulkVerificationPage:1,bulkVerificationPageSize:25,bulkVerificationSearch:'',
  $:selector=>nodes[selector]??=node(),el:(tag,text)=>{const result=node();result.textContent=text??'';return result},
  visibleAssetRows:()=>[],verificationLabel:value=>value,batchVerificationValue:value=>String(value),verificationValue:value=>String(value),message(){},
  api:async(path,options)=>{ctx.request=JSON.parse(options.body);return {preview_id:'p',revision:1,asset_count:2,assets:ctx.request.asset_ids.map(id=>({id,name:id,required_fields:[],blockers:[]}))}},
  updateBulkVerificationApplyState(){}});
 function extract(text,name){let start=text.indexOf('function '+name+'(');assert.notEqual(start,-1,`${name} must exist`);const asyncPrefix=text.slice(Math.max(0,start-6),start)==='async '? 'async ':'';let depth=0,opened=false;for(let i=text.indexOf('{',start);i<text.length;i++){if(text[i]==='{'){depth++;opened=true}if(text[i]==='}'){depth--;if(opened&&depth===0)return asyncPrefix+text.slice(start,i+1)}}throw Error(name+' has no closing brace')}
 vm.runInContext(extract(appSource,'setVisibleAssetSelection')+';'+extract(source,'openSelectedVerification'),ctx);
 ctx.setVisibleAssetSelection(true,[{id:'page-1-asset'}]);
 ctx.setVisibleAssetSelection(true,[{id:'filtered-page-2-asset'}]);
 assert.deepEqual(Array.from(selectedAssets),['page-1-asset','filtered-page-2-asset']);
 await ctx.openSelectedVerification();
 assert.deepEqual(Array.from(ctx.request.asset_ids),['page-1-asset','filtered-page-2-asset']);
});

function getFunctionBody(name){const start=source.indexOf('function '+name+'(');assert.notEqual(start,-1,`${name} must exist`);let depth=0,opened=false;for(let i=source.indexOf('{',start);i<source.length;i++){if(source[i]==='{'){depth++;opened=true}if(source[i]==='}'){depth--;if(opened&&depth===0)return source.slice(start,i+1)}}throw Error('missing function end')}

test('year-only preview groups dates by year and shows retained problems',()=>{
 const nodes={};function node(tag,text=''){return {tag,textContent:text,children:[],append(...items){this.children.push(...items)},replaceChildren(...items){this.children=items}}}
 const ctx=vm.createContext({$:s=>nodes[s]??=node('div'),el:node,verificationLabel:field=>field});
 vm.runInContext(source,ctx);
 ctx.renderYearOnlyPreview({selected_count:1,date_count:2,groups:[{year:'2020',date_count:1},{year:'2025',date_count:1}],changes:[{asset_id:'a',name:'Line A',date_changes:[{year:'2020',inspection_type:'OSI',field:'last_inspection_month',original:'2020',after:'2020-01'},{year:'2025',inspection_type:'OSI',field:'next_inspection_month',original:'2025',after:'2025-01'}],remaining_issues:[{message:'Next month precedes last inspection'}]}]});
 const all=n=>[n,...n.children.flatMap(all)];const text=all(nodes['#year-only-preview']).map(n=>n.textContent).join(' ');
 assert.match(text,/2020.*2020-01/);assert.match(text,/2025.*2025-01/);assert.match(text,/Next month precedes last inspection/);
 assert.equal(nodes['#year-only-apply'].disabled,false);
 ctx.renderYearOnlyPreview({selected_count:0,date_count:0,groups:[],changes:[]});
 assert.equal(nodes['#year-only-apply'].disabled,true);
});

function previewHarness(){
 const nodes={},requests=[];
 function node(tag='div',text=''){return {tagName:tag,textContent:text,value:'',disabled:false,children:[],dataset:{},listeners:{},open:false,
  addEventListener(type,fn){(this.listeners[type]??=[]).push(fn)},emit(type){for(const fn of this.listeners[type]||[])fn({preventDefault(){}})},
  append(...items){this.children.push(...items);if(this.tagName==='select'&&!this.value&&items[0])this.value=items[0].value},replaceChildren(...items){this.children=items;if(this.tagName==='select')this.value=''},
  showModal(){this.open=true},close(){this.open=false;this.emit('close')},click(){return this.onclick?.()},querySelectorAll(){return []}}}
 const ctx=vm.createContext({$:s=>nodes[s]??=node(s.includes('survivor')?'select':'div'),el:(tag,text)=>node(tag,text??''),
  selectedAssets:new Set(['a','b']),assets:[{id:'a',name:'A'},{id:'b',name:'B'},{id:'c',name:'C'}],confirm:()=>true,message(){},
  verificationLabel:x=>x,verificationValue:x=>String(x),sessionStorage:{setItem(){}},load:async()=>{},renderAssets(){},
  api:(path,options)=>new Promise((resolve,reject)=>requests.push({path,body:JSON.parse(options.body),resolve,reject}))});
 vm.runInContext(source.slice(source.indexOf('function setupRecoveryAndBulk()'),source.indexOf("if(typeof document!=='undefined')setupRecoveryAndBulk();")),ctx);
 vm.runInContext(source.slice(source.indexOf('function setupConsolidation()'),source.indexOf("if(typeof document!=='undefined')setupConsolidation();")),ctx);
 ctx.setupRecoveryAndBulk();ctx.setupConsolidation();return {ctx,nodes,requests};
}
test('bulk preview rejects responses after field operation value or scope changes',async()=>{
 const h=previewHarness(),n=h.nodes;n['#bulk-field'].value='plant';n['#bulk-operation'].value='set';n['#bulk-value'].value='North';n['#bulk-open'].click();
 const pending=n['#bulk-preview'].click();n['#bulk-field'].value='field';n['#bulk-field'].emit('input');
 h.requests[0].resolve({preview_id:'old',revision:1,selected_count:2,changes:[{asset_id:'a',before:'',after:'North'}]});await pending;
 assert.equal(n['#bulk-apply'].disabled,true);assert.equal(n['#bulk-changes'].children.length,0);
 for(const control of ['#bulk-operation','#bulk-value']){const p=n['#bulk-preview'].click();n[control].value+='changed';n[control].emit('input');h.requests.at(-1).resolve({preview_id:'stale',revision:1,selected_count:2,changes:[{}]});await p;assert.equal(n['#bulk-apply'].disabled,true)}
 const p=n['#bulk-preview'].click();n['#bulk-close'].click();h.ctx.selectedAssets=new Set(['c']);n['#bulk-open'].click();h.requests.at(-1).resolve({preview_id:'scope-old',revision:1,selected_count:2,changes:[{}]});await p;assert.equal(n['#bulk-apply'].disabled,true);
});
test('bulk preview applies only the newest request and displays its operation',async()=>{
 const h=previewHarness(),n=h.nodes;n['#bulk-field'].value='plant';n['#bulk-operation'].value='set';n['#bulk-value'].value='North';n['#bulk-open'].click();
 const first=n['#bulk-preview'].click(),second=n['#bulk-preview'].click();
 h.requests[1].resolve({preview_id:'new',revision:2,selected_count:2,changes:[{asset_id:'a',before:'x',after:'North'}]});await second;
 h.requests[0].resolve({preview_id:'old',revision:1,selected_count:2,changes:[{asset_id:'a',before:'x',after:'wrong'}]});await first;
 assert.match(n['#bulk-changes'].children[0].textContent,/plant/i);assert.match(n['#bulk-changes'].children[0].textContent,/set/i);
 n['#bulk-reason'].value='Reviewed';const applying=n['#bulk-apply'].click();assert.equal(h.requests.at(-1).body.preview_id,'new');h.requests.at(-1).resolve({operation_id:'op'});await applying;
});
test('consolidation ignores obsolete survivor and dialog preview responses',async()=>{
 const h=previewHarness(),n=h.nodes;n['#consolidate-open'].click();n['#consolidate-survivor'].value='a';
 const first=n['#consolidate-preview'].click();n['#consolidate-survivor'].value='b';n['#consolidate-survivor'].onchange();
 h.requests[0].resolve({preview_id:'old',revision:1,survivor:{id:'a'},duplicate:{id:'b'},conflicts:[]});await first;assert.equal(n['#consolidate-apply'].disabled,true);
 const older=n['#consolidate-preview'].click(),newer=n['#consolidate-preview'].click();
 h.requests[2].resolve({preview_id:'new',revision:2,survivor:{id:'b'},duplicate:{id:'a'},conflicts:[]});await newer;
 h.requests[1].resolve({preview_id:'stale',revision:1,survivor:{id:'b'},duplicate:{id:'a'},conflicts:[]});await older;
 assert.match(n['#consolidate-conflicts'].children[0].textContent,/Keep b; retire a/);
 n['#consolidate-evidence'].value='Same';const apply=n['#consolidate-apply'].click();assert.equal(h.requests.at(-1).body.preview_id,'new');h.requests.at(-1).resolve({survivor_id:'b'});await apply;
 h.ctx.selectedAssets=new Set(['a','b']);n['#consolidate-open'].click();const closing=n['#consolidate-preview'].click();n['#consolidate-close'].click();h.ctx.selectedAssets=new Set(['b','c']);n['#consolidate-open'].click();h.requests.at(-1).resolve({preview_id:'closed',revision:1,survivor:{id:'a'},duplicate:{id:'b'},conflicts:[]});await closing;assert.equal(n['#consolidate-apply'].disabled,true);
});
