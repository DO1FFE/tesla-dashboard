import os
import base64
import hashlib
import secrets
from datetime import datetime, timedelta
from functools import wraps
from urllib.parse import urlencode

import requests
from flask import (
    Blueprint,
    abort,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_required

# Avoid circular import by importing the database instance
# from models instead of app.
from models import TeslaToken, db

auth_bp = Blueprint("auth", __name__)


def get_user_token():
    if not current_user.is_authenticated:
        return None
    token = TeslaToken.query.filter_by(user_id=current_user.id).first()
    if token and token.expires_at <= datetime.utcnow():
        data = {
            "grant_type": "refresh_token",
            "client_id": os.getenv("TESLA_CLIENT_ID", "ownerapi"),
            "refresh_token": token.refresh_token,
        }
        headers = {"User-Agent": os.getenv("TESLA_USER_AGENT", "Mozilla/5.0")}
        resp = requests.post(
            "https://auth.tesla.com/oauth2/v3/token",
            json=data,
            headers=headers,
        )
        if resp.ok:
            info = resp.json()
            token.access_token = info["access_token"]
            token.refresh_token = info["refresh_token"]
            token.expires_at = datetime.utcnow() + timedelta(
                seconds=info["expires_in"]
            )
            db.session.commit()
        else:
            db.session.delete(token)
            db.session.commit()
            return None
    return token


def tesla_token_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not get_user_token():
            return redirect(url_for("auth.oauth_start"))
        return func(*args, **kwargs)

    return wrapper


@auth_bp.route("/oauth/start")
@login_required
def oauth_start():
    """Start OAuth flow with Tesla SSO using Authorization Code + PKCE."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=")
    session["code_verifier"] = verifier.decode("utf-8")
    challenge = (
        base64.urlsafe_b64encode(
            hashlib.sha256(session["code_verifier"].encode("utf-8")).digest()
        )
        .rstrip(b"=")
        .decode("utf-8")
    )
    params = {
        "client_id": os.getenv("TESLA_CLIENT_ID", "ownerapi"),
        "scope": "openid email offline_access",
        "response_type": "code",
        "redirect_uri": url_for("auth.oauth_callback", _external=True),
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    auth_url = "https://auth.tesla.com/oauth2/v3/authorize"
    return redirect(f"{auth_url}?{urlencode(params)}")


@auth_bp.route("/oauth/callback")
@login_required
def oauth_callback():
    code = request.args.get("code")
    verifier = session.get("code_verifier")
    if not code or not verifier:
        abort(400)
    data = {
        "grant_type": "authorization_code",
        "client_id": os.getenv("TESLA_CLIENT_ID", "ownerapi"),
        "code": code,
        "redirect_uri": url_for("auth.oauth_callback", _external=True),
        "code_verifier": verifier,
    }
    headers = {"User-Agent": os.getenv("TESLA_USER_AGENT", "Mozilla/5.0")}
    resp = requests.post(
        "https://auth.tesla.com/oauth2/v3/token",
        data=data,
        headers=headers,
    )
    resp.raise_for_status()
    token_data = resp.json()
    expires_at = datetime.utcnow() + timedelta(token_data.get("expires_in", 0))
    token = TeslaToken(
        user_id=current_user.id,
        access_token=token_data["access_token"],
        refresh_token=token_data["refresh_token"],
        expires_at=expires_at,
    )
    db.session.add(token)
    db.session.commit()
    try:
        headers_api = {
            "Authorization": f"Bearer {token.access_token}",
            "User-Agent": os.getenv("TESLA_USER_AGENT", "Mozilla/5.0"),
        }
        veh_resp = requests.get(
            "https://owner-api.teslamotors.com/api/1/vehicles",
            headers=headers_api,
        )
        veh_resp.raise_for_status()
        vehicles = veh_resp.json().get("response", [])
        if vehicles:
            token.vehicle_id = vehicles[0].get("id_s")
            db.session.commit()
    except Exception:
        pass
    session.pop("code_verifier", None)
    return redirect(url_for("index", username_slug=current_user.username_slug))


@auth_bp.route("/oauth/revoke", methods=["POST"])
@login_required
def oauth_revoke():
    token = TeslaToken.query.filter_by(user_id=current_user.id).first()
    if token:
        db.session.delete(token)
        db.session.commit()
    return redirect(url_for("index", username_slug=current_user.username_slug))
