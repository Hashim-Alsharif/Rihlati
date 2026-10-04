/* Account directory regression tests: synthetic data, no server or live DB. */
'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.resolve(__dirname,'..');
const state={user:{id:'root',role:'admin',is_primary:1,permissions:[]},approvedOffices:[{id:'o1',name:'مكتب النور'}],registration:{office:{}}};
const nodes=new Map();
const cards=[];
const document={addEventListener(){},querySelector:key=>nodes.get(key)||null,querySelectorAll:()=>cards};
const context=vm.createContext({state,document,stopAudio(){},tr:(ar,en)=>state.language==='ar'?ar:en});
const app=fs.readFileSync(path.join(root,'app/app.js'),'utf8');
vm.runInContext(app.slice(app.indexOf('const esc ='),app.indexOf('const subject =')),context);
vm.runInContext(app.slice(app.indexOf('const btn='),app.indexOf('const icon=')),context);
vm.runInContext(fs.readFileSync(path.join(root,'app/accounts.js'),'utf8'),context);
const base={status:'active',email:'',phone:'',permissions:[],office_ids:[]};
state.accounts={
  users:[
    {...base,id:'m1',display_name:'أَحْمَد علي',username:'Ahmad',role:'member',office_ids:['o1']},
    {...base,id:'m2',display_name:'Fatima',username:'FATIMA',role:'member'},
    {...base,id:'s1',display_name:'مختص أول',username:'staff',role:'office',office_id:'o1',office:{name:'مكتب النور'}},
    {...base,id:'a1',display_name:'Émilie',username:'emilie',role:'admin',permissions:['users']},
    {...base,id:'root',display_name:'Main admin',username:'admin',role:'admin',is_primary:1}
  ],
  offices:[{id:'o1',name:'مكتب النور',status:'approved'},{id:'o2',name:'مكتب جديد',status:'pending'}]
};
const ids=rows=>Array.from(rows,u=>u.id);
const filter=(q='',role='all')=>context.accountFilterResult(state.accounts,q,role);
assert.equal(filter().users.length,5);
assert.deepEqual(ids(filter('', 'member').users),['m1','m2']);
assert.deepEqual(ids(filter('', 'admin').users),['a1','root']);
assert.deepEqual(ids(filter('', 'office').users),['s1']);
assert.equal(filter('', 'member').offices.length,0);
assert.deepEqual(ids(filter('  احمد   علي ').users),['m1']);
assert.deepEqual(ids(filter('aHmAd').users),['m1']);
assert.deepEqual(ids(filter('emilie').users),['a1']);
assert.deepEqual(ids(filter('النور').users),['s1']);
assert.deepEqual(ids(filter('مختص').offices),['o1']);
assert.equal(filter('no-such-name').users.length,0);
assert.equal(filter('Fatima','admin').users.length,0);
assert.equal(filter('<script>').users.length,0);
assert.equal(state.accounts.users.length,5,'Filtering must not mutate source records');

let html=context.accountsPage();
assert.equal((html.match(/<details class="account-disclosure"/g)||[]).length,7);
assert.doesNotMatch(html,/<details[^>]*\sopen(?:\s|>)/,'All rows start collapsed');
assert.match(html,/id="account-search" type="search"/);
assert.match(html,/role="status" aria-live="polite"/);
assert.match(html,/value="member"/);assert.match(html,/value="office"/);assert.match(html,/value="admin"/);
assert.match(html,/class="user-admin-form account-form" data-id="m1"/);
assert.match(html,/class="admin-links-form account-form" data-id="m1"/);
assert.match(html,/class="office-admin-form account-form" data-id="o1"/);
assert.match(html,/name="permissions"/);
assert.match(html,/data-action="temporary-password" data-value="m1"/);
assert.doesNotMatch(context.adminUserDetails(state.accounts.users[4]),/<form|temporary-password/);
assert.doesNotMatch(context.adminUserDetails({...base,id:'root',role:'admin'}),/<form|temporary-password/);
state.accountOpen=['user:m1'];
assert.match(context.accountsPage(),/data-account-key="user:m1"[^>]* open>/);
state.accountQuery='"><img src=x onerror=alert(1)>';
state.accounts.users[1].display_name='<script>alert(1)</script>';
html=context.accountsPage();
assert.doesNotMatch(html,/<script>|<img src=x/);
assert.match(html,/&lt;script&gt;/);

// The server limits returned roles; the UI must not offer unauthorized filters.
state.user={id:'a1',role:'admin',is_primary:0,permissions:['users']};
state.accounts={users:[state.accounts.users[0]],offices:[]};
state.accountRole='admin';
html=context.accountsPage();
assert.equal(state.accountRole,'all');
assert.doesNotMatch(html,/<option value="(?:office|admin)"|id="account-add-admin"|id="account-offices"/);

// Filtering updates visibility in place; it must not replace a draft form.
state.user={id:'root',role:'admin',is_primary:1,permissions:[]};
state.accounts.users.push({...base,id:'s1',display_name:'Test office staff',role:'office',username:'staff'});
for(const selector of ['#account-result-count','#account-users-empty','#account-offices','#account-offices-empty','#account-add-admin'])nodes.set(selector,{hidden:false,textContent:''});
cards.push({dataset:{accountKind:'user',id:'m1'},hidden:false,draft:'unsaved profile'}, {dataset:{accountKind:'user',id:'s1'},hidden:false});
state.accountQuery='';state.accountRole='office';context.applyAccountFilters();
assert.equal(cards[0].hidden,true);assert.equal(cards[1].hidden,false);
assert.equal(nodes.get('#account-add-admin').hidden,true);
state.accountQuery='not found';context.applyAccountFilters();
assert.equal(nodes.get('#account-users-empty').hidden,false);
state.accountRole='all';state.accountQuery='';context.applyAccountFilters();
assert.equal(cards[0].hidden,false);assert.equal(cards[0].draft,'unsaved profile');
assert.match(nodes.get('#account-result-count').textContent,/Users: 2 \/ 2/);
context.resetPrivateState();
assert.equal(state.accountQuery,'');assert.equal(state.accountRole,'all');assert.equal(state.accountOpen.length,0);
console.log('Account directory: search, role filters, collapsed rows, draft preservation, permissions and session reset passed. No network or live database.');
