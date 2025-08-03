from datetime import datetime, timedelta
from urllib.parse import urlencode

import requests
import pkce
from flask import Blueprint, current_app, redirect, request, session, url_for
from flask_login import current_user, login_required

from models import TeslaToken, db

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/oauth/start")
@login_required
def oauth_start():
    verifier, challenge = pkce.generate_pkce_pair()
    session["code_verifier"] = verifier
    params = {
        "client_id": current_app.config["TESLA_CLIENT_ID"],
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "redirect_uri": current_app.config["TESLA_REDIRECT_URI"],
        "response_type": "code",
        "scope": "openid email offline_access",
    }
    url = "https://auth.tesla.com/oauth2/v3/authorize?" + urlencode(params)
    return redirect(url)


@auth_bp.route("/oauth/callback")
@login_required
def oauth_callback():
    code = request.args.get("code")
    verifier = session.pop("code_verifier", None)
    if not code or not verifier:
        return redirect(url_for("index"))
    payload = {
        "grant_type": "authorization_code",
        "client_id": current_app.config["TESLA_CLIENT_ID"],
        "code": code,
        "code_verifier": verifier,
        "redirect_uri": current_app.config["TESLA_REDIRECT_URI"],
    }
    headers = {"User-Agent": current_app.config["TESLA_USER_AGENT"]}
    resp = requests.post(
        "https://auth.tesla.com/oauth2/v3/token", json=payload, headers=headers, timeout=10
    )
    data = resp.json()
    expires = datetime.utcnow() + timedelta(seconds=data.get("expires_in", 0))
    token = TeslaToken.query.filter_by(user_id=current_user.id, vehicle_id=None).first()
    if token is None:
        token = TeslaToken(user_id=current_user.id)
        db.session.add(token)
    token.access_token = data.get("access_token", "")
    token.refresh_token = data.get("refresh_token", "")
    token.expires_at = expires
    db.session.commit()

    # optional: fetch first vehicle id
    try:
        veh_resp = requests.get(
            "https://owner-api.teslamotors.com/api/1/vehicles",
            headers={
                "Authorization": f"Bearer {token.access_token}",
                "User-Agent": current_app.config["TESLA_USER_AGENT"],
            },
            timeout=10,
        )
        vehicles = veh_resp.json().get("response")
        if vehicles:
            token.vehicle_id = str(vehicles[0].get("id"))
            db.session.commit()
    except Exception:
        pass

    return redirect(url_for("index"))


@auth_bp.route("/oauth/revoke")
@login_required
def oauth_revoke():
    token = TeslaToken.query.filter_by(user_id=current_user.id).first()
    if token is not None:
        db.session.delete(token)
        db.session.commit()
    return redirect(url_for("index"))
