"""数据修复: 把 answers.content_uri 中指向旧项目路径(media-radar-app)的记录改指当前 UPLOAD_DIR.

文件已在当前目录(旧目录被整体移动/改名), 仅 DB 字符串过时; 幂等可重复执行。
"""
import sys
sys.path.insert(0, ".")
from pathlib import Path

from app.config import settings
from app.db import SessionLocal
from app.models import Answer

base = Path(settings.UPLOAD_DIR).resolve()
old_marker = "media-radar-app"   # 旧项目目录名
fixed, missing = 0, []

db = SessionLocal()
try:
    rows = db.query(Answer).filter(Answer.content_uri != "").all()
    for a in rows:
        uri = (a.content_uri or "").strip()
        if not uri:
            continue
        p = Path(uri).resolve()
        if p.is_relative_to(base):
            continue   # 已指向当前目录
        name = p.name
        new_path = base / name
        if new_path.is_file():
            a.content_uri = str(new_path)
            fixed += 1
        else:
            missing.append((a.id, uri))
    db.commit()
finally:
    db.close()

print(f"修复 content_uri: {fixed} 条")
print(f"仍缺失(文件不存在): {len(missing)} 条")
for aid, uri in missing[:10]:
    print("  ", aid, uri)
