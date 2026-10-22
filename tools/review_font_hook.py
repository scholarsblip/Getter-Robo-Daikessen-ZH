from pathlib import Path
import json,struct,hashlib,sys,time
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'tools'));import getter_font as f
from extract_core_text import pointer_references
original=(root/'work/source/disc.provisional/SLPS_022.32').read_bytes();tables=f.native_tables(original);code,labels=f.lookup_code(3276,tables)

def run(mem,start,registers,stops,limit=40000):
 r=list(registers);pc=start;branch=None;load=None;hi=lo=0
 for steps in range(limit):
  if pc in stops:return r,mem,pc,steps
  b0=mem.get(pc,0);w=b0|mem.get(pc+1,0)<<8|mem.get(pc+2,0)<<16|mem.get(pc+3,0)<<24
  op=w>>26;rs=w>>21&31;rt=w>>16&31;rd=w>>11&31;sa=w>>6&31;fn=w&63;imm=w&65535;si=imm if imm<32768 else imm-65536
  last_branch=branch;branch=None;last_load=load;load=None;written=None;value=None
  if op==0:
   if fn==0:written=rd;value=r[rt]<<sa
   elif fn==2:written=rd;value=r[rt]>>sa
   elif fn==0x21:written=rd;value=r[rs]+r[rt]
   elif fn==0x24:written=rd;value=r[rs]&r[rt]
   elif fn==0x25:written=rd;value=r[rs]|r[rt]
   elif fn==0x2b:written=rd;value=int(r[rs]<r[rt])
   elif fn==0x19:p=r[rs]*r[rt];lo=p&0xffffffff;hi=p>>32
   elif fn==0x1b:lo,hi=divmod(r[rs],r[rt])
   elif fn==0x12:written=rd;value=lo
   elif fn==0x10:written=rd;value=hi
   else:raise ValueError(('unsupportedR',hex(pc),hex(w)))
  elif op==9:written=rt;value=r[rs]+si
  elif op==11:written=rt;value=int(r[rs]<(si&0xffffffff))
  elif op==12:written=rt;value=r[rs]&imm
  elif op==13:written=rt;value=r[rs]|imm
  elif op==15:written=rt;value=imm<<16
  elif op in (4,5):
   if (r[rs]==r[rt])==(op==4):branch=pc+4+si*4
  elif op in (2,3):
   if op==3:written=31;value=pc+8
   branch=((pc+4)&0xf0000000)|((w&0x3ffffff)<<2)
  elif op in (35,36,37):
   addr=(r[rs]+si)&0xffffffff;size={35:4,36:1,37:2}[op];load=(rt,sum(mem.get(addr+j,0)<<(j*8) for j in range(size)))
  elif op==43:
   addr=(r[rs]+si)&0xffffffff
   for j in range(4):mem[addr+j]=(r[rt]>>(j*8))&255
  else:raise ValueError(('unsupportedI',hex(pc),hex(w)))
  if last_load is not None and last_load[0] and last_load[0]!=written:r[last_load[0]]=last_load[1]&0xffffffff
  if written:r[written]=value&0xffffffff
  r[0]=0;pc=last_branch if last_branch is not None else pc+4
 raise ValueError(('noexit',hex(pc)))

def registers(char):
 r=[0x11220000+i for i in range(32)];r[0]=0;r[8]=char;r[21]=123;r[23]=456;r[30]=0x000c0000;r[29]=0x801ff000;return r

def assert_saved(r,old):assert all(r[q]==old[q] for q in (16,17,18,19,20,21,22,23,28,29,30))
mem_base={f.CAVE_ADDR+i:b for i,b in enumerate(code)};start=time.time();native_cases=custom_cases=0
for page,codes in enumerate(tables):
 for cell,char in enumerate(codes):
  initial=registers(char);r,m,stop,n=run(dict(mem_base),labels['lookup'],initial,{0x8004dae0,0x8004d6dc,0x8004dc80});assert_saved(r,initial)
  if char>>8<0x84:assert stop==0x8004dae0 and r[7]==char&255
  else:
   # Original initialized table ranges are searched in page order. Duplicate
   # entries in later pages are unreachable if an earlier range finds them.
   expected=next((p,t.index(char)) for p,t in enumerate(tables) if char in t)
   p,c=expected;desc=sum(m.get(initial[29]+0x10+j,0)<<(8*j) for j in range(4))
   assert stop==0x8004d6dc and r[6]==c and desc==labels['native_descriptors']+p*8,(page,cell,hex(char),hex(stop),r[6],p,c,hex(desc))
  native_cases+=1
for index in range(3276):
 char=((0xeb+index//188)<<8)+0x40+index%188+(index%188>=63);initial=registers(char);r,m,stop,n=run(dict(mem_base),labels['lookup'],initial,{0x8004dae0,0x8004d6dc,0x8004dc80});assert_saved(r,initial)
 plane,slot=divmod(index,1092);p=0 if slot<441 else 1 if slot<882 else 2;cell=slot-(0,441,882)[p];desc=sum(m.get(initial[29]+0x10+j,0)<<(8*j) for j in range(4))
 assert stop==0x8004d6dc and r[6]==cell and desc==labels['descriptors']+(plane*3+p)*8,(index,hex(stop),r[6],cell)
 custom_cases+=1
invalid=[0,0x20,0x8140,0x824f,0x8340,0x83ff,0x8400,0xeaff,0xeb00,0xeb3f,0xeb7f,0xebfd,0xecff,0xfc7f,0xfcfd,0xfd40,0xffff]
for char in invalid:
 initial=registers(char);r,m,stop,n=run(dict(mem_base),labels['lookup'],initial,{0x8004dae0,0x8004d6dc,0x8004dc80});assert_saved(r,initial);assert stop!=0x8004d6dc,(hex(char),hex(stop))
# Simulate actual startup clearing on a patched loaded image, with branch and
# one-instruction load delays enabled, rather than assuming file padding survives.
built=root/'work/font/build-reviewed-v2';plan=json.loads((built/'plan.json').read_text());patched=(built/'SLPS_022.32.font-only').read_bytes();actualcode,actual_labels=f.lookup_code(len(plan['glyphs']),tables)
assert patched[f.CAVE_OFF:f.CAVE_OFF+len(actualcode)]==actualcode
mem={f.BASE+i:b for i,b in enumerate(patched)}
for a in range(0x800833b0,0x8008b7a8):mem[a]=0xa5
before=bytes(mem[a] for a in range(f.CAVE_ADDR,f.BASE+f.CAVE_END));r,m,stop,n=run(mem,0x8001a3e4,[0]*32,{0x8001a408},100000)
after=bytes(m[a] for a in range(f.CAVE_ADDR,f.BASE+f.CAVE_END));assert before==after;assert all(m[a]==0 for a in range(0x800833b0,0x8008b7a8));assert patched[0x8001a3e4-f.BASE:0x8001a408-f.BASE]==original[0x8001a3e4-f.BASE:0x8001a408-f.BASE]
assert struct.unpack_from('<I',patched,0x8005205c-f.BASE)[0]==0x1000000e
assert patched[0x80052030-f.BASE:0x8005205c-f.BASE]==original[0x80052030-f.BASE:0x8005205c-f.BASE]
refs=[];gp_refs=[]
for name,b in [('SLPS_022.32',original)]+[(str(p.relative_to(root/'work/source/unpacked_vfs')),p.read_bytes()) for p in (root/'work/source/unpacked_vfs/bin').glob('*.bin')]:
 for address,items in pointer_references(b,name).items():
  if f.CAVE_ADDR<=address<f.BASE+f.CAVE_END:refs.append({'target':hex(address),'references':items})
 for o in range(0,len(b)-3,4):
  w=struct.unpack_from('<I',b,o)[0];imm=w&65535;si=imm if imm<32768 else imm-65536;addr=0x80082ac8+si
  if w>>21&31==28 and w>>26 in (32,33,35,36,37,40,41,43) and f.CAVE_ADDR<=addr<f.BASE+f.CAVE_END:
   if name=='SLPS_022.32' and f.CAVE_OFF<=o<f.CAVE_END:continue # old map data, not instructions
   gp_refs.append({'source':name,'offset':o,'target':hex(addr)})
assert len(refs)==3 and not gp_refs
assert all(all(x['kind']=='u32_le' and x['source']=='SLPS_022.32' and x['offset'] in (0x70f7c,0x70f80,0x70f84) for x in ref['references']) for ref in refs)
report={'version':'font-v2-reclaimed-native-map-cave','native_entry_cases':native_cases,'custom_index_cases':custom_cases,'invalid_fallback_cases':len(invalid),'mips_branch_and_load_delays_modeled':True,'callee_saved_registers_pass':True,'compiled_bytes':len(actualcode),'reclaimed_region_bytes':f.CAVE_END-f.CAVE_OFF,'native_compact_bytes':len(f.compact_native(tables)),'startup_bss_zero_simulation':'pass; unchanged0x800833b0..0x8008b7a8 zero loop preserves cave0x800807f4..0x8008108c','native_initializer_skip':'pass; branch to0x80052098, symbol/kana initialization bytes unchanged','references_to_reclaimed_data':refs,'other_direct_gp_references':gp_refs,'original_japanese_duplicates':'U+space0x8140 uses unchanged simple path;0x8E9Fand0x90AB duplicate later entries resolve earlier native page as original.','reviewed_binary_sha256':hashlib.sha256(patched).hexdigest(),'blocking_findings':[],'elapsed_seconds':round(time.time()-start,2),'limits':'Static and instruction-level tests do not prove GPU/runtime/gameplay compatibility or completeness of indirect pointer-use analysis.'}
(root/'verification').mkdir(parents=True,exist_ok=True)
(root/'verification/font_v2_review.generated.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report,ensure_ascii=False,indent=2))
