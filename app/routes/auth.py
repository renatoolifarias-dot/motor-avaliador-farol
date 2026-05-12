"""Login / logout routes (placeholder — implementação completa em sprint 2)."""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/login", response_class=HTMLResponse)
async def login_get(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/login")
async def login_post(request: Request):
    # TODO: validar credenciais, criar sessão
    return {"detail": "TODO"}


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return {"detail": "Deslogado"}
