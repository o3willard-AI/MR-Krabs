{{/*
MR-Krabs Helm chart helpers
*/}}

{{- define "mrkrabs.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "mrkrabs.fullname" -}}
{{- printf "%s-%s" (include "mrkrabs.name" .) .Release.Name | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "mrkrabs.labels" -}}
app.kubernetes.io/name: {{ include "mrkrabs.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "mrkrabs.selectorLabels" -}}
app.kubernetes.io/name: {{ include "mrkrabs.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
