// OPERATOR ONLY. Metadata discovery; never configures delivery or execution.
import { open, unlink } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { randomUUID } from 'node:crypto';
import path from 'node:path';
import { findBrowser, safeDirectories, pairingOptions, linkOnly } from './pair.mjs';

const VERSION='v1-whatsapp-identity-1';
const groupId=value => typeof value==='string' && /^\d+(?:-\d+)?@g\.us$/.test(value);
const nameKey=value => value.normalize('NFKC').toLowerCase().replace(/[^a-z0-9]/g,'');

// Source-inspected wwebjs metadata APIs; never invoke its message serializer.
export async function groupMetadataProjection({ids,wanted,aliases}, runtime=globalThis.window) {
  const candidates=[];
  let missing=0;
  const collections=runtime.require('WAWebCollections');
  const factory=runtime.require('WAWebWidFactory');
  // Community announcement groups may be absent from getCommonGroups. Inspect
  // cached titles inside the browser, returning only explicitly named matches.
  const selected=new Set(ids);
  for (const chat of collections.Chat.getModelsArray()) {
    if (typeof chat.formattedTitle!=='string' || !chat.groupMetadata) continue;
    const key=chat.formattedTitle.normalize('NFKC').toLowerCase().replace(/[^a-z0-9]/g,'');
    if (wanted.includes(key) && /^\d+(?:-\d+)?@g\.us$/.test(chat.id?._serialized ?? '')) {
      selected.add(chat.id._serialized);
    }
  }
  for (const id of [...selected].sort()) {
    const wid=factory.createWid(id);
    const chat=collections.Chat.get(wid);
    if (!chat || typeof chat.formattedTitle!=='string') { missing++; continue; }
    if (chat.id?._serialized!==id) throw new Error('GROUP_IDENTITY_MISMATCH');
    const key=chat.formattedTitle.normalize('NFKC').toLowerCase().replace(/[^a-z0-9]/g,'');
    if (!wanted.includes(key)) continue;
    const metadataCollection=collections.GroupMetadata||collections.WAWebGroupMetadataCollection;
    if (!metadataCollection || !chat.groupMetadata) { missing++; continue; }
    await metadataCollection.update(wid);
    const updatedKey=chat.formattedTitle.normalize('NFKC').toLowerCase().replace(/[^a-z0-9]/g,'');
    if (!wanted.includes(updatedKey)) throw new Error('GROUP_NAME_CHANGED_DURING_LOOKUP');
    const metadata=chat.groupMetadata;
    const participants=metadata.participants?.serialize();
    const member=Array.isArray(participants)
      ? participants.filter(p=>aliases.includes(p?.id?._serialized)) : [];
    const membership=member.length===1;
    candidates.push({group_id:id,name:chat.formattedTitle,
      announcement:metadata.announce===true,
      sender_membership_verified:membership,
      sender_admin:membership && (member[0].isAdmin===true||member[0].isSuperAdmin===true),
      sender_member_id:membership?member[0].id._serialized:null});
  }
  return {candidates,missing};
}

export function identityRequest(value) {
  const keys=['phone','group_names'];
  if (!value || typeof value!=='object' || Array.isArray(value) ||
      Object.keys(value).length!==keys.length || keys.some(k=>!(k in value)) ||
      typeof value.phone!=='string' || !/^[1-9]\d{9,14}$/.test(value.phone) ||
      !Array.isArray(value.group_names) || !value.group_names.length || value.group_names.length>5 ||
      value.group_names.some(n=>typeof n!=='string'||!n.trim()||n.length>100||!nameKey(n))) {
    throw new Error('INVALID_IDENTITY_REQUEST');
  }
  return {phone:value.phone,group_names:[...value.group_names]};
}

export async function discoverSource(client, input, clock=()=>new Date(), report=()=>{}) {
  const request=identityRequest(input);
  const linkedAccount=client.info?.wid?._serialized;
  if (typeof linkedAccount!=='string'||!/^\d+@(c\.us|lid)$/.test(linkedAccount)||
      await client.getState()!=='CONNECTED') throw new Error('LINKED_ACCOUNT_NOT_ATTESTED');
  report('IDENTITY_NUMBER_LOOKUP');
  const number=await client.getNumberId(request.phone);
  const registered=number?._serialized,pn=request.phone+'@c.us';
  report(JSON.stringify({number_result_shape:{present:number!=null,
    serialized_type:typeof registered,user_type:typeof number?.user,
    user_matches_requested:number?.user===request.phone,
    server_is_cus:number?.server==='c.us',server_is_lid:number?.server==='lid',
    serialized_is_lid:typeof registered==='string'&&/^\d+@lid$/.test(registered)}}));
  if (registered!==pn && !(typeof registered==='string'&&/^\d+@lid$/.test(registered))) {
    throw new Error('REGISTERED_NUMBER_MISMATCH');
  }
  const aliases=[pn];
  report('IDENTITY_ALIAS_LOOKUP');
  const pairs=await client.getContactLidAndPhone([registered]);
  if (!Array.isArray(pairs) || pairs.length!==1 || pairs[0].pn!==pn ||
      (pairs[0].lid!=null && !/^\d+@lid$/.test(pairs[0].lid)) ||
      (registered!==pn && pairs[0].lid!==registered)) {
    throw new Error('AUTHORITATIVE_ALIAS_REQUIRED');
  }
  if (pairs[0].lid) aliases.push(pairs[0].lid);
  report('IDENTITY_COMMON_GROUP_LOOKUP');
  const shared=await client.getCommonGroups(registered);
  if (!Array.isArray(shared) || shared.length>100) throw new Error('COMMON_GROUP_EVIDENCE_INVALID');
  const ids=shared.map(value=>typeof value==='string'?value:value?._serialized);
  if (ids.some(id=>!groupId(id))) throw new Error('INVALID_GROUP_ID');
  const wanted=request.group_names.map(nameKey);
  report('IDENTITY_GROUP_METADATA_LOOKUP');
  const {candidates,missing}=await client.pupPage.evaluate(groupMetadataProjection,
    {ids:[...new Set(ids)].sort(),wanted,aliases});
  if (client.info?.wid?._serialized!==linkedAccount||await client.getState()!=='CONNECTED') {
    throw new Error('LINKED_ACCOUNT_CHANGED');
  }
  const eligible=candidates.filter(c=>c.announcement && c.sender_membership_verified && c.sender_admin);
  const announcements=candidates.filter(c=>c.announcement);
  const status=missing>0 ? 'GROUP_METADATA_INCOMPLETE' :
    announcements.length===1 && eligible.length===1 ? 'SOURCE_IDENTITY_VERIFIED' :
    announcements.length>1 ? 'GROUP_SELECTION_AMBIGUOUS' :
    candidates.length===0 ? 'GROUP_NOT_FOUND' : 'GROUP_OR_SENDER_NOT_VERIFIED';
  return {version:VERSION,observed_at:clock().toISOString(),status,linked_account_id:linkedAccount,
    registered_sender_id:pn,native_lookup_id:registered,verified_sender_ids:aliases,candidates,
    incomplete_group_metadata_count:missing,
    selected_group_id:status==='SOURCE_IDENTITY_VERIFIED'?eligible[0].group_id:null,
    message_forwarding:false,execution_enabled:false,broker_execution:'HARD_DISABLED'};
}

async function operatorMain() {
  const root=fileURLToPath(new URL('../../backend/private/whatsapp/v1/',import.meta.url));
  let input='';
  for await (const chunk of process.stdin) {
    input+=chunk.toString('utf8');
    if (Buffer.byteLength(input)>4096) throw new Error('IDENTITY_INPUT_TOO_LARGE');
  }
  const request=identityRequest(JSON.parse(input));
  const browser=await findBrowser(process.argv.slice(2));
  await safeDirectories(root);
  const lockPath=path.join(root,'link-only.lock'),lock=await open(lockPath,'wx');
  try {
    const {default:wweb}=await import('whatsapp-web.js');
    const options=pairingOptions(browser,root);
    const client=new wweb.Client({authStrategy:new wweb.LocalAuth(options.auth),
      puppeteer:options.puppeteer,webVersionCache:options.webVersionCache});
    const report=status => process.stdout.write(status+'\n');
    process.exitCode=await linkOnly(client,report,120000,15000,async()=>{
      let evidence;
      try { evidence=await discoverSource(client,request,()=>new Date(),report); }
      catch(error) {
        const codes=new Set(['REGISTERED_NUMBER_MISMATCH','AUTHORITATIVE_ALIAS_REQUIRED',
          'COMMON_GROUP_EVIDENCE_INVALID','INVALID_GROUP_ID','GROUP_IDENTITY_MISMATCH',
          'LINKED_ACCOUNT_NOT_ATTESTED','LINKED_ACCOUNT_CHANGED','GROUP_NAME_CHANGED_DURING_LOOKUP']);
        report(codes.has(error.message)?error.message:'NATIVE_METADATA_LOOKUP_FAILED');
        throw new Error('IDENTITY_CHECK_FAILED');
      }
      const file=await open(path.join(root,'source-identity-'+randomUUID()+'.json'),'wx');
      try { await file.writeFile(JSON.stringify(evidence,null,2)+'\n'); await file.sync(); }
      finally { await file.close(); }
      report(evidence.status);
      // Only matching group names and booleans, never phone/IDs/messages/secrets.
      process.stdout.write(JSON.stringify({candidates:evidence.candidates.map(c=>({
        name:c.name,announcement:c.announcement,sender_verified:c.sender_membership_verified,
        sender_admin:c.sender_admin})),message_forwarding:false,execution_enabled:false})+'\n');
    });
  } finally { await lock.close(); await unlink(lockPath); }
}

if (process.argv[1] && path.resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
  operatorMain().then(()=>process.exit(process.exitCode??0)).catch(()=>{
    process.stderr.write('WHATSAPP_IDENTITY_CHECK_BLOCKED\n'); process.exit(2);
  });
}
