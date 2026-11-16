"""Derive stairs/slab names from matching RTF block names for this exact mod version."""
from pathlib import Path
import json,zipfile
root=Path(__file__).resolve().parent
mods=root.parent.parent/'voltage/Voltage/client-forge-1.20.1/mods'
jar=next(mods.glob('rechiseled*.jar'))
with zipfile.ZipFile(jar) as z:
    en=json.loads(z.read('assets/rechiseled/lang/en_us.json').decode('utf-8-sig'))
base=json.loads((root/'rtf-selected/rechiseled.json').read_text(encoding='utf-8'))
out={}
for key,eng in en.items():
    if not key.startswith('block.rechiseled.'):continue
    plain=key[:-11] if key.endswith('_connecting') else key
    for suffix,english_suffix,label in (('_stairs',' Stairs','Ступени: '),('_slab',' Slab','Плита: ')):
        if not plain.endswith(suffix):continue
        stem=plain[:-len(suffix)].replace('block.rechiseled.','rechiseled.block.',1)
        other=stem+'_connecting' if key.endswith('_connecting') and stem+'_connecting' in base else stem
        if other in base and other in en and eng==en[other]+english_suffix:
            out[key]=label+base[other]
manual={
    'rechiseled.item_group':'Rechiseled',
    'rechiseled.chiseling.chisel_all.shift':'%s для всех форм',
    'rechiseled.chiseling.chisel_all.items':'Предметов: %s',
    'rechiseled.chiseling.select_shape':'Форма: %s',
    'rechiseled.chiseling.filter':'Настройки фильтра',
    'rechiseled.chiseling.filter.clear':'Нажмите правой кнопкой, чтобы очистить',
    'rechiseled.chiseling.filter.show_blocks':'показывать блоки',
    'rechiseled.chiseling.filter.show_stairs':'показывать ступени',
    'rechiseled.chiseling.filter.show_slabs':'показывать плиты',
    'rechiseled.chiseling.filter.show_non_connecting':'показывать несоединяемые',
    'rechiseled.chiseling.scrollbar':'Полоса прокрутки',
    'rechiseled.chiseling.entry.recipe':'Рецепт: %s',
    'rechiseled.chiseling.entry.owner':'Модуль: %s',
    'rechiseled.recipe_category.title':'Резьба по блокам',
    'rechiseled.recipe_category.conversion_value':'Коэффициент преобразования: %s',
    'rechiseled.chiseling.shape.block':'Блок',
    'rechiseled.chiseling.shape.stairs':'Ступени',
    'rechiseled.chiseling.shape.slab':'Плита',
}
assert len(out)==2418 and all(key in en for key in manual)
assert all(en[k].count('%s')==v.count('%s') for k,v in manual.items())
out.update(manual)
folder=root/'rtf-derived';folder.mkdir(exist_ok=False)
(folder/'rechiseled.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(folder/'NOTICE_DERIVED.txt').write_text(
    'Derived Russian stair and slab names for Rechiseled from selected RTF Extension translations.\n'
    'Original RTF Extension contributors: https://github.com/Kamas50/RTF_Extension\n'
    'This modified selection is offered under GNU AGPL version 3; see LICENSE_RTF.txt.\n'
    'Source and generator: https://github.com/Manyun007/voltage-updates/tree/main/source/rtf-20\n',encoding='utf-8')
print('Generated',len(out),'compatible Russian Rechiseled entries')
