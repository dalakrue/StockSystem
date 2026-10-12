from __future__ import annotations
import ast, json, re, sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

EXACT_KEYS = {
    'symbol','selected_symbol','canonical_display_symbol_20260709','multi_symbol_selected_20260701',
    'multi_symbol_main_symbol_20260702','connector_symbol_20260702','calculation_symbol_20260702',
    'connector_symbol','calculation_symbol','settings_main_symbol','settings_main_symbol_20260702',
}
FIELD_KEY = re.compile(r'(?i)(?:field\d+|research|finder|dinner|morning|ai(?:_assistant)?).{0,40}symbol|symbol.{0,40}(?:field\d+|research|finder|dinner|morning|ai(?:_assistant)?)')
WIDGETS={'selectbox','multiselect','radio','segmented_control','select_slider','pills'}
EXCLUDE_PARTS={'.git','__pycache__','.pytest_cache','.venv','venv','tests','test_artifacts','delivery','backups','backup'}

def lit(node: ast.AST | None):
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value,str) else None

def state_base(node: ast.AST) -> bool:
    if isinstance(node, ast.Name): return node.id in {'state','session_state','ss'}
    if isinstance(node, ast.Attribute):
        return node.attr == 'session_state' or (isinstance(node.value, ast.Name) and node.value.id=='state')
    return False

def module_roles(rel: str, text: str) -> list[str]:
    low=(rel+'\n'+text).lower(); roles=[]
    tests={
      'configure_universe':['configure_universe','configured_symbols','multi_symbol_settings','settings'],
      'load_data':['publish_loaded_universe','load_manager','load_symbols','loaded_symbols','provider_symbol'],
      'calculate':['calculation_symbol','calculate','run_calculation','field3','institutional_quant'],
      'publish':['publish_completed','publication_status','canonical_runs','persist_field'],
      'display_evidence':['active_display','display_symbol','render_selector','filter_frame_for_symbol'],
      'connector_identity':['connector_symbol','connection.py','connector'],
      'export':['to_csv','to_excel','powerbi','export'],
      'ai_research':['ai_assistant','research'],
    }
    for role, needles in tests.items():
        if any(n in low for n in needles): roles.append(role)
    return roles

def scan(root: Path) -> dict[str,Any]:
    occurrences=[]; widgets=[]; parse_errors=[]; roles={}
    for p in sorted(root.rglob('*.py')):
        if any(part in EXCLUDE_PARTS for part in p.parts): continue
        rel=p.relative_to(root).as_posix()
        first=Path(rel).parts[0] if Path(rel).parts else ''
        if '/' in rel and first not in {'core','ui','tabs'}:
            continue
        try: text=p.read_text(encoding='utf-8',errors='ignore'); tree=ast.parse(text,filename=rel)
        except Exception as exc:
            parse_errors.append({'file':rel,'error':f'{type(exc).__name__}: {exc}'})
            continue
        roles[rel]=module_roles(rel,text)
        for node in ast.walk(tree):
            if isinstance(node,ast.Subscript) and state_base(node.value):
                key=lit(node.slice)
                if key and (key in EXACT_KEYS or FIELD_KEY.search(key)):
                    op='write' if isinstance(node.ctx,ast.Store) else 'delete' if isinstance(node.ctx,ast.Del) else 'read'
                    occurrences.append({'file':rel,'line':node.lineno,'key':key,'operation':op,'syntax':'subscript'})
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute):
                base=node.func.value; name=node.func.attr
                if state_base(base) and name in {'get','setdefault','pop'} and node.args:
                    key=lit(node.args[0])
                    if key and (key in EXACT_KEYS or FIELD_KEY.search(key)):
                        op='read' if name=='get' else 'write' if name=='setdefault' else 'delete'
                        occurrences.append({'file':rel,'line':node.lineno,'key':key,'operation':op,'syntax':name})
                if name=='update' and state_base(base) and node.args and isinstance(node.args[0],ast.Dict):
                    for kn in node.args[0].keys:
                        key=lit(kn)
                        if key and (key in EXACT_KEYS or FIELD_KEY.search(key)):
                            occurrences.append({'file':rel,'line':node.lineno,'key':key,'operation':'write','syntax':'update'})
                if name in WIDGETS:
                    label=lit(node.args[0]) if node.args else None
                    key=None
                    for kw in node.keywords:
                        if kw.arg=='key': key=lit(kw.value) or ast.unparse(kw.value)
                    if key or (label and 'symbol' in label.lower()):
                        widgets.append({'file':rel,'line':node.lineno,'widget':name,'label':label,'key':key})
    # dedupe exact AST overlaps
    seen=set(); uniq=[]
    for x in occurrences:
        sig=tuple(x[k] for k in ('file','line','key','operation','syntax'))
        if sig not in seen: seen.add(sig); uniq.append(x)
    key_counts=Counter((x['key'],x['operation']) for x in uniq)
    writers=defaultdict(list)
    for x in uniq:
        if x['operation'] in {'write','delete'}: writers[x['key']].append({'file':x['file'],'line':x['line'],'operation':x['operation']})
    return {
      'root':str(root),'python_files_scanned':sum(1 for _ in root.rglob('*.py')),
      'exact_keys':sorted(EXACT_KEYS),'occurrences':uniq,'selector_widgets':widgets,
      'key_operation_counts':[{'key':k,'operation':op,'count':n} for (k,op),n in sorted(key_counts.items())],
      'writers_by_key':dict(sorted(writers.items())),'module_roles':{k:v for k,v in roles.items() if v},
      'symbol_selector_widgets':[w for w in widgets if 'symbol' in str(w.get('label') or '').lower() or 'symbol' in str(w.get('key') or '').lower()],
      'parse_errors':parse_errors,
    }

def main():
    if len(sys.argv)<4: raise SystemExit('usage: script BEFORE_ROOT AFTER_ROOT OUTPUT')
    before=scan(Path(sys.argv[1])); after=scan(Path(sys.argv[2]))
    report={'report_version':2,'scope':'runtime Python source; exact generic keys plus field/surface-specific symbol keys and selector widgets',
            'before':before,'after':after,
            'summary':{
              'before_occurrences':len(before['occurrences']),'after_occurrences':len(after['occurrences']),
              'before_symbol_writes':sum(1 for x in before['occurrences'] if x['operation'] in {'write','delete'}),
              'after_symbol_writes':sum(1 for x in after['occurrences'] if x['operation'] in {'write','delete'}),
              'before_selector_widgets':len(before['selector_widgets']),'after_selector_widgets':len(after['selector_widgets']),
              'before_symbol_selector_widgets':len(before['symbol_selector_widgets']),'after_symbol_selector_widgets':len(after['symbol_selector_widgets']),
            }}
    Path(sys.argv[3]).write_text(json.dumps(report,indent=2,ensure_ascii=False,default=str),encoding='utf-8')
    print(json.dumps(report['summary'],indent=2))
if __name__=='__main__': main()
