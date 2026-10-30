"""Small deterministic overlay on the pinned upstream chart's common env helper."""
from pathlib import Path

ANCHOR = '- name: CONNECTOR_CORS_ORIGINS\n  value: {{ .Values.commonEnv.CONNECTOR_CORS_ORIGINS | quote }}\n'
EXTRA = '''{{- if .Values.cossSigning.enabled }}
- name: CONNECTOR_REQUIRE_SIGNING
  value: "true"
- name: CONNECTOR_SIGNING_ENABLED
  value: "true"
- name: CONNECTOR_SIGNING_ALGORITHM
  value: "RS256"
- name: CONNECTOR_SIGNING_ISSUER
  value: {{ required "Signing partnerId is required" .Values.cossSigning.partnerId | quote }}
- name: CONNECTOR_SIGNING_KEY_ID
  value: {{ required "Signing keyId is required" .Values.cossSigning.keyId | quote }}
- name: CONNECTOR_SIGNING_PRIVATE_KEY_PEM
  valueFrom:
    secretKeyRef:
      name: {{ required "Signing Secret is required" .Values.cossSigning.secret | quote }}
      key: private-key.pem
{{- end }}
{{- if .Values.cossQueue }}
- name: CONNECTOR_CELERY_QUEUE
  value: {{ .Values.cossQueue | quote }}
{{- end }}
{{- with .Values.adminAuth }}
- name: CONNECTOR_ADMIN_AUTH_ISSUER
  value: {{ required "adminAuth.issuer is required" .issuer | quote }}
- name: CONNECTOR_ADMIN_AUTH_JWKS_URL
  value: {{ required "adminAuth.jwksUrl is required" .jwksUrl | quote }}
- name: CONNECTOR_ADMIN_AUTH_CLIENT_ID
  value: {{ required "adminAuth.clientId is required" .clientId | quote }}
- name: CONNECTOR_ADMIN_AUTH_ROLE
  value: {{ required "adminAuth.role is required" .role | quote }}
- name: CONNECTOR_ADMIN_AUTH_UI_CLIENT_ID
  value: {{ required "adminAuth.uiClientId is required" .uiClientId | quote }}
{{- end }}
'''


def apply(chart):
    path = Path(chart) / "templates/_helpers.tpl"
    source = path.read_text(encoding="utf-8")
    if ANCHOR + EXTRA in source:
        return
    if source.count(ANCHOR) != 1 or "CONNECTOR_SIGNING_PRIVATE_KEY_PEM" in source:
        raise ValueError("Upstream connector env helper changed; review signing overlay")
    path.write_text(source.replace(ANCHOR, ANCHOR + EXTRA), encoding="utf-8", newline="\n")
