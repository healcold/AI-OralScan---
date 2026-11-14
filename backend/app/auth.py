from datetime import timedelta
from hashlib import scrypt, sha256
from hmac import compare_digest
import re
from secrets import token_urlsafe
from threading import Lock
from time import monotonic
from typing import Annotated, Literal
from unicodedata import normalize
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .database import get_db, lock_scan_write
from .models import Account, AccountRecovery, LoginSession, ScanSession, now

COOKIE = 'oralscan_session'
SESSION_SECONDS = 8 * 60 * 60
router = APIRouter(prefix='/api/auth')
Db = Annotated[Session, Depends(get_db)]
_lock = Lock()
_attempts: dict[tuple[str, str], tuple[float, int]] = {}
_phone = re.compile(r'1[3-9][0-9]{9}')


def password_digest(password: str, salt: str) -> str:
    return scrypt(password.encode(), salt=salt.encode(), n=2**15, r=8, p=3, maxmem=64*1024*1024).hex()


RecoveryQuestion = Literal['father', 'mother', 'teacher', 'custom']


def create_account(db: Session, username: str, password: str, role: Literal['patient', 'admin'] = 'patient', *,
                   recovery: tuple[str, str] | None = None) -> Account:
    salt = token_urlsafe(24)
    account = Account(username=username.strip().lower(), password_salt=salt,
                      password_hash=password_digest(password, salt), role=role)
    answer_salt = token_urlsafe(24)
    answer_hash = password_digest(recovery[1], answer_salt) if recovery else None
    db.add(account)
    if recovery and answer_hash:
        db.flush()
        db.add(AccountRecovery(account_id=account.account_id, question=recovery[0],
                               answer_hash=answer_hash, answer_salt=answer_salt))
    db.commit()
    return account


def current_account(request: Request, db: Db) -> Account:
    token = request.cookies.get(COOKIE)
    if token and len(token) <= 128:
        session = db.get(LoginSession, sha256(token.encode()).hexdigest())
        if session and session.expires_at > int(now().timestamp()):
            account = db.get(Account, session.account_id)
            if account:
                return account
    raise HTTPException(401, '请先登录。')


CurrentAccount = Annotated[Account, Depends(current_account)]


def require_admin(account: CurrentAccount):
    if account.role != 'admin':
        raise HTTPException(403, '此操作仅工作台管理员可用。')


def own_scan(db: Session, account: Account, scan_id: UUID | str) -> ScanSession | None:
    return db.scalar(select(ScanSession).where(
        ScanSession.scan_id == str(scan_id), ScanSession.owner_id == account.account_id))


def require_owned_scan(scan_id: UUID, db: Db, account: CurrentAccount):
    if own_scan(db, account, scan_id) is None:
        raise HTTPException(404, '检查记录不存在。')


def same_origin_write(request: Request):
    # The frontend and API are served from the same public origin, including behind a proxy.
    origin = request.headers.get('origin')
    if request.headers.get('sec-fetch-site') in {'cross-site', 'same-site'} or (
        origin is not None and (
            urlsplit(origin).scheme not in {'http', 'https'}
            or urlsplit(origin).netloc.lower() != request.headers.get('host', '').lower()
        )
    ):
        raise HTTPException(403, '请从本站页面操作。')


class Credentials(BaseModel):
    model_config = ConfigDict(extra='forbid')
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128, repr=False)


def account_out(account: Account):
    return {'username': account.username, 'role': account.role}


class RecoveryRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    phone: str = Field(max_length=32)
    password: str = Field(max_length=128, repr=False)
    question: RecoveryQuestion
    custom_prompt: str = Field(default='', max_length=60, repr=False)
    answer: str = Field(repr=False)


def limit_attempts(request: Request, action: str, maximum: int, window_seconds: int, *, subject: str | None = None):
    peer = request.client.host if request.client else 'unknown'
    key = (action, subject if subject is not None else peer)
    instant = monotonic()
    with _lock:
        for expired, (until, _) in list(_attempts.items()):
            if until <= instant:
                del _attempts[expired]
        until, count = _attempts.get(key, (instant + window_seconds, 0))
        if count >= maximum or (key not in _attempts and len(_attempts) >= 4096):
            raise HTTPException(429, '尝试次数较多，请稍后再试。')
        _attempts[key] = (until, count + 1)


def recovery_fields(body: RecoveryRequest) -> tuple[str, str, str]:
    phone = body.phone.strip()
    if not _phone.fullmatch(phone):
        raise HTTPException(422, '请输入有效的中国大陆 11 位手机号。')
    if len(body.password) < 6 or not body.password.strip():
        raise HTTPException(422, '密码至少 6 个字符，且不能全部为空白。')
    answer = body.answer.strip()
    if not answer:
        raise HTTPException(422, '请填写找回答案。')
    if answer == body.password.strip() or phone in answer:
        raise HTTPException(422, '找回答案不能和密码相同，也不要包含手机号。')
    question = body.question
    prompt = normalize('NFC', body.custom_prompt.strip())
    if question == 'custom':
        if not prompt or prompt == normalize('NFC', answer) or phone in prompt:
            raise HTTPException(422, '请输入自定义提示，请勿在提示里填写答案或手机号。')
        question_key = 'custom:' + sha256(prompt.encode()).hexdigest()
    else:
        question_key = question
    return phone, answer, question_key


@router.post('/register', status_code=201, dependencies=[Depends(same_origin_write)])
def register(body: RecoveryRequest, request: Request, db: Db):
    phone, answer, question_key = recovery_fields(body)
    limit_attempts(request, 'register', 10, 60)
    if db.scalar(select(Account.account_id).where(Account.username == phone)):
        raise HTTPException(409, '该手机号已注册，请返回登录。')
    try:
        account = create_account(db, phone, body.password, recovery=(question_key, answer))
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, '该手机号已注册，请返回登录。') from None
    return account_out(account)


@router.post('/reset-password', status_code=204, dependencies=[Depends(same_origin_write)])
def reset_password(body: RecoveryRequest, request: Request, db: Db):
    phone, answer, question_key = recovery_fields(body)
    limit_attempts(request, 'recovery-peer', 15, 15 * 60)
    limit_attempts(request, 'recovery-account', 5, 15 * 60, subject=sha256(phone.encode()).hexdigest())
    record = db.execute(
        select(Account.account_id, AccountRecovery.question, AccountRecovery.answer_salt, AccountRecovery.answer_hash)
        .join(AccountRecovery).where(Account.username == phone, Account.role == 'patient')
    ).one_or_none()
    db.rollback()
    digest = password_digest(answer, record.answer_salt if record else 'oralscan-unknown-recovery')
    if not compare_digest(digest, record.answer_hash if record else '0' * 128) or not record or record.question != question_key:
        raise HTTPException(401, '无法核对找回信息。请检查手机号、提示和答案；若未设置过找回答案，请联系项目管理员。')

    salt = token_urlsafe(24)
    new_hash = password_digest(body.password, salt)
    lock_scan_write(db)
    changed = db.execute(update(Account).where(Account.account_id == record.account_id, Account.role == 'patient')
                         .values(password_hash=new_hash, password_salt=salt))
    if not changed.rowcount:
        raise HTTPException(401, '无法核对找回信息。')
    db.execute(delete(LoginSession).where(LoginSession.account_id == record.account_id))
    db.commit()
    return Response(status_code=204)


@router.post('/login', dependencies=[Depends(same_origin_write)])
def login(body: Credentials, request: Request, response: Response, db: Db,
          settings: Annotated[Settings, Depends(get_settings)]):
    limit_attempts(request, 'login', 20, 60)
    account = db.scalar(select(Account).where(Account.username == body.username.strip().lower()))
    account_id = account.account_id if account else None
    salt = account.password_salt if account else 'unknown-account'
    expected = account.password_hash if account else '0' * 128
    db.rollback()
    digest = password_digest(body.password, salt)
    if not compare_digest(digest, expected) or account_id is None:
        raise HTTPException(401, '账号或密码不正确。')

    # Serialize session creation with password reset and reject stale credentials.
    lock_scan_write(db)
    account = db.scalar(select(Account).where(Account.account_id == account_id, Account.password_hash == expected)
                        .with_for_update())
    if account is None:
        raise HTTPException(401, '账号或密码不正确。')
    old = request.cookies.get(COOKIE)
    if old and len(old) <= 128:
        db.execute(delete(LoginSession).where(LoginSession.token_hash == sha256(old.encode()).hexdigest()))
    timestamp = now()
    db.execute(delete(LoginSession).where(LoginSession.expires_at <= int(timestamp.timestamp())))
    token = token_urlsafe(32)
    db.add(LoginSession(token_hash=sha256(token.encode()).hexdigest(), account_id=account.account_id,
                        expires_at=int((timestamp + timedelta(seconds=SESSION_SECONDS)).timestamp())))
    db.commit()
    response.set_cookie(COOKIE, token, max_age=SESSION_SECONDS, httponly=True,
                        samesite='strict', secure=settings.secure_session_cookie or request.url.scheme == 'https')
    return account_out(account)


@router.get('/me')
def me(account: CurrentAccount):
    return account_out(account)


@router.post('/logout', dependencies=[Depends(same_origin_write)], status_code=204)
def logout(request: Request, db: Db):
    token = request.cookies.get(COOKIE)
    if token and len(token) <= 128:
        db.execute(delete(LoginSession).where(LoginSession.token_hash == sha256(token.encode()).hexdigest()))
        db.commit()
    response = Response(status_code=204)
    response.delete_cookie(COOKIE, httponly=True, samesite='strict')
    return response
