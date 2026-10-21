{{- define "dashboard.fullname" -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "dashboard.selectorLabels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "dashboard.labels" -}}
{{ include "dashboard.selectorLabels" . }}
app.kubernetes.io/version: {{ .Values.image.tag | default .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{- end -}}

{{/* A VirtualService http route to the dashboards Service for one host. */}}
{{- define "dashboard.httpRoute" -}}
- headers:
    request:
      set:
        x-forwarded-host: {{ .host | quote }}
        x-forwarded-proto: https
  match:
    - uri:
        prefix: /
  route:
    - destination:
        host: {{ include "dashboard.fullname" .root }}
        port:
          number: {{ .root.Values.service.port }}
{{- end -}}

{{- define "dashboard.serviceAccountName" -}}
{{ include "dashboard.fullname" . }}
{{- end -}}

{{- define "dashboard.ecrRefresher" -}}
{{ include "dashboard.fullname" . }}-ecr-refresh
{{- end -}}

{{/* ECR registry host (<account>.dkr.ecr.<region>.amazonaws.com): ecrPullSecret.registry, else the host of image.repository. */}}
{{- define "dashboard.ecrRegistry" -}}
{{- $registry := .Values.ecrPullSecret.registry | default (first (splitList "/" (toString .Values.image.repository))) -}}
{{- if not (contains ".dkr.ecr." $registry) -}}
{{- fail (printf "ecrPullSecret: %q is not an ECR registry host; set ecrPullSecret.registry or disable ecrPullSecret" $registry) -}}
{{- end -}}
{{- $registry -}}
{{- end -}}

{{/* Job spec that fetches an ECR token and writes the pull secret. Takes dict root, serviceAccount. */}}
{{- define "dashboard.ecrJobSpec" -}}
{{- $v := .root.Values.ecrPullSecret -}}
{{- $registry := include "dashboard.ecrRegistry" .root -}}
backoffLimit: 2
activeDeadlineSeconds: 300
template:
  metadata:
    labels:
      app.kubernetes.io/name: {{ .root.Chart.Name }}-ecr-refresh
      app.kubernetes.io/instance: {{ .root.Release.Name }}
  spec:
    serviceAccountName: {{ .serviceAccount }}
    restartPolicy: Never
    initContainers:
      - name: get-token
        image: {{ $v.awsCliImage }}
        command: ["/bin/sh", "-c", "aws ecr get-login-password --region {{ index (splitList "." $registry) 3 }} > /token/ecr"]
        volumeMounts:
          - name: token
            mountPath: /token
    containers:
      - name: write-secret
        image: {{ $v.kubectlImage }}
        command:
          - /bin/sh
          - -c
          - |
            set -eu
            kubectl create secret docker-registry {{ $v.name }} \
              --namespace {{ .root.Release.Namespace }} \
              --docker-server={{ $registry }} \
              --docker-username=AWS \
              --docker-password="$(cat /token/ecr)" \
              --dry-run=client -o yaml | kubectl apply -f -
        volumeMounts:
          - name: token
            mountPath: /token
            readOnly: true
    volumes:
      - name: token
        emptyDir:
          medium: Memory
{{- end -}}

{{/* The image reference (repository and tag are required). */}}
{{- define "dashboard.image" -}}
"{{ required "image.repository is required" .Values.image.repository }}:{{ required "image.tag is required" .Values.image.tag }}"
{{- end -}}

{{/* imagePullSecrets: the release's ECR pull secret first, then any others. */}}
{{- define "dashboard.imagePullSecrets" -}}
{{- $pullSecrets := .Values.imagePullSecrets }}
{{- if .Values.ecrPullSecret.enabled }}
{{- $pullSecrets = prepend $pullSecrets (dict "name" .Values.ecrPullSecret.name) }}
{{- end }}
{{- with $pullSecrets }}
imagePullSecrets:
  {{- toYaml . | nindent 2 }}
{{- end }}
{{- end -}}

{{/*
Cookie domain of the registry's IAM: iam.cookieDomain when set, otherwise read
from the IAM Deployment at install time (its IAM_STAFF_AUTH_COOKIE_DOMAIN).
The dashboard must be served under it, or the browser never sends it IAM's
session cookies. Lookups need a cluster: `helm template` cannot resolve it,
`helm upgrade --dry-run=server` can.
*/}}
{{- define "dashboard.cookieDomain" -}}
{{- if .Values.iam.cookieDomain -}}
{{- .Values.iam.cookieDomain -}}
{{- else -}}
{{- $found := "" -}}
{{- $deploy := lookup "apps/v1" "Deployment" .Release.Namespace .Values.iam.service -}}
{{- if $deploy -}}
{{- range $c := $deploy.spec.template.spec.containers -}}
{{- range $e := ($c.env | default list) -}}
{{- if and (eq $e.name "IAM_STAFF_AUTH_COOKIE_DOMAIN") $e.value -}}
{{- $found = $e.value -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- required (printf "could not read IAM_STAFF_AUTH_COOKIE_DOMAIN from Deployment %s/%s; set iam.cookieDomain" .Release.Namespace .Values.iam.service) $found -}}
{{- end -}}
{{- end -}}

{{/* Base domain: domain when set, else the IAM cookie domain without its leading dot. */}}
{{- define "dashboard.domain" -}}
{{- .Values.domain | default (trimPrefix "." (include "dashboard.cookieDomain" .)) -}}
{{- end -}}

{{/* <name>[-<environment>].<domain>: the naming every public host of the environment follows. */}}
{{- define "dashboard.hostFor" -}}
{{- $root := .root -}}
{{- if $root.Values.environment -}}
{{- printf "%s-%s.%s" .name $root.Values.environment (include "dashboard.domain" $root) -}}
{{- else -}}
{{- printf "%s.%s" .name (include "dashboard.domain" $root) -}}
{{- end -}}
{{- end -}}

{{/* The dashboard's public host: host when set, else <release>[-<environment>].<domain>. */}}
{{- define "dashboard.host" -}}
{{- .Values.host | default (include "dashboard.hostFor" (dict "root" . "name" .Release.Name)) -}}
{{- end -}}

{{- define "dashboard.publicUrl" -}}
https://{{ include "dashboard.host" . }}
{{- end -}}

{{/* The registry's staff portal: links.staffPortalUrl, else staff-portal-<registry>[-<environment>].<domain>. */}}
{{- define "dashboard.staffPortalUrl" -}}
{{- if .Values.links.staffPortalUrl -}}
{{- .Values.links.staffPortalUrl -}}
{{- else if .Values.registry -}}
https://{{ include "dashboard.hostFor" (dict "root" . "name" (printf "staff-portal-%s" .Values.registry)) }}
{{- end -}}
{{- end -}}

{{/* The dashboard-api: dashboardApi.url, else its Service in this namespace. */}}
{{- define "dashboard.dashboardApiUrl" -}}
{{- .Values.dashboardApi.url | default (printf "http://%s" .Values.dashboardApi.service) | trimSuffix "/" -}}
{{- end -}}

{{/* The registry's IAM as the server calls it: iam.url, else its Service (iam.service). */}}
{{- define "dashboard.iamUrl" -}}
{{- .Values.iam.url | default (printf "http://%s" .Values.iam.service) | trimSuffix "/" -}}
{{- end -}}

{{/* Settings shared by the server and the IAM setup job. */}}
{{- define "dashboard.appEnv" -}}
- name: PUBLIC_URL
  value: {{ include "dashboard.publicUrl" . | quote }}
- name: IAM_URL
  value: {{ include "dashboard.iamUrl" . | quote }}
- name: COOKIE_DOMAIN
  value: {{ include "dashboard.cookieDomain" . | quote }}
- name: LOGIN_PROVIDER_ID
  value: {{ .Values.iam.loginProviderId | quote }}
- name: DASHBOARD_CLIENT_ID
  value: {{ .Values.access.clientId | quote }}
- name: DASHBOARD_ROLE
  value: {{ .Values.access.role | quote }}
{{- end -}}

{{/* Secret holding the Keycloak client secret: iamSetup.clientSecret.name, else the release's own. */}}
{{- define "dashboard.clientSecretName" -}}
{{- .Values.iamSetup.clientSecret.name | default (printf "%s-client" (include "dashboard.fullname" .)) -}}
{{- end -}}
