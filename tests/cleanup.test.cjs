const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const source=()=>fs.readFileSync('static/cleanup.js','utf8');
function storage(values){const rows=new Map(Object.entries(values));return {get length(){return rows.size},key:i=>Array.from(rows.keys())[i],removeItem:k=>rows.delete(k),getItem:k=>rows.get(k)??null}}
test('browser cleanup removes app drafts and reconciliation but preserves appearance and other apps',()=>{
 const local=storage({'inspection-theme':'dark','inspection-editor-draft:a':'draft','inspection-reconciliation-v1':'workbook',unrelated:'keep'});
 const session=storage({'inspection-last-bulk':'x','inspection-recon-highlights':'x',unrelated:'keep'});
 const ctx=vm.createContext({});vm.runInContext(source(),ctx);
 ctx.clearStoredBrowserData(local,session);
 assert.equal(local.getItem('inspection-editor-draft:a'),null);assert.equal(local.getItem('inspection-reconciliation-v1'),null);
 assert.equal(session.getItem('inspection-last-bulk'),null);assert.equal(local.getItem('inspection-theme'),'dark');assert.equal(local.getItem('unrelated'),'keep');assert.equal(session.getItem('unrelated'),'keep');
});
test('confirmation requires exact preview phrase and a preview',()=>{
 const ctx=vm.createContext({});vm.runInContext(source(),ctx);
 assert.equal(ctx.cleanupConfirmationMatches(null,'DELETE'),false);
 assert.equal(ctx.cleanupConfirmationMatches({confirmation:'RESET WORKING DATA'},'DELETE'),false);
 assert.equal(ctx.cleanupConfirmationMatches({confirmation:'DELETE'},'delete'),false);
 assert.equal(ctx.cleanupConfirmationMatches({confirmation:'DELETE'},'DELETE'),true);
});
test('coverage excludes dismissed and deleted evidence unless showing dismissed entries',()=>{
 const ctx=vm.createContext({});vm.runInContext(source(),ctx);
 const rows=[{batch_id:'one',unclassified_count:1},{batch_id:'two',unclassified_count:1,dismissed:true},{batch_id:'three',unclassified_count:0,excluded_sheets:['X']},{batch_id:'deleted',unclassified_count:1,evidence_deleted:true}];
 assert.deepEqual(Array.from(ctx.visibleSourceCoverage(rows,false),r=>r.batch_id),['one','three']);
 assert.deepEqual(Array.from(ctx.visibleSourceCoverage(rows,true),r=>r.batch_id),['one','two','three']);
});
test('deletion preview names exact files, retained copies and dependencies',()=>{
 const ctx=vm.createContext({});vm.runInContext(source(),ctx);
 const text=ctx.cleanupPreviewText({category:'sources',counts:{sources:1},files:[{filename:'source.xlsx',folder:'local/source-archives'}],dependent_assets:2,notice:'Embedded copies remain in assets and backups.'});
 assert.match(text,/source.xlsx/);assert.match(text,/2/);assert.match(text,/Embedded copies remain/);
});
