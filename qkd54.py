# stage54_key_wrapping_rotation.py
# 段階54：二重鍵化（Key Wrapping: scrypt+AES-GCM）＋ パスフレーズ保護 ＋ 鍵ローテーション ＋ 監査鍵分離
# 依存: cryptography
# 実行: pip install cryptography && python stage54_key_wrapping_rotation.py

import os, sys, time, json, base64, random, hmac, hashlib, getpass
from dataclasses import dataclass, field
from typing import Dict, Tuple, List, Optional, Any
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

# ===== パラメータ =====
IKM_BYTES      = 32
CHUNK_BYTES    = 1024
SKIP_WINDOW    = 16
ACK_TIMEOUT    = 0.12
MAX_RETRIES    = 6
RUNTIME_SEC    = 2.0
DROP_PROB      = 0.12
REORDER_PROB   = 0.25
MAX_DELAY      = 0.02

STATE_FILE     = "state.bin"          # DEKで暗号化
STATE_FILE_OLD = "state.prev.bin"
WRAP_FILE      = "wrapped_keys.json"  # DEKをMKでラップして保存（パスフレーズ必要）
AUDIT_FILE     = "audit.log"          # HMACチェーン（監査用）
AUTOSAVE_EVERY = 6

random.seed(7)

# ===== ユーティリティ =====
def hkdf(ikm: bytes, length: int, info: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=None, info=info).derive(ikm)
def b64e(b: bytes) -> str: return base64.b64encode(b).decode()
def b64d(s: str) -> bytes: return base64.b64decode(s.encode())

# ====== 二重鍵化（パスフレーズ→MK、MKでDEKをラップ） ======
class KeyWrapper:
    """
    - Passphrase → scrypt(KDF) → MK(32B)
    - MK で {data_DEK, audit_DEK} を AES-GCM で包む（nonce, ct, tag）
    - version と monotonic counter でロールバック耐性
    """
    def __init__(self, wrap_path=WRAP_FILE, scrypt_params=None):
        self.wrap_path = wrap_path
        self.scrypt_params = scrypt_params or {"n": 2**15, "r": 8, "p": 1}  # ほどよいコスト（デモ向け）
        self.meta = None  # ロード済みJSON

    def _mk_from_pass(self, passphrase: str, salt: bytes) -> bytes:
        kdf = Scrypt(salt=salt, length=32, n=self.scrypt_params["n"],
                     r=self.scrypt_params["r"], p=self.scrypt_params["p"])
        return kdf.derive(passphrase.encode())

    def create_or_load(self, passphrase: str) -> Tuple[bytes, bytes]:
        """
        戻り値: (data_DEK, audit_DEK)
        """
        if os.path.exists(self.wrap_path):
            with open(self.wrap_path, "r", encoding="utf-8") as f:
                self.meta = json.load(f)
            salt = b64d(self.meta["salt"])
            mk = self._mk_from_pass(passphrase, salt)
            # 解除
            data_DEK = self._unwrap(mk, self.meta["data"])
            audit_DEK = self._unwrap(mk, self.meta["audit"])
            return data_DEK, audit_DEK
        # 新規作成
        salt = os.urandom(16)
        mk = self._mk_from_pass(passphrase, salt)
        data_DEK = os.urandom(32)
        audit_DEK = os.urandom(32)
        meta = {
            "version": 1,
            "counter": 1,
            "scrypt": self.scrypt_params,
            "salt": b64e(salt),
            "data": self._wrap(mk, data_DEK),
            "audit": self._wrap(mk, audit_DEK),
        }
        with open(self.wrap_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        self.meta = meta
        return data_DEK, audit_DEK

    def rotate(self, passphrase: str, which: str = "data|audit") -> Tuple[bytes, bytes]:
        """
        which: "data", "audit", "data|audit"
        新DEKを発行してラップを更新（カウンタ増分）
        """
        if not os.path.exists(self.wrap_path):
            raise RuntimeError("wrapped_keys.json がありません（初期化してください）")
        with open(self.wrap_path, "r", encoding="utf-8") as f:
            self.meta = json.load(f)
        salt = b64d(self.meta["salt"])
        mk = self._mk_from_pass(passphrase, salt)

        # 現在のDEKを解錠
        cur_data = self._unwrap(mk, self.meta["data"])
        cur_audit = self._unwrap(mk, self.meta["audit"])

        do_data = "data" in which
        do_audit = "audit" in which

        if do_data:
            cur_data = os.urandom(32)
            self.meta["data"] = self._wrap(mk, cur_data)
        if do_audit:
            cur_audit = os.urandom(32)
            self.meta["audit"] = self._wrap(mk, cur_audit)

        self.meta["counter"] = int(self.meta.get("counter", 1)) + 1
        with open(self.wrap_path, "w", encoding="utf-8") as f:
            json.dump(self.meta, f, ensure_ascii=False, indent=2)

        return cur_data, cur_audit

    def _wrap(self, mk: bytes, dek: bytes) -> dict:
        nonce = os.urandom(12)
        ct = AESGCM(mk).encrypt(nonce, dek, b"wrap")
        return {"nonce": b64e(nonce), "ct": b64e(ct)}

    def _unwrap(self, mk: bytes, blob: dict) -> bytes:
        nonce = b64d(blob["nonce"])
        ct = b64d(blob["ct"])
        return AESGCM(mk).decrypt(nonce, ct, b"wrap")

# ===== 監査ログ（HMACチェーン、監査キーをDEKから派生） =====
class AuditVerifier:
    def __init__(self, audit_DEK: bytes, path=AUDIT_FILE):
        self.path = path
        # 監査用 HMAC キーを DEK から派生（用途固定）
        self.key = hashlib.sha256(b"AUDIT:"+audit_DEK).digest()
        self.prev = b"\x00"*32
        self._bootstrap()

    def _mac(self, prev: bytes, data_json: str) -> bytes:
        return hmac.new(self.key, prev + data_json.encode(), hashlib.sha256).digest()

    def _bootstrap(self):
        if not os.path.exists(self.path):
            self.append({"event":"AUDIT_CHAIN_START","note":"stage54"})
            return
        if not self.verify_all(verbose=False):
            self.append({"event":"AUDIT_CHAIN_RESYNC","note":"verify-failed"})

    def append(self, event: dict):
        data_json = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
        tag = self._mac(self.prev, data_json)
        rec = {"ts": time.time(), "data": event, "tag": b64e(tag)}
        with open(self.path, "ab") as f:
            f.write((json.dumps(rec, ensure_ascii=False)+"\n").encode())
        self.prev = tag

    def verify_all(self, verbose=True) -> bool:
        prev = b"\x00"*32
        if not os.path.exists(self.path):
            if verbose: print("[AUDIT] 監査ログなし"); return True
        with open(self.path, "rb") as f:
            for i, line in enumerate(f, 1):
                try:
                    rec = json.loads(line.decode())
                    tag = b64d(rec["tag"])
                    data_json = json.dumps(rec["data"], ensure_ascii=False, separators=(",", ":"))
                    calc = self._mac(prev, data_json)
                    if not hmac.compare_digest(tag, calc):
                        if verbose: print(f"[AUDIT] 改ざん検出: {i}行目")
                        return False
                    prev = tag
                except Exception:
                    if verbose: print(f"[AUDIT] パース失敗: {i}行目")
                    return False
        self.prev = prev
        if verbose: print("[AUDIT] OK")
        return True

# ===== QKDテープ（模擬） =====
class GroupTape:
    def __init__(self): self.buf = bytearray()
    def ensure(self, min_bytes=IKM_BYTES):
        while len(self.buf) < min_bytes:
            self.buf.extend(os.urandom(CHUNK_BYTES))
    def take_ikm(self, n=IKM_BYTES)->bytes:
        self.ensure(n); ikm = bytes(self.buf[:n]); del self.buf[:n]; return ikm
    def to_dict(self): return {"buf": b64e(bytes(self.buf))}
    @classmethod
    def from_dict(cls, d): o=cls(); o.buf=bytearray(b64d(d["buf"])); return o

# ===== ラチェット（Sender Keys） =====
@dataclass
class SenderState:
    send_ck: bytes; nonce_base: bytes; seq: int = 0
    def next_mk_nonce(self)->Tuple[bytes,bytes,int]:
        mk = hmac.new(self.send_ck, b"MSG", hashlib.sha256).digest()
        self.send_ck = hmac.new(self.send_ck, b"NEXT", hashlib.sha256).digest()
        nonce = self.seq.to_bytes(4,"big")+self.nonce_base
        s=self.seq; self.seq+=1
        return mk, nonce, s
    def to_dict(self): return {"send_ck":b64e(self.send_ck),"nonce_base":b64e(self.nonce_base),"seq":self.seq}
    @classmethod
    def from_dict(cls,d): return cls(b64d(d["send_ck"]),b64d(d["nonce_base"]),d["seq"])

@dataclass
class ReceiverState:
    recv_ck: bytes; nonce_base: bytes; next_seq:int=0; skip:Dict[int,bytes]=field(default_factory=dict)
    def _advance_to(self, target:int, limit:int=SKIP_WINDOW):
        if target<self.next_seq: return
        steps=target-self.next_seq
        if steps>limit: raise ValueError("skip window 超過")
        for _ in range(steps):
            mk=hmac.new(self.recv_ck,b"MSG",hashlib.sha256).digest()
            self.recv_ck=hmac.new(self.recv_ck,b"NEXT",hashlib.sha256).digest()
            self.skip[self.next_seq]=mk; self.next_seq+=1
    def key_for(self, seq:int)->Tuple[bytes,bytes]:
        if seq<self.next_seq:
            if seq not in self.skip: raise ValueError("過去鍵なし")
            mk=self.skip.pop(seq)
        elif seq==self.next_seq:
            mk=hmac.new(self.recv_ck,b"MSG",hashlib.sha256).digest()
            self.recv_ck=hmac.new(self.recv_ck,b"NEXT",hashlib.sha256).digest()
            self.next_seq+=1
        else:
            self._advance_to(seq)
            mk=hmac.new(self.recv_ck,b"MSG",hashlib.sha256).digest()
            self.recv_ck=hmac.new(self.recv_ck,b"NEXT",hashlib.sha256).digest()
            self.next_seq+=1
        nonce=seq.to_bytes(4,"big")+self.nonce_base
        return mk, nonce
    def to_dict(self):
        return {"recv_ck":b64e(self.recv_ck),"nonce_base":b64e(self.nonce_base),
                "next_seq":self.next_seq,"skip":{str(k):b64e(v) for k,v in self.skip.items()}}
    @classmethod
    def from_dict(cls,d):
        o=cls(b64d(d["recv_ck"]),b64d(d["nonce_base"]),d["next_seq"])
        o.skip={int(k):b64d(v) for k,v in d.get("skip",{}).items()}; return o

# ===== エポック =====
class GroupEpoch:
    def __init__(self, epoch_id:int, ikm:bytes, members:List[str]):
        self.id=epoch_id; self.members=list(members)
        self.root = hkdf(ikm,32,b"group-root:"+str(epoch_id).encode())
        self.control_key = hkdf(ikm,32,b"group-control:"+str(epoch_id).encode())
        self.sender_seeds:Dict[str,Tuple[bytes,bytes]]={}
        for sid in self.members:
            seed=hkdf(self.root,40,b"sender-seed:"+sid.encode())
            self.sender_seeds[sid]=(seed[:32],seed[32:40])
    def to_dict(self):
        return {"id":self.id,"members":self.members,"root":b64e(self.root),
                "control_key":b64e(self.control_key),
                "sender_seeds":{k:[b64e(v[0]),b64e(v[1])] for k,v in self.sender_seeds.items()}}
    @classmethod
    def from_dict(cls,d):
        o=cls.__new__(cls); o.id=d["id"]; o.members=list(d["members"])
        o.root=b64d(d["root"]); o.control_key=b64d(d["control_key"])
        o.sender_seeds={k:(b64d(v[0]),b64d(v[1])) for k,v in d["sender_seeds"].items()}
        return o

# ===== メンバー =====
class Member:
    def __init__(self, mid:str, all_ids:List[str]):
        self.id=mid; self.all_ids=list(all_ids)
        self.sender:Optional[SenderState]=None
        self.receivers:Dict[str,ReceiverState]={}
        self.epoch_id=-1; self.ctrl_key:Optional[bytes]=None
        self.inbox:List[str]=[]; self.seen:set=set()
    def enter_epoch(self, epoch:GroupEpoch):
        self.epoch_id=epoch.id; self.ctrl_key=epoch.control_key
        sc,nb=epoch.sender_seeds[self.id]; self.sender=SenderState(sc,nb,0)
        self.receivers={}
        for sid in epoch.members:
            if sid==self.id: continue
            rc,rnb=epoch.sender_seeds[sid]; self.receivers[sid]=ReceiverState(rc,rnb,0)
        self.seen.clear()
    def encrypt_for_group(self, text:str, aad:bytes=b""):
        mk,nonce,seq=self.sender.next_mk_nonce()
        ct=AESGCM(mk).encrypt(nonce,text.encode(),aad)
        return ("DATA",self.id,self.epoch_id,seq,nonce,ct,aad)
    def recv_data(self,sender_id:str,epoch:int,seq:int,nonce:bytes,ct:bytes,aad:bytes=b""):
        key=(sender_id,epoch,seq)
        if key in self.seen: return True,("ACK",sender_id,epoch,seq,self.id)
        if epoch!=self.epoch_id or sender_id not in self.receivers: return False,None
        try: mk,exp=self.receivers[sender_id].key_for(seq)
        except Exception: return False,None
        if exp!=nonce: return False,None
        try: pt=AESGCM(mk).decrypt(nonce,ct,aad).decode()
        except Exception: return False,None
        self.inbox.append(f"{sender_id}@E{epoch}: {pt}")
        self.seen.add(key); return True,("ACK",sender_id,epoch,seq,self.id)
    def to_dict(self):
        return {"id":self.id,"all_ids":self.all_ids,"epoch_id":self.epoch_id,
                "ctrl_key":b64e(self.ctrl_key) if self.ctrl_key else None,
                "sender":self.sender.to_dict() if self.sender else None,
                "receivers":{k:v.to_dict() for k,v in self.receivers.items()},
                "inbox":self.inbox,"seen":[list(x) for x in self.seen]}
    @classmethod
    def from_dict(cls,d):
        o=cls(d["id"],d["all_ids"]); o.epoch_id=d["epoch_id"]
        o.ctrl_key=b64d(d["ctrl_key"]) if d["ctrl_key"] else None
        o.sender=SenderState.from_dict(d["sender"]) if d["sender"] else None
        o.receivers={k:ReceiverState.from_dict(v) for k,v in d["receivers"].items()}
        o.inbox=list(d["inbox"]); o.seen=set(tuple(x) for x in d["seen"]); return o

# ===== 擬似ネット =====
class UnreliableBus:
    def __init__(self, drop=DROP_PROB, reorder=REORDER_PROB, max_delay=MAX_DELAY):
        self.drop=drop; self.reorder=reorder; self.max_delay=max_delay; self.buf=[]
    def send(self,to_id:str,packet:tuple):
        if random.random()<self.drop: return
        d=random.random()*self.max_delay
        if random.random()<self.reorder: d+=random.random()*self.max_delay
        self.buf.append((time.time()+d,to_id,packet))
    def recv_ready(self):
        now=time.time(); out=[]; keep=[]
        for t,to_id,pk in self.buf:
            (out if t<=now else keep).append((t,to_id,pk))
        self.buf=keep; return [(to_id,pk) for _,to_id,pk in out]

# ===== Inflight =====
@dataclass
class Inflight:
    epoch:int; seq:int; nonce:bytes; ct:bytes; aad:bytes
    waiting:set; last_send:Dict[str,float]; tries:Dict[str,int]
    def to_dict(self):
        return {"epoch":self.epoch,"seq":self.seq,"nonce":b64e(self.nonce),"ct":b64e(self.ct),
                "aad":b64e(self.aad),"waiting":list(self.waiting),
                "last_send":{k:v for k,v in self.last_send.items()},
                "tries":{k:v for k,v in self.tries.items()}}
    @classmethod
    def from_dict(cls,d):
        return cls(d["epoch"],d["seq"],b64d(d["nonce"]),b64d(d["ct"]),b64d(d["aad"]),
                   set(d["waiting"]),{k:float(v) for k,v in d["last_send"].items()},
                   {k:int(v) for k,v in d["tries"].items()})

# ===== 永続化（DEKで暗号化・原子的保存・ロールバック） =====
class Persistence:
    def __init__(self, data_DEK: bytes):
        self.data_DEK = data_DEK
    def save(self, obj: Dict[str,Any], cur="state.bin", prev="state.prev.bin"):
        data=json.dumps(obj,ensure_ascii=False).encode()
        nonce=os.urandom(12); ct=AESGCM(self.data_DEK).encrypt(nonce,data,b"stage54-state")
        tmp=cur+".tmp"; open(tmp,"wb").write(nonce+ct)
        if os.path.exists(cur): os.replace(cur, prev)
        os.replace(tmp, cur)
    def load(self, cur="state.bin", prev="state.prev.bin")->Optional[Dict[str,Any]]:
        def _try(path):
            if not os.path.exists(path): return None
            blob=open(path,"rb").read(); nonce,ct=blob[:12],blob[12:]
            try:
                data=AESGCM(self.data_DEK).decrypt(nonce,ct,b"stage54-state")
                return json.loads(data.decode())
            except Exception: return None
        return _try(cur) or _try(prev)

# ===== グループ管理（鍵ラップ＋監査＋ローテーション） =====
class GroupReliablePersistent:
    def __init__(self, member_ids: List[str], data_DEK: bytes, audit_DEK: bytes):
        self.ids=list(member_ids); self.roster=list(member_ids)
        self.members={mid:Member(mid,self.ids) for mid in self.ids}
        self.tape=GroupTape(); self.bus=UnreliableBus()
        self.audit=AuditVerifier(audit_DEK)
        self.persist=Persistence(data_DEK)
        self.epoch_id=-1
        self.inflight:Dict[str,Dict[int,Inflight]]={mid:{} for mid in self.ids}
        if not self._restore():
            self._start_epoch()
            self.audit.append({"event":"BOOT_NEW","epoch":self.epoch_id,"roster":self.roster})

    def _start_epoch(self):
        self.epoch_id+=1
        ikm=self.tape.take_ikm(IKM_BYTES)
        epoch=GroupEpoch(self.epoch_id,ikm,self.roster)
        for mid in self.roster: self.members[mid].enter_epoch(epoch)
        self.audit.append({"event":"REKEY","epoch":self.epoch_id,"roster":self.roster})

    def send(self, sender_id:str, text:str, aad:bytes=b""):
        if sender_id not in self.roster: return
        pkt=self.members[sender_id].encrypt_for_group(text,aad)
        _,sid,ep,seq,nonce,ct,aad=pkt
        waiting=set(self.roster)-{sid}
        infl=Inflight(ep,seq,nonce,ct,aad,waiting,{},{})
        self.inflight.setdefault(sid,{})[seq]=infl
        now=time.time()
        for rid in list(waiting):
            self.bus.send(rid,pkt); infl.last_send[rid]=now; infl.tries[rid]=1
        self.audit.append({"event":"SEND","sid":sid,"epoch":ep,"seq":seq,"to":sorted(list(waiting))})

    def _deliver_bus(self):
        for to_id,pkt in self.bus.recv_ready():
            typ=pkt[0]
            if typ=="DATA":
                _,sid,ep,seq,nonce,ct,aad=pkt
                if to_id not in self.roster: continue
                ok,ack=self.members[to_id].recv_data(sid,ep,seq,nonce,ct,aad)
                if ack: self.bus.send(sid,ack)
            elif typ=="ACK":
                _,sid,ep,seq,from_id=pkt
                infl=self.inflight.get(sid,{}).get(seq)
                if infl and ep==infl.epoch and from_id in infl.waiting:
                    infl.waiting.remove(from_id)
                    if not infl.waiting:
                        self.audit.append({"event":"DELIVERED","sid":sid,"epoch":ep,"seq":seq})

    def _retransmit_timeouts(self):
        now=time.time()
        for sid,table in self.inflight.items():
            for seq,infl in list(table.items()):
                if not infl.waiting:
                    del table[seq]; continue
                for rid in list(infl.waiting):
                    last=infl.last_send.get(rid,0.0); tries=infl.tries.get(rid,0)
                    if now-last>ACK_TIMEOUT and tries<MAX_RETRIES:
                        pkt=("DATA",sid,infl.epoch,infl.seq,infl.nonce,infl.ct,infl.aad)
                        self.bus.send(rid,pkt)
                        infl.last_send[rid]=now; infl.tries[rid]=tries+1
                        if tries+1==MAX_RETRIES:
                            self.audit.append({"event":"RETRY_LIMIT","sid":sid,"seq":infl.seq,"to":rid})

    def all_delivered(self)->bool:
        return all(len(tbl)==0 for tbl in self.inflight.values())

    def run_until_done(self, time_limit=RUNTIME_SEC, autosave_every=AUTOSAVE_EVERY):
        end=time.time()+time_limit; tick=0
        while time.time()<end and not self.all_delivered():
            self._deliver_bus(); self._retransmit_timeouts(); time.sleep(0.003)
            tick+=1
            if tick%autosave_every==0: self.save_state()
        self._deliver_bus(); self.save_state()

    def save_state(self):
        obj={"epoch_id":self.epoch_id,"roster":self.roster,
             "tape":self.tape.to_dict(),
             "members":{k:v.to_dict() for k,v in self.members.items()},
             "inflight":{sid:{str(seq):infl.to_dict() for seq,infl in tbl.items()} for sid,tbl in self.inflight.items()}}
        self.persist.save(obj)
        self.audit.append({"event":"CHECKPOINT","epoch":self.epoch_id,
                           "inflight_total":sum(len(tbl) for tbl in self.inflight.values())})

    def _restore(self)->bool:
        obj=self.persist.load()
        if not obj: return False
        try:
            self.epoch_id=obj["epoch_id"]; self.roster=obj["roster"]
            self.tape=GroupTape.from_dict(obj["tape"])
            self.members={mid:Member.from_dict(md) for mid,md in obj["members"].items()}
            self.inflight={sid:{int(seq):Inflight.from_dict(v) for seq,v in tbl.items()}
                           for sid,tbl in obj["inflight"].items()}
            self.audit.append({"event":"RESTORE_OK","epoch":self.epoch_id,
                               "inflight_total":sum(len(tbl) for tbl in self.inflight.values())})
            return True
        except Exception as e:
            self.audit.append({"event":"RESTORE_FAIL","reason":str(e)})
            return False

# ===== 実行デモ & ローテーション シナリオ =====
def run_demo():
    # 1) パスフレーズ読み取り
    if sys.stdin.isatty():
        pw = getpass.getpass("パスフレーズ（空でも可・デモ向け）: ")
    else:
        pw = ""  # 非対話環境は空

    # 2) ラップファイルから DEK を取得（無ければ新規作成）
    wrapper = KeyWrapper()
    data_DEK, audit_DEK = wrapper.create_or_load(pw)

    # 3) システム起動
    ids=["A","B","C"]
    chat = GroupReliablePersistent(ids, data_DEK, audit_DEK)

    # 4) 送信・配達
    if chat.all_delivered():
        for i in range(3):
            for sid in ids:
                chat.send(sid, f"{sid}-hello-{i+1}")
    chat.run_until_done()
    chat.audit.verify_all(verbose=True)

    # 5) 鍵ローテーション（データ鍵だけ更新→状態再保存→継続可能）
    print("\n--- 🔁 データ鍵ローテーションを試します ---")
    new_data_DEK, _ = wrapper.rotate(pw, which="data")
    # 新しい Persistence に差し替え（旧DEKで復号→新DEKで再暗号化）
    # 実運用では “読み出し→再保存” で再暗号化マイグレーションを行う
    migrator = Persistence(new_data_DEK)
    obj = chat.persist.load()
    if obj is None:
        print("状態読み出し失敗（ローテーション中止）")
        return
    migrator.save(obj)                 # 新DEKで再暗号化
    chat.persist = migrator            # 差し替え
    chat.audit.append({"event":"ROTATE_DATA_DEK","at":time.time()})

    # 6) ローテーション後も継続送信できることを確認
    for sid in ids:
        chat.send(sid, f"{sid}-after-rotate")
    chat.run_until_done()
    chat.audit.verify_all(verbose=True)

    # 結果
    for mid in ids:
        inbox = chat.members[mid].inbox
        print(f"=== {mid} 受信（{len(inbox)}通）===")
        print(", ".join(inbox)); print()

if __name__ == "__main__":
    run_demo()
