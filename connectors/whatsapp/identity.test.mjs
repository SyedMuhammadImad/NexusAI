import test from 'node:test';
import assert from 'node:assert/strict';
import { discoverSource, identityRequest, groupMetadataProjection } from './identity.mjs';
const phone='15555550101',pn=phone+'@c.us',lid='123456@lid';
const group='15555550100@g.us';
const request={phone,group_names:['REDACTED_SOURCE']};
const id=value=>({_serialized:value});
const chat=(groupId=group)=>({id:id(groupId),isGroup:true,name:'REDACTED_SOURCE',
  groupMetadata:{announce:true},participants:[{id:id(lid),isAdmin:true}],
  lastMessage:'FIXTURE_MESSAGE_MUST_NOT_LEAK',description:'FIXTURE_DESCRIPTION_MUST_NOT_LEAK'});
function client(chats=[chat()]) {
  const value={
    info:{wid:id('15555550102@c.us')},getState:async()=>'CONNECTED',
    getNumberId:async number=>{assert.equal(number,phone);return id(pn);},
    getContactLidAndPhone:async ids=>{assert.deepEqual(ids,[pn]);return [{pn,lid}];},
    getCommonGroups:async contact=>{assert.equal(contact,pn);return chats.map(c=>c.id);},
    getChatById:()=>{throw new Error('LAST_MESSAGE_SERIALIZER_FORBIDDEN');},
    getChats:()=>{throw new Error('ALL_CHATS_FORBIDDEN');},
    getContacts:()=>{throw new Error('ALL_CONTACTS_FORBIDDEN');},
    sendMessage:()=>{throw new Error('SEND_FORBIDDEN');},
  };
  value.pupPage={evaluate:async(fn,args)=>{
    assert.equal(fn,groupMetadataProjection);
    const runtime={require:name=>{
      if(name==='WAWebWidFactory') return {createWid:id};
      if(name==='WAWebCollections') return {
        Chat:{getModelsArray:()=>chats.map(c=>({id:c.id,formattedTitle:c.name,
          groupMetadata:c.groupMetadata})),get:wid=>{
          const found=chats.find(c=>c.id._serialized===wid._serialized);
          return found ? {id:found.id,formattedTitle:found.name,
            groupMetadata:{...found.groupMetadata,participants:{serialize:()=>found.participants}},
            serialize:()=>{throw new Error('CHAT_SERIALIZATION_FORBIDDEN');}} : null;
        }},
        GroupMetadata:{update:async()=>{}},
      };
      throw new Error('UNRELATED_MODULE_FORBIDDEN');
    }};
    return fn(args,runtime);
  }};
  return value;
}

test('exact registered PN/LID member and announcement admin verify metadata only',async()=>{
  const result=await discoverSource(client(),request,()=>new Date('2026-10-02T10:00:00Z'));
  assert.equal(result.status,'SOURCE_IDENTITY_VERIFIED');
  assert.equal(result.selected_group_id,group);
  assert.equal(result.execution_enabled,false);
  assert.equal(result.message_forwarding,false);
  assert.deepEqual(result.verified_sender_ids,[pn,lid]);
  assert.ok(!JSON.stringify(result).includes('MUST_NOT_LEAK'));
});
test('phone and LID mapping cannot be guessed or suffix matched',async()=>{
  const fake=client();fake.getNumberId=async()=>id('15555550104@c.us');
  await assert.rejects(discoverSource(fake,request),/NUMBER_MISMATCH/);
  const alias=client();alias.getContactLidAndPhone=async()=>[{pn:'wrong@c.us',lid}];
  await assert.rejects(discoverSource(alias,request),/ALIAS_REQUIRED/);
});
test('native number lookup may return LID only when authoritative PN mapping agrees',async()=>{
  const fake=client();fake.getNumberId=async()=>id(lid);
  fake.getContactLidAndPhone=async ids=>{assert.deepEqual(ids,[lid]);return [{pn,lid}];};
  fake.getCommonGroups=async contact=>{assert.equal(contact,lid);return [id(group)];};
  const result=await discoverSource(fake,request);
  assert.equal(result.status,'SOURCE_IDENTITY_VERIFIED');
  assert.equal(result.native_lookup_id,lid);
  fake.getContactLidAndPhone=async()=>[{pn,lid:'999999@lid'}];
  await assert.rejects(discoverSource(fake,request),/ALIAS_REQUIRED/);
});
test('duplicate group names remain ambiguous',async()=>{
  const result=await discoverSource(client([chat(),chat('15555550105@g.us')]),request);
  assert.equal(result.status,'GROUP_SELECTION_AMBIGUOUS');
  assert.equal(result.selected_group_id,null);
});
test('explicit announcements scope distinguishes same-name normal discussion group',async()=>{
  const regular=chat('15555550105@g.us');regular.groupMetadata.announce=false;
  const result=await discoverSource(client([chat(),regular]),request);
  assert.equal(result.status,'SOURCE_IDENTITY_VERIFIED');
  assert.equal(result.selected_group_id,group);
  assert.equal(result.candidates.length,2);
});
for(const missing of ['announcement','member','admin']) {
  test(`missing ${missing} fails closed`,async()=>{
    const value=chat();
    if(missing==='announcement') value.groupMetadata.announce=false;
    if(missing==='member') value.participants=[{id:id('999999@lid'),isAdmin:true}];
    if(missing==='admin') value.participants[0].isAdmin=false;
    const result=await discoverSource(client([value]),request);
    assert.equal(result.status,'GROUP_OR_SENDER_NOT_VERIFIED');
    assert.equal(result.selected_group_id,null);
  });
}
test('missing group and unrelated names are not authorized',async()=>{
  const value=chat();value.name='UNRELATED_PRIVATE_GROUP';
  const result=await discoverSource(client([value]),request);
  assert.equal(result.status,'GROUP_NOT_FOUND');
  assert.deepEqual(result.candidates,[]);
  assert.ok(!JSON.stringify(result).includes('UNRELATED_PRIVATE_GROUP'));
});
test('same group replay deduplicates IDs and results',async()=>{
  const result=await discoverSource(client([chat(),chat()]),request);
  assert.equal(result.candidates.length,1);
  assert.equal(result.status,'SOURCE_IDENTITY_VERIFIED');
});
test('malformed group identifiers or mismatched provider identity reject',async()=>{
  const fake=client();fake.getCommonGroups=async()=>[id('15555550100@newsletter')];
  await assert.rejects(discoverSource(fake,request),/INVALID_GROUP_ID/);
  const changed=client();changed.pupPage.evaluate=async(fn,args)=>fn(args,{
    require:name=>name==='WAWebWidFactory'?{createWid:id}:{Chat:{getModelsArray:()=>[],get:()=>({
      id:id('15555550105@g.us'),formattedTitle:'REDACTED_SOURCE'})}},
  });
  await assert.rejects(discoverSource(changed,request),/GROUP_IDENTITY_MISMATCH/);
});
test('uncached shared group remains incomplete, never assumed unrelated',async()=>{
  const fake=client();fake.getCommonGroups=async()=>[id(group),id('15555550105@g.us')];
  const result=await discoverSource(fake,request);
  assert.equal(result.status,'GROUP_METADATA_INCOMPLETE');
  assert.equal(result.selected_group_id,null);
  assert.equal(result.incomplete_group_metadata_count,1);
});
test('named cached announcement may be absent from common-group list but needs exact membership',async()=>{
  const fake=client();fake.getCommonGroups=async()=>[];
  const result=await discoverSource(fake,request);
  assert.equal(result.status,'SOURCE_IDENTITY_VERIFIED');
  assert.equal(result.selected_group_id,group);
  const other=chat();other.participants=[];
  const outsider=client([other]);outsider.getCommonGroups=async()=>[];
  assert.equal((await discoverSource(outsider,request)).selected_group_id,null);
});
test('request types and extra fields reject',()=>{
  for(const value of [null,{...request,token:'FIXTURE'}, {...request,phone:1},
    {...request,phone:'+15555550199'},{...request,group_names:[]},{...request,group_names:['#']}]) {
    assert.throws(()=>identityRequest(value));
  }
});
test('missing connected-account identity or disconnected state rejects',async()=>{
  const absent=client();delete absent.info;
  await assert.rejects(discoverSource(absent,request),/ACCOUNT_NOT_ATTESTED/);
  const disconnected=client();disconnected.getState=async()=>'UNPAIRED';
  await assert.rejects(discoverSource(disconnected,request),/ACCOUNT_NOT_ATTESTED/);
});
test('session account change during source lookup rejects',async()=>{
  const fake=client(),read=fake.pupPage.evaluate;
  fake.pupPage.evaluate=async(...args)=>{
    const value=await read(...args);fake.info.wid=id('15555550103@c.us');return value;
  };
  await assert.rejects(discoverSource(fake,request),/ACCOUNT_CHANGED/);
});
test('renamed group during metadata refresh rejects',async()=>{
  const fake=client();
  fake.pupPage.evaluate=async(fn,args)=>{
    const native={id:id(group),formattedTitle:'REDACTED_SOURCE',groupMetadata:{announce:true}};
    return fn(args,{require:name=>name==='WAWebWidFactory'?{createWid:id}:{
      Chat:{getModelsArray:()=>[native],get:()=>native},
      GroupMetadata:{update:async()=>{native.formattedTitle='UNRELATED_GROUP';}},
    }});
  };
  await assert.rejects(discoverSource(fake,request),/NAME_CHANGED/);
});
