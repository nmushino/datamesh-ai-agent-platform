{{/*
共通ラベル
*/}}
{{- define "platform.labels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: datamesh-ai-agent-platform
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end }}

{{/*
AI Agent セレクターラベル
*/}}
{{- define "aiAgent.selectorLabels" -}}
app: ai-agent-orchestrator
app.kubernetes.io/name: ai-agent-orchestrator
{{- end }}

{{/*
Business API セレクターラベル
*/}}
{{- define "businessApi.selectorLabels" -}}
app: business-api
app.kubernetes.io/name: business-api
{{- end }}

{{/*
イメージ参照
*/}}
{{- define "platform.image" -}}
{{ .Values.global.imageRegistry }}/{{ .name }}:{{ .tag }}
{{- end }}
