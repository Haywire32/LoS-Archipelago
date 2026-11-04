"""Immutable Lua seed sidecar; materialized before the next level starts."""
import json
import os
import tempfile
from pathlib import Path

def lua_value(value):
    if isinstance(value,str):return json.dumps(value,ensure_ascii=False)
    if value is True:return 'true'
    if value is False:return 'false'
    if value is None:return 'nil'
    if isinstance(value,int):return str(value)
    if isinstance(value,(list,tuple)):return '{'+','.join(map(lua_value,value))+'}'
    if isinstance(value,dict):return '{'+','.join('['+lua_value(k)+']='+lua_value(v) for k,v in sorted(value.items()))+'}'
    raise TypeError(type(value))

def write_active(root: Path, plan: dict):
    """Commit in one rename; loader sees either complete old or complete new plan."""
    target=root/'active.lua'
    text='return '+lua_value(plan)+'\n'
    if target.is_file() and target.read_text(encoding='utf-8')==text:return
    fd,name=tempfile.mkstemp(prefix='active-',suffix='.tmp',dir=root)
    try:
        with os.fdopen(fd,'w',encoding='utf-8',newline='\n') as stream:
            stream.write(text);stream.flush();os.fsync(stream.fileno())
        os.replace(name,target)
    finally:
        if os.path.exists(name):os.unlink(name)
