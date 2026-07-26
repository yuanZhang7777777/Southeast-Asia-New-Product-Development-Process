from fastapi import APIRouter, HTTPException, Response

from app.oss_storage import read_oss_object_by_public_url

router = APIRouter(prefix="/media", tags=["media"])


THUMB_PROCESS = "image/resize,w_400"


@router.get("/oss-image")
def oss_image(src: str, thumb: bool = False) -> Response:
    """公开只读代理私有 OSS 桶内的商品图。

    不加鉴权：商品图低敏，且 read_oss_object_by_public_url 做 host 白名单校验；
    此处仅放行 product-images/ 前缀（认领证据图走 claims 的带鉴权代理）。
    thumb=true 时由 OSS 出 400px 宽缩略图（列表场景省 ~90% 流量）。
    """
    try:
        data, content_type = read_oss_object_by_public_url(
            src, allowed_prefixes=("product-images/",), process=THUMB_PROCESS if thumb else None
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="failed to read OSS image") from exc
    return Response(content=data, media_type=content_type, headers={"Cache-Control": "public, max-age=604800"})
