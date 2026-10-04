/* Synthetic rendering/state tests; no browser, network, provider or live DB. */
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.resolve(__dirname,'..'),nodes=new Map();
const ctx=vm.createContext({localStorage:{getItem:()=>null},document:{querySelector:s=>nodes.get(s)||null,addEventListener(){}},window:{},console});
vm.runInContext(fs.readFileSync(path.join(root,'app/i18n.js'),'utf8'),ctx);
vm.runInContext(fs.readFileSync(path.join(root,'app/accounts.js'),'utf8'),ctx);
const code=fs.readFileSync(path.join(root,'app/app.js'),'utf8');
vm.runInContext(code.slice(0,code.indexOf("document.addEventListener('click'")),ctx);
const state=vm.runInContext('state',ctx);
const base={status:'approved',subject:'general',level:1,uploaded_by:'Test office'};
state.data={completed:['ar'],sources:[
  {...base,id:'ar',title:'Arabic level one',language:'ar'},
  {...base,id:'en',title:'English general book',language:'en',level:0},
  {...base,id:'fil',title:'Filipino book',language:'fil',level:2},
  {...base,id:'tl',title:'Legacy Tagalog book',language:'tl',level:3},
  {...base,id:'extra',title:'Additional book',language:'ar',level:4},
  {...base,id:'pending',title:'Unapproved source',language:'ar',status:'pending_review'},
  {...base,id:'deleted',title:'Archived source',language:'ar',status:'deleted'}
]};
assert.equal(ctx.journeySources().length,5,'All approved books by default');
let html=ctx.journeyPage();
assert.match(html,/English general book/);assert.match(html,/Additional book/);
assert.doesNotMatch(html,/Unapproved source|Archived source/);
assert.match(html,/id="journey-language"/);assert.match(html,/value="all"/);assert.match(html,/class="done"/);
state.journeyLanguage='fil';html=ctx.journeyPage();
assert.equal(ctx.journeySources().length,2);assert.match(html,/Legacy Tagalog book/);assert.doesNotMatch(html,/English general book|Arabic level one/);
assert.equal(state.language,'ar','Book filter must not change UI language');
state.journeyLanguage='fr';assert.match(ctx.journeyPage(),/data-action="journey-all"/);
state.journeyLanguage='all';state.data.sources[0].title='<img src=x onerror=1>';state.data.sources[0].uploaded_by='<script>x</script>';
assert.doesNotMatch(ctx.journeyPage(),/<img src=x|<script>/);
const header={innerHTML:'',hidden:false};nodes.set('#web-user',header);
for(const role of ['member','office','admin']){
  state.user={role,display_name:'Test <img src=x>',username:'test',permissions:[],is_primary:role==='admin',office:{name:'Office <b>name</b>'},office_id:'o1'};
  ctx.renderWebIdentity();assert.equal(header.hidden,false);assert.match(header.innerHTML,/Test &lt;img/);assert.doesNotMatch(header.innerHTML,/<img src=x>|<b>name/);
}
state.office={sources:[]};
const pending={id:'test',status:'pending_review',processing_status:'needs_review',passage_count:0};
assert.match(ctx.sourceReviewActions(pending),/review-source/);assert.doesNotMatch(ctx.sourceReviewActions(pending),/approve-source/);
pending.passage_count=1;assert.match(ctx.sourceReviewActions(pending),/approve-source/);
for(const status of ['queued','indexing','failed']){pending.processing_status=status;assert.doesNotMatch(ctx.sourceReviewActions(pending),/approve-source/);}
state.user={role:'office',office_id:'o1'};pending.processing_status='ready';
assert.equal(ctx.sourceReviewActions(pending),'');pending.uploaded_by_office_id='o1';
assert.match(ctx.sourceReviewActions(pending),/review-source/);assert.doesNotMatch(ctx.sourceReviewActions(pending),/approve-source/);
state.office.sources=[pending];state.reviewSource='test';state.reviewPage={page_number:1,raw_text:'<script>bad</script>',extraction_status:'needs_review'};
html=ctx.pageReviewPanel();assert.match(html,/name="verified" required/);assert.doesNotMatch(html,/<script>/);
ctx.resetPrivateState();ctx.renderWebIdentity();assert.equal(header.hidden,true);assert.equal(header.innerHTML,'');assert.equal(state.journeyLanguage,'all');
console.log('Journey languages/general books, safe identity, source review gating and session reset passed. No live calls.');
