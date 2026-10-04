"""Offline label coverage audit. No provider/network calls and no file writes."""
import ast
import json
import re
from knowledge import ROOT

def labels():
    result=set();string=r"'(?:\\.|[^'\\])*'"
    for name in ('app.js','accounts.js'):
        for match in re.finditer(r'(?:tr|title)\(('+string+r'),\s*('+string+r')(?:,|\))',(ROOT/'app'/name).read_text('utf-8')):
            try:result.add(ast.literal_eval(match[2]))
            except (ValueError,SyntaxError):pass
    for match in re.finditer(r'else ('+string+r')',(ROOT/'scripts/assistant_engine.py').read_text('utf-8')):
        value=ast.literal_eval(match[1])
        if len(value)>25 and value.isascii():result.add(value)
    existing=set()
    for match in re.finditer(r'\[('+string+'),',(ROOT/'app/i18n.js').read_text('utf-8')):
        try:existing.add(ast.literal_eval(match[1]))
        except (ValueError,SyntaxError):pass
    existing.update(row[0] for row in json.loads((ROOT/'app/locales.json').read_text('utf-8')))
    return sorted(result-existing)

if __name__=='__main__':
    missing=labels()
    print(json.dumps({'missing_labels':missing},ensure_ascii=True))
    raise SystemExit(bool(missing))
