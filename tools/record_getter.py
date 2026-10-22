#!/usr/bin/env python3
"""Continuous original gameplay video/audio recorder for Getter QA.

This is a standalone libretro frontend derived from qa_getter.py. It never
captures the desktop or injects RAM. Documented input schedules drive the game.
The reported display aspect is preserved across native resolution switches.
"""
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import time
import re
import subprocess
import wave
import struct

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1] / 'work' / 'qa' / 'recording_runtime'
parser = argparse.ArgumentParser()
parser.add_argument('game')
parser.add_argument('--core',default=str(ROOT/'cores/pcsx_rearmed_libretro.dylib'))
parser.add_argument('--frames',type=int,default=1800)
parser.add_argument('--captures',default='60,300,600,900,1200,1800')
parser.add_argument('--schedule')
parser.add_argument('--output',default=str(ROOT/'captures'))
parser.add_argument('--save-state')
parser.add_argument('--load-state')
parser.add_argument('--checkpoint-states',default='',help='Comma-separated frame numbers to save matching-build diagnostic states')
parser.add_argument('--dump-memory',action='store_true',help='Dump exposed libretro RAM/VRAM at the end of the run')
parser.add_argument('--dry-run',action='store_true')
parser.add_argument('--option',action='append',default=[],help='Documented core option key=value')
parser.add_argument('--system-dir')
parser.add_argument('--registers',action='store_true',help='Read native core registers for diagnostics; never modify')
parser.add_argument('--record-output',required=True)
parser.add_argument('--ffmpeg',required=True)
parser.add_argument('--record-every',type=int,default=2)
args=parser.parse_args()
capture_frames={int(x) for x in args.captures.split(',') if x}
checkpoint_frames={int(x) for x in args.checkpoint_states.split(',') if x}
schedule=json.loads(Path(args.schedule).read_text()) if args.schedule else []
out=Path(args.output).resolve()
settings={
 'pcsx_rearmed_bios':b'HLE',
 'pcsx_rearmed_region':b'Auto',
 'pcsx_rearmed_show_bios_bootlogo':b'disabled',
 'pcsx_rearmed_drc':b'disabled',
 'pcsx_rearmed_gpu_thread_rendering':b'disabled',
 'pcsx_rearmed_spu_thread':b'disabled',
}
dirs={9:str(ROOT/'system').encode(),31:str(ROOT/'saves').encode(),30:str(ROOT).encode()}
if args.system_dir:dirs[9]=str(Path(args.system_dir).resolve()).encode()
for value in args.option:
 key,separator,val=value.partition('=');assert separator and re.fullmatch(r'[A-Za-z0-9_]+',key)
 settings[key]=val.encode()
buttons={'b':0,'y':1,'select':2,'start':3,'up':4,'down':5,'left':6,'right':7,'a':8,'x':9,'l':10,'r':11,'l2':12,'r2':13,'l3':14,'r3':15}
if args.dry_run:
 print(json.dumps({'game':str(Path(args.game).resolve()),'core':args.core,'frames':args.frames,'captures':sorted(capture_frames),'checkpoint_states':sorted(checkpoint_frames),'schedule':schedule,'bios':'built-in HLE','output':str(out)},indent=2));raise SystemExit(0)
out.mkdir(parents=True,exist_ok=True)
for b in dirs.values():Path(b.decode()).mkdir(parents=True,exist_ok=True)
core=C.CDLL(str(Path(args.core).resolve()))
frame=0
pix_fmt=0
last_frame=None
last_raw=None
events=[]
refs=[]
log_events=[]
ENV=C.CFUNCTYPE(C.c_bool,C.c_uint,C.c_void_p)
VIDEO=C.CFUNCTYPE(None,C.c_void_p,C.c_uint,C.c_uint,C.c_size_t)
AUDIO=C.CFUNCTYPE(None,C.c_int16,C.c_int16)
AUDIO_BATCH=C.CFUNCTYPE(C.c_size_t,C.POINTER(C.c_int16),C.c_size_t)
INPUT_POLL=C.CFUNCTYPE(None)
INPUT_STATE=C.CFUNCTYPE(C.c_int16,C.c_uint,C.c_uint,C.c_uint,C.c_uint)
LOG=C.CFUNCTYPE(None,C.c_int,C.c_char_p)

@LOG
def logger(level,fmt):
 if fmt and len(log_events)<500:
  log_events.append({'level':level,'format':fmt.decode('utf-8','replace')})

native_log_path=Path(__file__).with_name('getter_core_log.dylib')
if native_log_path.exists():
 native_log_lib=C.CDLL(str(native_log_path))
 native_log_lib.getter_core_log_set_path.argtypes=[C.c_char_p]
 native_log_lib.getter_core_log_set_path(str(out/'core.log').encode())
 logger=C.cast(native_log_lib.getter_core_log,LOG)

class LogInterface(C.Structure):_fields_=[('log',LOG)]

class Variable(C.Structure):_fields_=[('key',C.c_char_p),('value',C.c_char_p)]
class SystemInfo(C.Structure):_fields_=[('library_name',C.c_char_p),('library_version',C.c_char_p),('valid_extensions',C.c_char_p),('need_fullpath',C.c_bool),('block_extract',C.c_bool)]
class GameInfo(C.Structure):_fields_=[('path',C.c_char_p),('data',C.c_void_p),('size',C.c_size_t),('meta',C.c_char_p)]

@ENV
def env(cmd,data):
 global pix_fmt
 cmd=cmd&0xffff
 if cmd==10:
  pix_fmt=C.cast(data,C.POINTER(C.c_int))[0];return pix_fmt in (0,1,2)
 if cmd in dirs:
  C.cast(data,C.POINTER(C.c_char_p))[0]=dirs[cmd];return True
 if cmd==15:
  v=C.cast(data,C.POINTER(Variable)).contents
  k=v.key.decode()
  if k in settings:v.value=settings[k];return True
  return False
 if cmd==16:
  v=C.cast(data,C.POINTER(Variable));i=0
  while v[i].key:
   k=v[i].key.decode();raw=v[i].value or b''
   if k not in settings and b'; ' in raw:settings[k]=raw.split(b'; ',1)[1].split(b'|')[0]
   i+=1
  return True
 if cmd==17:
  C.cast(data,C.POINTER(C.c_bool))[0]=False;return True
 if cmd==27:
  C.cast(data,C.POINTER(LogInterface)).contents.log=logger;return True
 if cmd==3:
  C.cast(data,C.POINTER(C.c_bool))[0]=True;return True
 if cmd==51:return True
 if cmd==52:
  C.cast(data,C.POINTER(C.c_uint))[0]=0;return True
 if cmd==39:
  C.cast(data,C.POINTER(C.c_uint))[0]=0;return True
 if cmd==49:
  C.cast(data,C.POINTER(C.c_bool))[0]=True;return True
 if cmd in (1,6,11,18,32,35,37):return True
 return False

def convert(data,w,h,pitch):
 raw=data if isinstance(data,bytes) else C.string_at(data,pitch*h)
 if pix_fmt==1:
  a=np.frombuffer(raw,dtype=np.uint8).reshape(h,pitch)[:,:w*4].reshape(h,w,4)
  return Image.fromarray(a[:,:,[2,1,0]],'RGB')
 a=np.frombuffer(raw,dtype='<u2').reshape(h,pitch//2)[:,:w]
 if pix_fmt==2:r=(a>>11)&31;g=(a>>5)&63;b=a&31;gm=63
 else:r=(a>>10)&31;g=(a>>5)&31;b=a&31;gm=31
 rgb=np.stack([(r.astype(np.uint32)*255//31),(g.astype(np.uint32)*255//gm),(b.astype(np.uint32)*255//31)],axis=-1).astype(np.uint8)
 return Image.fromarray(rgb,'RGB')

@VIDEO
def video(data,w,h,pitch):
 global last_frame,last_raw
 if data and data!=C.c_void_p(-1).value:
  last_raw=(C.string_at(data,pitch*h),w,h,pitch)
 if frame in capture_frames and last_raw:
  raw,w,h,pitch=last_raw
  im=convert(raw,w,h,pitch);p=out/('frame_%06d.png'%frame);im.save(p)
  events.append({'frame':frame,'image':str(p),'width':w,'height':h,'pixel_format':pix_fmt,'nonzero':bool(np.asarray(im).any())})
  print('CAPTURE',frame,w,h,flush=True)
  last_frame=im

recording_active=False
audio_writer=None
audio_frames=0
@AUDIO
def audio(l,r):
 global audio_frames
 if recording_active and audio_writer:
  audio_writer.writeframesraw(struct.pack('<hh',l,r));audio_frames+=1
@AUDIO_BATCH
def audio_batch(data,n):
 global audio_frames
 if recording_active and audio_writer and n:
  audio_writer.writeframesraw(C.string_at(data,n*4));audio_frames+=n
 return n
@INPUT_POLL
def poll():pass
@INPUT_STATE
def inp(port,device,index,ident):
 if port!=0 or device!=1:return 0
 active=set()
 for row in schedule:
  if row['start']<=frame<=row['end']:active.update(buttons[b] for b in row['buttons'])
 if ident==256:return sum(1<<b for b in active)
 return int(ident in active)

for name,fn in [('environment',env),('video_refresh',video),('audio_sample',audio),('audio_sample_batch',audio_batch),('input_poll',poll),('input_state',inp)]:
 f=getattr(core,'retro_set_'+name);f.argtypes=[type(fn)];f(fn);refs.append(fn)
core.retro_api_version.restype=C.c_uint
core.retro_init.argtypes=[];core.retro_init()
si=SystemInfo();core.retro_get_system_info.argtypes=[C.POINTER(SystemInfo)];core.retro_get_system_info(C.byref(si))
print('CORE',si.library_name,si.library_version,'fullpath',si.need_fullpath,flush=True)
path=str(Path(args.game).resolve()).encode();content=None
if not si.need_fullpath:
 blob=Path(args.game).read_bytes();content=C.create_string_buffer(blob)
gi=GameInfo(path,C.cast(content,C.c_void_p) if content else None,len(blob) if content else 0,None)
core.retro_load_game.argtypes=[C.POINTER(GameInfo)];core.retro_load_game.restype=C.c_bool
assert core.retro_load_game(C.byref(gi)),'retro_load_game failed'
core.retro_set_controller_port_device.argtypes=[C.c_uint,C.c_uint];core.retro_set_controller_port_device(0,1)
core.retro_serialize_size.restype=C.c_size_t
if args.load_state:
 state=Path(args.load_state).read_bytes();buf=C.create_string_buffer(state)
 core.retro_unserialize.argtypes=[C.c_void_p,C.c_size_t];core.retro_unserialize.restype=C.c_bool
 assert core.retro_unserialize(buf,len(state)),'state restore failed'

register_events=[]
def read_registers(at):
 if not args.registers:return
 try:
  registers=(C.c_uint32*210).in_dll(core,'psxRegs')
  event={'frame':at,'pc':hex(registers[130]),'sp':hex(registers[29]),'gp':hex(registers[28]),
         'gpr':[hex(registers[i]) for i in range(32)]}
  register_events.append(event);print('REGISTERS',json.dumps(event),flush=True)
 except ValueError as error:print('REGISTERS_UNAVAILABLE',str(error),flush=True)
read_registers(0)

class Geometry(C.Structure):
 _fields_=[('base_width',C.c_uint),('base_height',C.c_uint),('max_width',C.c_uint),('max_height',C.c_uint),('aspect_ratio',C.c_float)]
class Timing(C.Structure):_fields_=[('fps',C.c_double),('sample_rate',C.c_double)]
class AVInfo(C.Structure):_fields_=[('geometry',Geometry),('timing',Timing)]
av=AVInfo();core.retro_get_system_av_info.argtypes=[C.POINTER(AVInfo)];core.retro_get_system_av_info(C.byref(av))
assert av.timing.fps>0 and av.timing.sample_rate>0
record_path=Path(args.record_output).resolve();record_path.parent.mkdir(parents=True,exist_ok=True)
assert not record_path.exists(),record_path
video_path=record_path.with_suffix('.video-only.mp4')
audio_path=record_path.with_suffix('.audio.wav')
assert not video_path.exists() and not audio_path.exists()
record_fps=av.timing.fps/args.record_every
encoder_log=open(out/'encoder.log','wb')
encoder=subprocess.Popen([args.ffmpeg,'-nostdin','-hide_banner','-loglevel','warning','-f','rawvideo','-pixel_format','rgb24','-video_size','640x480','-framerate',f'{record_fps:.12f}','-i','pipe:0','-an','-c:v','libx264','-preset','veryfast','-crf','17','-pix_fmt','yuv420p','-movflags','+faststart',str(video_path)],stdin=subprocess.PIPE,stderr=encoder_log)
audio_writer=wave.open(str(audio_path),'wb');audio_writer.setnchannels(2);audio_writer.setsampwidth(2);audio_writer.setframerate(round(av.timing.sample_rate))
recorded_frames=0
recording_active=True
print('RECORD',json.dumps({'fps':record_fps,'native_fps':av.timing.fps,'sample_rate':av.timing.sample_rate,'display_aspect':av.geometry.aspect_ratio,'video':str(record_path)}),flush=True)
t=time.monotonic()
checkpoint_events=[]
def save_state_to(destination):
 n=core.retro_serialize_size();buf=C.create_string_buffer(n)
 core.retro_serialize.argtypes=[C.c_void_p,C.c_size_t];core.retro_serialize.restype=C.c_bool
 assert core.retro_serialize(buf,n),'state save failed'
 Path(destination).write_bytes(buf.raw)
for frame in range(1,args.frames+1):
 core.retro_run()
 if frame%args.record_every==0:
  if last_raw:
   raw,w,h,pitch=last_raw;im=convert(raw,w,h,pitch)
   # Libretro geometry reports display aspect; PS1 resolution switches retain4:3.
   aspect=av.geometry.aspect_ratio if av.geometry.aspect_ratio>0 else 4/3
   target_w=min(640,round(480*aspect));target_h=min(480,round(640/aspect))
   im=im.resize((target_w,target_h),Image.Resampling.NEAREST)
   canvas=Image.new('RGB',(640,480));canvas.paste(im,((640-target_w)//2,(480-target_h)//2))
  else:canvas=Image.new('RGB',(640,480))
  encoder.stdin.write(canvas.tobytes());recorded_frames+=1
 if frame in capture_frames:read_registers(frame)
 if frame in checkpoint_frames:
  checkpoint=out/('frame_%06d.state'%frame);save_state_to(checkpoint)
  checkpoint_events.append({'frame':frame,'state':str(checkpoint)})
  print('CHECKPOINT',frame,str(checkpoint),flush=True)
if args.save_state:save_state_to(args.save_state)
if args.dump_memory:
 core.retro_get_memory_size.argtypes=[C.c_uint];core.retro_get_memory_size.restype=C.c_size_t
 core.retro_get_memory_data.argtypes=[C.c_uint];core.retro_get_memory_data.restype=C.c_void_p
 for ident,label in [(0,'save_ram'),(1,'rtc'),(2,'system_ram'),(3,'video_ram')]:
  n=core.retro_get_memory_size(ident);ptr=core.retro_get_memory_data(ident)
  if ptr and n:
   p=out/(label+'.bin');p.write_bytes(C.string_at(ptr,n));print('MEMORY',ident,label,n,str(p),flush=True)
  else:print('MEMORY_UNAVAILABLE',ident,label,n,flush=True)
recording_active=False
audio_writer.close();encoder.stdin.close();assert encoder.wait()==0,'Video encoder failed; see encoder.log'
encoder_log.close()
assert audio_frames>0,'No original game audio captured'
subprocess.run([args.ffmpeg,'-nostdin','-hide_banner','-loglevel','warning','-i',str(video_path),'-i',str(audio_path),'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','192k','-shortest','-movflags','+faststart',str(record_path)],check=True)
core.retro_unload_game();core.retro_deinit()
report={'core':si.library_name.decode(),'version':si.library_version.decode(),'game':path.decode(),'frames':args.frames,'seconds':round(time.monotonic()-t,2),'bios':'HLE','settings':{k:v.decode() for k,v in settings.items()},'captures':events,'checkpoint_states':checkpoint_events}
report['recording']={'output':str(record_path),'video_frames':recorded_frames,'video_fps':record_fps,'video_seconds':recorded_frames/record_fps,'audio_sample_frames':audio_frames,'audio_sample_rate':av.timing.sample_rate,'audio_seconds':audio_frames/av.timing.sample_rate,'canvas':[640,480],'display_aspect':av.geometry.aspect_ratio,'original_game_audio':True,'frame_sampling':f'one video frame per {args.record_every} emulated frames, native emulation timing retained','native_resolution_changes_preserve_reported_display_aspect':True,'source_state_sha256':hashlib.sha256(Path(args.load_state).read_bytes()).hexdigest() if args.load_state else None,'schedule_sha256':hashlib.sha256(Path(args.schedule).read_bytes()).hexdigest() if args.schedule else None}
report['registers']=register_events
report['core_log_formats']=log_events
report['bios']='HLE' if settings['pcsx_rearmed_bios']==b'HLE' else 'auto-detected; see core.log'
if si.library_name==b'SwanStation':
 report['bios']='OpenBIOS' if settings.get('swanstation_BIOS_PathNTSCJ')==b'openbios.bin' else 'SwanStation-selected; see core.log'
report['native_core_log']=str(out/'core.log') if native_log_path.exists() else None
(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print('DONE',json.dumps({'frames':args.frames,'seconds':report['seconds'],'captures':len(events)}),flush=True)
