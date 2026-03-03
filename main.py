from fastapi import FastAPI, HTTPException, Depends, Header
from pydantic import BaseModel
from typing import List, Any, Dict
import httpx
import json
import os

VV_MCP = "https://mcp001.vkusvill.ru/mcp"
API_KEY = os.getenv("VV_API_KEY")  # задаётся в Render

app = FastAPI(title="VkusVill Cart Link API", version="1.0.0")


class CartItem(BaseModel):
    xml_id: int
    quantity: float = 1


class CartRequest(BaseModel):
    items: List[CartItem]


def require_api_key(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="x-api-key"),
):
    if not API_KEY:
        raise HTTPException(status_code=500, detail="Server API key is not configured (VV_API_KEY)")

    token = None

    # 1) Принимаем Bearer токен (то, что GPT умеет стабильно отправлять)
    if authorization:
        low = authorization.lower()
        if low.startswith("bearer "):
            token = authorization[7:].strip()

    # 2) Оставляем поддержку x-api-key (на всякий)
    if not token and x_api_key:
        token = x_api_key

    if token != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


async def mcp_init(client: httpx.AsyncClient) -> str:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }

    init_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "vv-gpt-backend", "version": "1.0"},
        },
    }

    r = await client.post(VV_MCP, json=init_payload, headers=headers)
    sid = r.headers.get("mcp-session-id") or r.headers.get("Mcp-Session-Id")
    if not sid:
        raise RuntimeError("VkusVill MCP did not return mcp-session-id header")

    headers["Mcp-Session-Id"] = sid
    await client.post(
        VV_MCP,
        json={"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        headers=headers,
    )
    return sid


def _extract_text_json(mcp_result: Any) -> Any:
    if isinstance(mcp_result, dict) and isinstance(mcp_result.get("content"), list) and mcp_result["content"]:
        first = mcp_result["content"][0]
        if isinstance(first, dict) and first.get("type") == "text" and isinstance(first.get("text"), str):
            txt = first["text"]
            try:
                return json.loads(txt)
            except Exception:
                return {"text": txt, "raw": mcp_result}
    return mcp_result


async def mcp_tool_call(tool_name: str, arguments: Dict[str, Any]) -> Any:
    async with httpx.AsyncClient(timeout=30) as client:
        sid = await mcp_init(client)
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Mcp-Session-Id": sid,
        }
        payload = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }
        r = await client.post(VV_MCP, json=payload, headers=headers)
        data = r.json()
        if "error" in data:
            raise RuntimeError(str(data["error"]))
        return data.get("result", data)


@app.get("/vv/search")
async def vv_search(q: str, page: int = 1, sort: str = "popularity", _: None = Depends(require_api_key)):
    try:
        res = await mcp_tool_call("vkusvill_products_search", {"q": q, "page": page, "sort": sort})
        return _extract_text_json(res)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/vv/cart-link")
async def vv_cart_link(req: CartRequest, _: None = Depends(require_api_key)):
    try:
        products = [{"xml_id": i.xml_id, "q": float(i.quantity)} for i in req.items]
        res = await mcp_tool_call("vkusvill_cart_link_create", {"products": products})
        parsed = _extract_text_json(res)
        if isinstance(parsed, dict) and "link" in parsed:
            return {"link": parsed["link"]}
        return parsed
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/")
def root():
    return {"status": "ok"}


@app.get("/healthcheck")
def healthcheck():
    return {"status": "ok"}
