from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()


class DevChatIn(BaseModel):
    phone: str
    text: str


@router.post("/dev/chat")
def dev_chat(body: DevChatIn, request: Request) -> dict:
    reply = request.app.state.engine.handle_message(body.phone, body.text)
    return {"reply": reply}
