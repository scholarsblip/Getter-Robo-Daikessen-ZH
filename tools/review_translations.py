#!/usr/bin/env python3
"""Apply exact reviewed terms and remove machine-generated spacing artefacts.

Original extracted text and original machine output remain unchanged.
"""
import argparse,hashlib,json,re,unicodedata
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def normalize(text):
    text=''.join(c for c in text if unicodedata.category(c)!='Cf')
    # Keep meaningful spaces inside Latin words and identifiers; CJK text does
    # not need the spaces introduced around translation entity markers.
    text=re.sub(r'(?<![A-Za-z0-9]) +| +(?![A-Za-z0-9])','',text)
    return text

def main():
    p=argparse.ArgumentParser();p.add_argument('input',type=Path);p.add_argument('output',type=Path);p.add_argument('--overrides',type=Path,nargs='*',default=[]);a=p.parse_args()
    if a.input.resolve()==a.output.resolve():raise ValueError('Original MT must not be overwritten')
    maps={}
    for path in a.overrides:maps.update(json.loads(path.read_text()))
    rows=[];changed=[]
    for line in a.input.read_text().splitlines():
        if not line.strip():continue
        r=json.loads(line);old=r['zh_CN'];new=maps.get(r['id'],maps.get(r['ja'],normalize(old)))
        r['zh_CN']=new
        if old!=new:
            r['review']={'method':'manual row review' if r['id'] in maps else 'exact terminology/UI override' if r['ja'] in maps else 'MT spacing normalization','previous_target_sha256':hashlib.sha256(old.encode()).hexdigest()};changed.append(r['id'])
        rows.append(r)
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
    print(json.dumps({'rows':len(rows),'changed':len(changed),'output':str(a.output)}))
if __name__=='__main__':main()
