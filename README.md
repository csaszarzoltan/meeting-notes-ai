# MeetingNotesAI

Micro-SaaS for meeting transcription and structured notes.

## Features

- **Transcription**: Upload audio files for transcription via OpenAI Whisper API
- **Extraction**: Automatically extract action items, decisions, and key points using LLM
- **Mode-specific processing**:
  - **General**: Standard meeting notes
  - **Healthcare**: SOAP notes with HIPAA compliance markers
  - **Legal**: Deposition summaries with objection tracking
- **Export**: JSON and Markdown export formats
- **SSRF Protection**: Built-in URL validation to prevent server-side request forgery

## Quick Start

```bash
# Install dependencies
uv sync

# Set your OpenAI API key
export OPENAI_API_KEY=sk-...

# Run the server
uvicorn meeting_notes_ai.main:app --host 0.0.0.0 --port 8000

# Health check
curl http://localhost:8000/healthz
```

## API

### POST /api/v1/meetings

Upload an audio file for processing.

**Parameters:**
- `file` (UploadFile, required): Audio file (WAV, MP3, MP4, WebM, max 25MB)
- `mode` (str, optional): `general`, `healthcare`, or `legal` (default: `general`)
- `language` (str, optional): ISO language code for transcription
- `patient_id` (str, optional): Patient identifier (healthcare mode)
- `consent_confirmed` (bool, optional): Consent confirmation (healthcare mode)
- `case_number` (str, optional): Case number (legal mode)
- `jurisdiction` (str, optional): Jurisdiction (legal mode)

### GET /healthz

Health check endpoint returning service status.

## Testing

```bash
.venv/bin/python -m pytest -q
```

## Deployment

Deployed on Railway. See `railway.toml` for configuration.
