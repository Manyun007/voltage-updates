"""Select compatible missing keys from RTF Extension; retain source and AGPL notice."""
from pathlib import Path
import json,re,shutil,zipfile
root=Path(__file__).resolve().parent
mods=root.parent.parent/'voltage/Voltage/client-forge-1.20.1/mods'
installed=root.parent.parent/'voltage/Voltage/client-forge-1.20.1/resourcepacks/voltage-client-compat.zip'
out=root/'rtf-selected';out.mkdir(exist_ok=False)
current={}
with zipfile.ZipFile(installed) as z:
    for n in z.namelist():
        if n.startswith('assets/') and n.endswith('/lang/ru_ru.json'):
            current[n.split('/')[1]]=json.loads(z.read(n).decode('utf-8'))
english={};russian={}
for jar in mods.glob('*.jar'):
    with zipfile.ZipFile(jar) as z:
        for name in z.namelist():
            if not name.startswith('assets/') or not name.endswith('/lang/en_us.json'):continue
            namespace=name.split('/')[1]
            try:
                english.setdefault(namespace,{}).update(json.loads(z.read(name).decode('utf-8-sig')))
                localized=name.replace('/en_us.json','/ru_ru.json')
                if localized in z.namelist():russian.setdefault(namespace,{}).update(json.loads(z.read(localized).decode('utf-8-sig')))
            except (ValueError,UnicodeError):continue
pattern=re.compile(r'%(?:(\d+)\$)?([a-zA-Z%])')
def placeholders(s):return sorted((i or '',t) for i,t in pattern.findall(s) if t!='%')
counts={}
with zipfile.ZipFile(root/'rtf-extension-source.zip') as z:
    for name in z.namelist():
        if not name.startswith('assets/') or not name.endswith('/lang/ru_ru.json'):continue
        namespace=name.split('/')[1]
        if namespace not in english:continue
        try:source=json.loads(z.read(name).decode('utf-8-sig'))
        except (ValueError,UnicodeError):continue
        en=english[namespace];known=set(russian.get(namespace,{}))|set(current.get(namespace,{}))
        selected={k:v for k,v in source.items() if k in en and k not in known and isinstance(v,str)
                  and isinstance(en[k],str) and v!=en[k] and placeholders(v)==placeholders(en[k])}
        if selected:
            (out/(namespace+'.json')).write_text(json.dumps(selected,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            counts[namespace]=len(selected)
shutil.copy2(root/'LICENSE_AGPL3.txt',out/'LICENSE_RTF.txt')
shutil.copy2(root/'rtf-readme.txt',out/'README_RTF.txt')
(out/'NOTICE_RTF.txt').write_text(
    'RTF Extension translations by Kamas50 and project contributors.\n'
    'Modified for VOLTAGE: selected missing language keys and checked formatting placeholders.\n'
    'License: GNU AGPL version 3 only; see LICENSE_RTF.txt.\n'
    'Original project and source: https://github.com/Kamas50/RTF_Extension\n'
    'Original release: https://modrinth.com/resourcepack/rtf-extension/version/Jc3ynK1l\n'
    'These modified JSON source files and the launcher source are distributed in the signed VOLTAGE release at '
    'https://github.com/Manyun007/voltage-updates/tree/main/releases/19\n',encoding='utf-8')
print('Selected',sum(counts.values()),'translations in',len(counts),'namespaces:',counts)
