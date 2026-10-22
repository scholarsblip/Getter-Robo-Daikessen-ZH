#!/usr/bin/env python3
"""Independent 12px Chinese font and PS1 lookup for Getter Robo Daikessen.

Native Japanese kanji retain their bitmap shapes in bitplane 0. Three further
bitplanes give 3276 Chinese cells without changing texture VRAM allocations.
A custom CLUT occupies the unused four rows below the native kanji textures.
"""
from pathlib import Path
import argparse, hashlib, json, struct, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]
SOURCE_SHA='edc4b01e09708d64db21430ed341e4fb222799089a2ca360f329a8fe15f5bb8b'
FONT_SHA=''
CAPACITY=1092*3
CAVE_OFF=0x70ff4
CAVE_END=0x7188c
CAVE_ADDR=0x800807f4
BASE=0x8000f800
CLUT=0x7f38 # x896,y508; palette columns 0..3, bitplane rows 0..3
SHEETS=('font12j0.tim','font12j1.tim','font12j2.tim')


def tim_pixels(data):
    if data[:8]!=b'\x10\x00\x00\x00\x08\x00\x00\x00':raise ValueError('Expected 4bpp TIM')
    csize=struct.unpack_from('<I',data,8)[0]; pos=8+csize
    size,x,y,w,h=struct.unpack_from('<IHHHH',data,pos)
    if pos+size!=len(data):raise ValueError('TIM trailing data')
    raw=np.frombuffer(data[pos+12:],np.uint8).reshape(h,w*2)
    pixels=np.zeros((h,w*4),np.uint8);pixels[:,::2]=raw&15;pixels[:,1::2]=raw>>4
    return pixels,(x,y,w,h),pos


def replace_tim(data,pixels,clut=None):
    old,rect,pos=tim_pixels(data)
    if old.shape!=pixels.shape:raise ValueError('Texture dimension changed')
    if clut is None:header=data[:pos]
    else:
        x,y,w,h,colors=clut
        header=data[:8]+struct.pack('<IHHHH',12+w*h*2,x,y,w,h)+np.asarray(colors,dtype='<u2').tobytes()
    raw=(pixels[:,::2]|pixels[:,1::2]<<4).astype(np.uint8).tobytes()
    return header+data[pos:pos+12]+raw


def needs_custom(ch):
    if 0x2e80<=ord(ch)<=0x9fff or 0xf900<=ord(ch)<=0xfaff:return True
    try:ch.encode('cp932');return False
    except UnicodeEncodeError:return True


def make_plan(texts):
    chars=sorted({ch for t in texts for ch in t if needs_custom(ch)})
    if len(chars)>CAPACITY:raise ValueError(f'{len(chars)} Chinese characters exceed {CAPACITY} cells')
    codes={ch:((0xeb+i//188)<<8)+(0x40+i%188+(i%188>=63)) for i,ch in enumerate(chars)}
    return {'format':'Getter custom SJIS leads EB-FC','characters':len(chars),'capacity':CAPACITY,
            'glyphs':codes,'clut_vram':[896,508,64,4],'native_texture_rectangles_preserved':True,
            'native_japanese_bitmap_shapes_retained':True,'pixel_cell':[12,12],
            'font':'Cubic11 size12, native 11px bitmap ink','runtime_verified':False,
            'limitations':['Kanji uses monochrome pixels; four main text colours retained.']}


def encode(text,plan):
    out=bytearray()
    for ch in text:
        if ch in plan['glyphs']:out+=int(plan['glyphs'][ch]).to_bytes(2,'big')
        else:out+=ch.encode('cp932')
    return bytes(out)


def decode(raw,plan):
    reverse={int(v):k for k,v in plan['glyphs'].items()};out=[];i=0
    while i<len(raw):
        b=raw[i];wide=0x81<=b<=0x9f or 0xe0<=b<=0xfc
        part=raw[i:i+(2 if wide else 1)]
        code=int.from_bytes(part,'big')
        out.append(reverse[code] if code in reverse else part.decode('cp932'));i+=len(part)
    return ''.join(out)


def render_cell(ch,font,fallback=None):
    if fallback and ch in fallback:return fallback[ch].copy()
    if ch.isspace():return np.zeros((12,12),np.uint8)
    im=Image.new('L',(40,24));ImageDraw.Draw(im).text((8,1),ch,font=font,fill=255)
    a=np.asarray(im);ys,xs=np.nonzero(a>=128)
    if not len(xs):raise ValueError(f'No ink for {ch!r}')
    ink=a[ys.min():ys.max()+1,xs.min():xs.max()+1]
    if ink.shape[0]>12 or ink.shape[1]>12:raise ValueError(f'Glyph exceeds cell: {ch!r} {ink.shape}')
    out=np.zeros((12,12),np.uint8);x=(12-ink.shape[1])//2;y=max(0,11-ink.shape[0]);out[y:y+ink.shape[0],x:x+ink.shape[1]]=ink>=128
    return out


def bdf_cells(path,characters):
    """Read exact 12px WenQuanYi cells; never scale or substitute a character."""
    wanted={ord(c):c for c in characters};result={};ascent=10
    text=Path(path).read_text()
    import re
    found=re.search(r'^FONT_ASCENT (\d+)$',text,re.M)
    if found:ascent=int(found.group(1))
    for block in text.split('STARTCHAR ')[1:]:
        enc=re.search(r'^ENCODING (\d+)$',block,re.M)
        if not enc or int(enc.group(1)) not in wanted:continue
        ch=wanted[int(enc.group(1))]
        match=re.search(r'^BBX (\d+) (\d+) (-?\d+) (-?\d+)$',block,re.M)
        w,h,x,y=map(int,match.groups())
        # WQY carries extra global Latin ascender space. Align its intact CJK
        # ink to the same eleven-pixel baseline as Cubic11, with no resampling.
        x=(12-w)//2;start_y=max(0,11-h)
        if w>12 or h>12:raise ValueError('BDF glyph outside 12px cell '+ch)
        bitmap=block.split('BITMAP',1)[1].split('ENDCHAR',1)[0].strip().splitlines()
        if len(bitmap)!=h:raise ValueError('BDF bitmap height mismatch')
        cell=np.zeros((12,12),np.uint8)
        for row,line in enumerate(bitmap):
            bits=''.join(f'{int(digit,16):04b}' for digit in line.strip())
            cell[start_y+row,x:x+w]=[int(bit) for bit in bits[:w]]
        result[ch]=cell
    if set(result)!=set(characters):raise ValueError('Missing BDF glyphs '+repr(set(characters)-set(result)))
    return result


def font_codepoints(path):
    """Read Unicode cmap4/12 directly, so Pillow tofu cannot pass as a glyph."""
    data=Path(path).read_bytes();num=struct.unpack_from('>H',data,4)[0];tables={}
    for i in range(num):
        tag,_,offset,length=struct.unpack_from('>4sIII',data,12+i*16);tables[tag]=(offset,length)
    base,_=tables[b'cmap'];count=struct.unpack_from('>H',data,base+2)[0];result=set();seen=set()
    for i in range(count):
        platform,encoding,offset=struct.unpack_from('>HHI',data,base+4+i*8)
        if platform not in (0,3) or offset in seen:continue
        seen.add(offset);p=base+offset;fmt=struct.unpack_from('>H',data,p)[0]
        if fmt==12:
            n=struct.unpack_from('>I',data,p+12)[0]
            for j in range(n):
                start,end,glyph=struct.unpack_from('>III',data,p+16+j*12)
                result.update(range(start+(glyph==0),end+1))
        elif fmt==4:
            n=struct.unpack_from('>H',data,p+6)[0]//2;ends=p+14;starts=ends+n*2+2;deltas=starts+n*2;ranges=deltas+n*2
            for j in range(n):
                end=struct.unpack_from('>H',data,ends+j*2)[0];start=struct.unpack_from('>H',data,starts+j*2)[0]
                delta=struct.unpack_from('>h',data,deltas+j*2)[0];ro=struct.unpack_from('>H',data,ranges+j*2)[0]
                for cp in range(start,min(end,65534)+1):
                    if ro:
                        glyph=struct.unpack_from('>H',data,ranges+j*2+ro+(cp-start)*2)[0]
                        if glyph:glyph=(glyph+delta)&65535
                    else:glyph=(cp+delta)&65535
                    if glyph:result.add(cp)
    if not result:raise ValueError('No supported Unicode cmap found')
    return result


def build_sheets(plan,sources,font_path):
    font=ImageFont.truetype(str(font_path),12)
    available=font_codepoints(font_path)
    missing=[ch for ch in plan['glyphs'] if ord(ch) not in available]
    for ch in plan['glyphs']:
        if ch in missing:continue
        try:render_cell(ch,font)
        except ValueError:missing.append(ch)
    fallback={}
    if missing:
        bdf_path=ROOT/'incoming/WenQuanYi/wenquanyi_9pt.bdf'
        fallback=bdf_cells(bdf_path,missing)
        plan['exact_12px_wenquanyi_fallbacks']=missing
        plan['wenquanyi_bdf_sha256']=hashlib.sha256(bdf_path.read_bytes()).hexdigest()
    pixels=[]
    for name in SHEETS:
        old,rect,pos=tim_pixels(sources[name]);pixels.append((old<10).astype(np.uint8))
    previews=[]
    for i,ch in enumerate(plan['glyphs']):
        plane,slot=divmod(i,1092);page=0 if slot<441 else 1 if slot<882 else 2
        local=slot-(0,441,882)[page];row,col=divmod(local,21)
        cell=render_cell(ch,font,fallback);pixels[page][row*12:row*12+12,col*12:col*12+12]|=cell<<(plane+1)
        if i<240:previews.append((ch,cell))
    palette=np.zeros((4,64),dtype=np.uint16)
    colors=(0x7fff,0x77bf,0x7fbd,0x77fd)
    for plane in range(4):
        for color in range(4):
            for idx in range(16):palette[plane,color*16+idx]=colors[color] if idx&(1<<plane) else 0
    assets={name:replace_tim(sources[name],pix,(896,508,64,4,palette) if name==SHEETS[-1] else None)
            for name,pix in zip(SHEETS,pixels)}
    # Bitplane identity and legacy glyph shapes are checked directly after TIM encode.
    for name,pix in zip(SHEETS,pixels):
        check,*_=tim_pixels(assets[name]);assert np.array_equal(check,pix)
        old,*_=tim_pixels(sources[name]);assert np.array_equal(check&1,(old<10).astype(np.uint8))
    for i,ch in enumerate(plan['glyphs']):
        plane,slot=divmod(i,1092);page=0 if slot<441 else 1 if slot<882 else 2
        row,col=divmod(slot-(0,441,882)[page],21)
        got=(pixels[page][row*12:row*12+12,col*12:col*12+12]>>(plane+1))&1
        assert np.array_equal(got,render_cell(ch,font,fallback)),ch
    return assets,previews


class Mips:
    def __init__(self,base):self.base=base;self.words=[];self.labels={};self.fix=[]
    @property
    def pc(self):return self.base+4*len(self.words)
    def label(self,name):self.labels[name]=self.pc
    def w(self,w):self.words.append(w&0xffffffff)
    def i(self,op,rt,rs,imm):self.w(op<<26|rs<<21|rt<<16|(imm&0xffff))
    def r(self,fun,rd,rs,rt,sa=0):self.w(rs<<21|rt<<16|rd<<11|sa<<6|fun)
    def li(self,rt,x):self.i(9,rt,0,x)
    def move(self,rd,rs):self.r(0x21,rd,rs,0)
    def branch(self,op,rs,rt,label):self.fix.append((len(self.words),'branch',label));self.i(op,rt,rs,0)
    def jump(self,target,link=False):
        if isinstance(target,str):self.fix.append((len(self.words),'jal' if link else 'jump',target));self.w(0)
        else:self.w((3 if link else 2)<<26|((target>>2)&0x3ffffff))
    def nop(self):self.w(0)
    def address(self,rt,label):
        self.fix.append((len(self.words),'hi',label));self.i(15,rt,0,0)
        self.fix.append((len(self.words),'lo',label));self.i(13,rt,rt,0)
    def finish(self):
        for idx,kind,label in self.fix:
            addr=self.labels[label]
            if kind=='branch':self.words[idx]|=((addr-(self.base+idx*4+4))//4)&0xffff
            elif kind in ('jump','jal'):self.words[idx]=(3 if kind=='jal' else 2)<<26|((addr>>2)&0x3ffffff)
            else:self.words[idx]|=(addr>>16 if kind=='hi' else addr)&0xffff
        return struct.pack('<%dI'%len(self.words),*self.words)


def native_tables(exe):
    tables=[]
    for address in (0x800807f4,0x80080b6c,0x80080ee4):
        offset=address-BASE+4;codes=[]
        while exe[offset]:
            codes.append(int.from_bytes(exe[offset:offset+2],'big'));offset+=2
        tables.append(codes)
    if list(map(len,tables))!=[441,441,209]:raise ValueError('Unexpected original Japanese map')
    return tables


def compact_native(tables):
    out=bytearray()
    for codes in tables:
        out+=struct.pack('<H',len(codes));previous=0
        for code in codes:
            delta=code-previous
            out+=bytes([delta]) if 0<=delta<128 else b'\x80'+code.to_bytes(2,'big')
            previous=code
        if len(out)%2:out+=b'\0'
    # Verify all glyph indexes, duplicates and original codes survive exactly.
    cursor=0
    for expected in tables:
        count=struct.unpack_from('<H',out,cursor)[0];cursor+=2;value=0;actual=[]
        for _ in range(count):
            delta=out[cursor];cursor+=1
            if delta==128:value=int.from_bytes(out[cursor:cursor+2],'big');cursor+=2
            else:value+=delta
            actual.append(value)
        cursor=(cursor+1)&~1
        if actual!=expected:raise ValueError('Compact native map roundtrip failed')
    return bytes(out)


def lookup_code(nchars,tables=None):
    if tables is None:tables=native_tables((ROOT/'work/source/disc.provisional/SLPS_022.32').read_bytes())
    # Registers: v0=2,v1=3,a0..3=4..7,t0..7=8..15,t8=24,s5=21,s7=23,fp=30,sp=29.
    a=Mips(CAVE_ADDR)
    a.label('lookup')
    a.i(12,7,8,255) # original displaced andi a3,t0,255
    a.i(12,10,8,65535);a.r(2,11,0,10,8);a.i(9,11,11,-0xeb)
    a.i(11,2,11,18);a.branch(4,2,0,'fallback');a.nop()
    a.i(9,12,7,-0x40);a.i(11,2,12,0xbd);a.branch(4,2,0,'fallback');a.nop()
    a.li(2,0x7f);a.branch(4,7,2,'fallback');a.nop()
    a.i(11,2,7,0x80);a.branch(5,2,0,'trail_done');a.nop();a.i(9,12,12,-1)
    a.label('trail_done');a.li(13,188);a.r(0x19,0,11,13);a.r(0x12,10,0,0);a.r(0x21,10,10,12)
    a.i(11,2,10,nchars);a.branch(4,2,0,'fallback');a.nop()
    a.li(13,1092);a.r(0x1b,0,10,13);a.r(0x12,12,0,0);a.r(0x10,6,0,0)
    a.li(13,0);a.i(11,2,6,441);a.branch(5,2,0,'page_done');a.nop()
    a.i(9,6,6,-441);a.li(13,1);a.i(11,2,6,441);a.branch(5,2,0,'page_done');a.nop()
    a.i(9,6,6,-441);a.li(13,2)
    a.label('page_done');a.r(0,2,0,12,1);a.r(0x21,12,12,2);a.r(0x21,12,12,13);a.r(0,12,0,12,3)
    a.address(9,'descriptors');a.r(0x21,9,9,12)
    a.label('draw');a.i(43,9,29,0x10)
    a.move(4,21);a.move(5,23);a.move(7,30);a.jump(0x8004d6dc,True);a.nop();a.jump(0x8004dcc4);a.nop()
    a.label('fallback')
    a.r(2,3,0,10,8);a.i(11,2,3,0x84);a.branch(5,2,0,'native_simple');a.nop()
    a.address(13,'native_data');a.li(12,0)
    a.label('native_page');a.i(37,14,13,0);a.i(9,13,13,2);a.li(6,0);a.li(11,0)
    a.label('native_next');a.i(36,2,13,0);a.i(9,13,13,1);a.li(3,128)
    a.branch(4,2,3,'native_absolute');a.nop();a.r(0x21,11,11,2);a.jump('native_compare');a.nop()
    a.label('native_absolute');a.i(36,11,13,0);a.i(36,3,13,1);a.r(0,11,0,11,8);a.r(0x25,11,11,3);a.i(9,13,13,2)
    a.label('native_compare');a.branch(4,11,10,'native_found');a.nop();a.i(9,6,6,1)
    a.r(0x2b,2,6,14);a.branch(5,2,0,'native_next');a.nop()
    a.i(9,13,13,1);a.li(14,-2);a.r(0x24,13,13,14);a.i(9,12,12,1)
    a.i(11,2,12,3);a.branch(5,2,0,'native_page');a.nop();a.jump(0x8004dc80);a.nop()
    a.label('native_found');a.r(0,12,0,12,3);a.address(9,'native_descriptors');a.r(0x21,9,9,12);a.jump('draw');a.nop()
    a.label('native_simple');a.jump(0x8004dae0);a.nop()
    a.label('palette_proxy');a.i(35,15,29,0x10);a.nop();a.i(37,24,15,4);a.nop()
    a.i(9,24,24,-CLUT);a.i(11,24,24,193);a.branch(4,24,0,'palette_done');a.nop()
    a.i(15,15,0,0xfff3);a.i(13,15,15,0xffff);a.r(0x24,7,7,15)
    a.label('palette_done');a.i(9,29,29,-0x28);a.i(43,19,29,0x1c);a.jump(0x8004d6e4);a.nop()
    a.label('descriptors')
    descriptors=((30,0,0,21),(29,0,0,21),(11,0,128,21))
    for plane in (1,2,3):
        for page,u,v,cols in descriptors:
            a.w(page|(u<<16)|(v<<24));a.w((CLUT+plane*64)|(cols<<16))
    a.label('native_descriptors')
    for page,u,v,cols in descriptors:a.w(page|(u<<16)|(v<<24));a.w(CLUT|(cols<<16))
    a.label('native_data');packed=compact_native(tables)
    packed+=b'\0'*((-len(packed))%4)
    for offset in range(0,len(packed),4):a.w(int.from_bytes(packed[offset:offset+4],'little'))
    code=a.finish()
    if len(code)>CAVE_END-CAVE_OFF:raise ValueError('Font lookup exceeds reclaimed mapping region')
    return code,a.labels


def patch_exe(exe,plan):
    if hashlib.sha256(exe).hexdigest()!=SOURCE_SHA:raise ValueError('Unexpected original EXE')
    tables=native_tables(exe);code,labels=lookup_code(len(plan['glyphs']),tables);out=bytearray(exe);out[CAVE_OFF:CAVE_OFF+len(code)]=code
    assert out[0x3e2d8:0x3e2e0]==struct.pack('<II',0,0x310700ff)
    struct.pack_into('<II',out,0x8004dad8-BASE,0x08000000|((labels['lookup']>>2)&0x3ffffff),0)
    assert out[0x8004d6dc-BASE:0x8004d6e4-BASE]==struct.pack('<II',0x27bdffd8,0xafb3001c)
    struct.pack_into('<II',out,0x8004d6dc-BASE,0x08000000|((labels['palette_proxy']>>2)&0x3ffffff),0)
    for address in (0x8007f580,0x8007f594,0x8007f5a8):struct.pack_into('<H',out,address-BASE,CLUT)
    # Native maps are now read by our compact lookup. Skip the old initializer
    # that expects unpacked arrays at these addresses; symbol/kana setup stays.
    assert struct.unpack_from('<I',exe,0x8005205c-BASE)[0]==0x1040000e
    struct.pack_into('<I',out,0x8005205c-BASE,0x1000000e)
    plan['native_map_counts']=list(map(len,tables));plan['native_map_compact_bytes']=len(compact_native(tables))
    plan['startup_bss_range_preserved']=['0x800833b0','0x8008b7a8']
    plan['lookup_code_bytes']=len(code);plan['lookup_labels']={k:hex(v) for k,v in labels.items()};plan['original_exe_sha256']=SOURCE_SHA
    return bytes(out)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--texts',type=Path,required=True);p.add_argument('--font',type=Path,required=True);p.add_argument('--output',type=Path,default=ROOT/'work/font/build');p.add_argument('--write',action='store_true');a=p.parse_args()
    rows=[json.loads(line) for line in a.texts.read_text().splitlines() if line.strip()];texts=[r.get('zh',r.get('zh_CN',r.get('ja',''))) for r in rows]
    plan=make_plan(texts)
    for text in texts:assert decode(encode(text,plan),plan)==text
    from getter_pac import parse,member_data
    pac=(ROOT/'work/source/unpacked_vfs/bin/setup.pac').read_bytes();records=parse(pac);sources={r['name']:member_data(pac,r) for r in records if r['name'] in SHEETS}
    assets,previews=build_sheets(plan,sources,a.font);exe=patch_exe((ROOT/'work/source/disc.provisional/SLPS_022.32').read_bytes(),plan)
    plan['font_sha256']=hashlib.sha256(a.font.read_bytes()).hexdigest();plan['input_texts']=len(texts);plan['encoding_roundtrip_passed']=True
    print(json.dumps({k:v for k,v in plan.items() if k!='glyphs'},ensure_ascii=False,indent=2))
    if a.write:
        a.output.mkdir(parents=True,exist_ok=True)
        for name,data in assets.items():(a.output/name).write_bytes(data)
        (a.output/'SLPS_022.32.font-only').write_bytes(exe);(a.output/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2))
        im=Image.new('RGB',(16*52,((len(previews)+15)//16)*40),(22,25,38));dr=ImageDraw.Draw(im)
        for i,(ch,cell) in enumerate(previews):
            x=(i%16)*52;y=(i//16)*40;im.paste(Image.fromarray(cell*255).resize((36,36),Image.Resampling.NEAREST).convert('RGB'),(x,y));dr.text((x+36,y+12),str(i),fill=(140,200,255))
        im.save(a.output/'glyph_preview.png')

if __name__=='__main__':main()
