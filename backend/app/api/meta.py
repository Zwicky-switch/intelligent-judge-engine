"""引擎信息(任意登录角色可读): 用于页面"技术铭牌"与引擎导览页的实时口径."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.config import settings
from app.constants import MODEL_VERSION
from app.core.deps import CurrentUser, get_current_user
from app.llm.base import normalize_provider

router = APIRouter(prefix="/meta", tags=["引擎信息"])


@router.get("")
def engine_meta(cur: CurrentUser = Depends(get_current_user)):
    prov = normalize_provider()
    has_key = bool((settings.GRADE_LLM_API_KEY or "").strip())
    online = prov != "builtin" and has_key
    # 评阅引擎铭牌: 始终以产品化措辞呈现(不出现 mock/演示字眼)。
    if online:
        label = {
            "deepseek": "DeepSeek", "qwen": "通义千问", "zhipu": "智谱 GLM",
            "openai": "OpenAI 兼容接口", "openai_compat": "OpenAI 兼容接口",
        }.get(prov, prov)
        note = (f"评阅复核层由 {label} 驱动; 给分始终以题目量规为准, "
                "外部模型仅复核判点并生成评语, 不绕过量规。")
    else:
        note = ("当前评阅由内置确定性引擎本地完成(未配置外部模型 Key); "
                "接入外部模型后, 其复核与评语层将自动启用, 给分仍以题目量规为准。")
    return {
        "model_version": MODEL_VERSION,
        "llm_provider": prov,
        "llm_model": (settings.GRADE_LLM_MODEL or "").strip(),
        "has_api_key": has_key,
        "review_threshold": settings.REVIEW_THRESHOLD,
        "auto_release_objective": settings.AUTO_RELEASE_OBJECTIVE,
        "note": note,
    }
