// Pure adapter and durable delivery queue. No WhatsApp session or trading API.
import { createHash } from 'node:crypto';
import { DatabaseSync } from 'node:sqlite';

const hash = x => createHash('sha256').update(x).digest('hex');
export function normalize(message, config) {
  if (message.fromMe || message.isStatus || message.type !== 'chat') return null;
  if (message.from !== config.group_id || !config.sender_ids.includes(message.author)) return null;
  if (!message.id?._serialized || !Number.isSafeInteger(message.timestamp) || message.timestamp <= 0 ||
      typeof message.body !== 'string' || !message.body.trim() || message.body.length > 16000) throw new Error('INVALID_MESSAGE');
  return {source_type:'WHATSAPP_HUMAN',source_id:config.source_id,message_id:message.id._serialized,
    original_timestamp:new Date(message.timestamp * 1000).toISOString(),timezone_evidence:'UTC',
    sender_id:message.author,group_id:message.from,raw_text:message.body,
    provenance:{transport:'whatsapp-web.js-1.34.7',raw_reference:`sha256:${hash(message.body)}`}};
}

export class Outbox {
  constructor(path) {
    this.db=new DatabaseSync(path);
    this.db.exec(`PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL;
      CREATE TABLE IF NOT EXISTS messages (id TEXT PRIMARY KEY, body TEXT NOT NULL, digest TEXT NOT NULL,
        state TEXT NOT NULL CHECK(state IN ('PENDING','DELIVERED','CONFLICT','REJECTED')));
      CREATE TABLE IF NOT EXISTS conflicts(id TEXT NOT NULL,digest TEXT NOT NULL,body TEXT NOT NULL,PRIMARY KEY(id,digest));`);
  }
  enqueue(envelope) {
    const id=hash(JSON.stringify([envelope.source_id,envelope.group_id,envelope.message_id]));
    const body=JSON.stringify(envelope),digest=hash(body);
    this.db.exec('BEGIN IMMEDIATE');
    try {
      const old=this.db.prepare('SELECT digest,state FROM messages WHERE id=?').get(id);
      if (old && old.digest!==digest) {
        this.db.prepare('INSERT OR IGNORE INTO conflicts VALUES(?,?,?)').run(id,digest,body);
        this.db.prepare("UPDATE messages SET state='CONFLICT' WHERE id=?").run(id);
        this.db.exec('COMMIT'); return 'CONFLICT';
      }
      this.db.prepare("INSERT OR IGNORE INTO messages VALUES(?,?,?,'PENDING')").run(id,body,digest);
      this.db.exec('COMMIT'); return old?.state || 'PENDING';
    } catch(e) {this.db.exec('ROLLBACK');throw e;}
  }
  async drain(send) {
    for (const row of this.db.prepare("SELECT id,body FROM messages WHERE state='PENDING' ORDER BY rowid LIMIT 100").all()) {
      const result=await send(JSON.parse(row.body));
      if(result==='DELIVERED'||result==='REJECTED') this.db.prepare("UPDATE messages SET state=? WHERE id=? AND state='PENDING'").run(result,row.id);
      else break; // Preserve identity on uncertain HTTP delivery; backend never directly sends orders.
    }
  }
  counts() {return this.db.prepare('SELECT state,count(*) count FROM messages GROUP BY state').all();}
  close() {this.db.close();}
}

export async function deliver(envelope,config,fetcher=fetch) {
  const url=new URL(config.backend_url);
  if(url.protocol!=='http:'||url.hostname!=='127.0.0.1'||url.username||url.password||url.pathname!=='/'||url.search||url.hash) throw new Error('LOOPBACK_REQUIRED');
  const response=await fetcher(new URL('/api/core/operations/whatsapp',url),{method:'POST',redirect:'error',
    headers:{'Content-Type':'application/json','X-Connector-Token':config.connector_token},
    body:JSON.stringify(envelope),signal:AbortSignal.timeout(10000)});
  if(response.ok) return 'DELIVERED';
  if([400,409,422].includes(response.status)) return 'REJECTED';
  return 'PENDING';
}
